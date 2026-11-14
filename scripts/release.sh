#!/usr/bin/env bash
# A release of this repository's reusable workflows, one step at a time: scripts/release.sh STEP, run from the
# repository's root by the release workflow (.github/workflows/release.yml). Every step reads the release's inputs from
# its environment and checks each by its form first; none is ever evaluated as code.
#
#   IRONBEE_VERSION        MAJOR.MINOR.PATCH: the version every listed workflow and its image share
#   IRONBEE_PRERELEASE     rc.<N> for a pre-release, tagged v<version>-rc.<N>; empty for a release, tagged v<version>
#   IRONBEE_IMAGE_DIGEST   sha256:<64 hex>: the image's index digest, as the image's publishing printed it
#
#   workflows        the workflows a release stamps, each with the image it runs
#   plan             the release's tag new, or this very release's (a run again after its push); a release never
#                    below the newest one; no pre-release of a released version; every listed workflow stampable
#   index            each image's index by digest: linux/amd64 and linux/arm64 alone, and the version's tag naming it
#   image ARCH       each image's linux/ARCH image, pulled by digest on a runner of that architecture and run with no
#                    network: its runner reports the version
#   signature        each index's signature with the committed public key: a release's must verify, a pre-release's
#                    may have been signed for IronBee's own tests. GITHUB_OUTPUT gets signature: verified or tests
#   stamp            each listed workflow given the digest and the version, in the working tree
#   token            whether the push's token (IRONBEE_PUSH_TOKEN) may push a workflow file: a classic token's scopes
#                    must hold `workflow`; a fine-grained token's permissions cannot be read, and a notice says so
#   publish          the stamp committed on main, tagged, the floating tag moved, all pushed at once; nothing when the
#                    tag is already this release's
#   github-release   the GitHub release, when it is missing (GH_TOKEN; IRONBEE_SIGNATURE, the signature step's)
#
# Exit 0: done; 1: refused, or a call that failed; 2: the inputs, the repository or the runner.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# The reusable workflows a release stamps, `<workflow> <image>` a line, all given the same version. A second line needs
# a digest of its own, which image-digest cannot give: the inputs refuse it until the release takes one per image.
WORKFLOWS='.github/workflows/code-review.yml docker.io/ironbeeai/ironbee-code-review-runner'
KEY=ironbee-image-signing.pem                                   # IronBee's public key: a release's image verifies with it
PLATFORMS="linux/amd64 linux/arm64"

SEMVER='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
RELEASE_TAG='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
RC='^rc\.[1-9][0-9]*$'
DIGEST='^sha256:[0-9a-f]{64}$'
ZEROS=sha256:$(printf '%064d' 0)
IMAGE_LINE='^([[:space:]]*image:[[:space:]]+)([^@[:space:]]+)@(sha256:[0-9a-f]{64})([[:space:]].*)?$'
VERSION_LINE='^([[:space:]]*IRONBEE_RUNNER_VERSION:[[:space:]]+)([0-9]+\.[0-9]+\.[0-9]+)([[:space:]].*)?$'

notice() { printf '::notice::%s\n' "$(command_text "$*")"; }

# bot ARGS...: git as github-actions[bot], the author, committer and tagger of what a release writes.
bot() {
  GIT_AUTHOR_NAME='github-actions[bot]' GIT_AUTHOR_EMAIL='41898282+github-actions[bot]@users.noreply.github.com' \
    GIT_COMMITTER_NAME='github-actions[bot]' GIT_COMMITTER_EMAIL='41898282+github-actions[bot]@users.noreply.github.com' git "$@"
}

tools() {
  local tool
  for tool in "$@"; do
    command -v "$tool" > /dev/null || fail 2 "$tool is not installed on this runner"
  done
}

# The inputs, each by its form, and the names they give: tag (the repository's), image_tag (the image's), floating
# (v0 follows the pre-releases, v<MAJOR> the releases of that major version).
inputs() {
  local lines
  version=${IRONBEE_VERSION:-}
  prerelease=${IRONBEE_PRERELEASE:-}
  digest=${IRONBEE_IMAGE_DIGEST:-}
  [[ $version =~ $SEMVER ]] || fail 2 "version is not MAJOR.MINOR.PATCH"
  major=${BASH_REMATCH[1]}
  if [ -n "$prerelease" ] && ! [[ $prerelease =~ $RC ]]; then
    fail 2 "prerelease is not rc.<N>, N from 1"
  fi
  [[ $digest =~ $DIGEST ]] || fail 2 "image-digest is not sha256:<64 hex>"
  [ "$digest" != "$ZEROS" ] || fail 2 "image-digest is the placeholder of all zeros"
  if [ -n "$prerelease" ]; then
    tag=v$version-$prerelease
    image_tag=$version-$prerelease
    floating=v0
  else
    [ "$major" != 0 ] || fail 2 "a release of major version 0: v0 is the pre-releases' tag"
    tag=v$version
    image_tag=$version
    floating=v$major
  fi
  lines=$(printf '%s\n' "$WORKFLOWS" | grep -c .)
  [ "$lines" = 1 ] || fail 2 "the release lists $lines workflows, and image-digest names the index of one image"
}

# newer A B: whether version A is above version B, each MAJOR.MINOR.PATCH with no leading zero.
newer() {
  local a b i x y
  IFS=. read -r -a a <<< "$1"
  IFS=. read -r -a b <<< "$2"
  for i in 0 1 2; do
    x=${a[$i]}
    y=${b[$i]}
    if [ "${#x}" != "${#y}" ]; then
      [ "${#x}" -gt "${#y}" ]
      return
    fi
    if [ "$x" != "$y" ]; then
      [[ $x > $y ]]
      return
    fi
  done
  return 1
}

# The newest release's version among the tags, or nothing.
newest_release() {
  local t newest=""
  while IFS= read -r t; do
    [[ $t =~ $RELEASE_TAG ]] || continue
    if [ -z "$newest" ] || newer "${t#v}" "$newest"; then
      newest=${t#v}
    fi
  done < <(git tag -l 'v*')
  printf '%s' "$newest"
}

# stamp_file FILE NAME IMAGE OUT: FILE with its one image line naming IMAGE given the release's digest and its one
# IRONBEE_RUNNER_VERSION line given the release's version, written to OUT; a trailing comment keeps its column. Sets
# was_digest and was_version to what FILE named. NAME is FILE's name in the messages.
stamp_file() {
  local file=$1 name=$2 image=$3 out=$4 line images=0 versions=0 rest lead width
  was_digest=""
  was_version=""
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ $line =~ $IMAGE_LINE ]] && [ "${BASH_REMATCH[2]}" = "$image" ]; then
      images=$((images + 1))
      was_digest=${BASH_REMATCH[3]}
      line=${BASH_REMATCH[1]}$image@$digest${BASH_REMATCH[4]}
    elif [[ $line =~ $VERSION_LINE ]]; then
      versions=$((versions + 1))
      was_version=${BASH_REMATCH[2]}
      rest=${BASH_REMATCH[3]}
      line=${BASH_REMATCH[1]}$version
      if [ -n "$rest" ]; then
        lead=${rest%%[![:space:]]*}
        width=$((${#was_version} + ${#lead} - ${#version}))
        [ "$width" -ge 1 ] || width=1
        line=$line$(printf '%*s' "$width" '')${rest#"$lead"}
      fi
    fi
    printf '%s\n' "$line"
  done < "$file" > "$out"
  [ "$images" = 1 ] || fail 2 "$name: the image line naming $image is there $images times, not once"
  [ "$versions" = 1 ] || fail 2 "$name: the IRONBEE_RUNNER_VERSION line is there $versions times, not once"
}

# pushed: whether the release's tag exists, its commit's workflows naming this image and this version: a run again
# after its push. A tag that names anything else is refused, since a tag is never moved.
pushed() {
  local workflow image
  git rev-parse -q --verify "refs/tags/$tag" > /dev/null || return 1
  while read -r workflow image <&3; do
    git show "refs/tags/$tag:$workflow" > "$IRONBEE_TMP/tagged" 2> /dev/null || fail 1 "$tag exists without $workflow: a tag is never moved"
    stamp_file "$IRONBEE_TMP/tagged" "$tag:$workflow" "$image" "$IRONBEE_TMP/tagged.stamped"
    if [ "$was_digest" != "$digest" ] || [ "$was_version" != "$version" ]; then
      fail 1 "$tag exists and names $image@$was_digest, version $was_version: a tag is never moved"
    fi
  done 3<<< "$WORKFLOWS"
  return 0
}

# read_index REF: the index at REF, in $IRONBEE_TMP/index.json, holding linux/amd64 and linux/arm64 alone.
read_index() {
  local platforms
  docker buildx imagetools inspect --raw "$1" > "$IRONBEE_TMP/index.json" 2> "$IRONBEE_TMP/docker.err" \
    || fail 1 "could not read $1: $(tail -n 1 "$IRONBEE_TMP/docker.err")"
  platforms=$(jq -r '[.manifests[]? | (.platform.os // "?") + "/" + (.platform.architecture // "?")] | sort | join(" ")' \
    "$IRONBEE_TMP/index.json" 2> /dev/null) || fail 1 "$1 is no image index"
  [ "$platforms" = "$PLATFORMS" ] || fail 1 "$1 holds ${platforms:-no platform}, not $PLATFORMS alone"
}

# platform_digest ARCH: the index's linux/ARCH image, by digest, in $platform.
platform_digest() {
  platform=$(jq -r --arg arch "$1" '.manifests[] | select(.platform.os == "linux" and .platform.architecture == $arch) | .digest' \
    "$IRONBEE_TMP/index.json")
  [[ $platform =~ $DIGEST ]] || fail 1 "the index names no digest for linux/$1"
}

step_plan() {
  local workflow image newest
  tools git
  [ "${GITHUB_REF:-}" = refs/heads/main ] || fail 2 "a release runs from main, not ${GITHUB_REF:-an unknown ref}"
  if [ -n "$prerelease" ] && git rev-parse -q --verify "refs/tags/v$version" > /dev/null; then
    fail 1 "v$version is released: it takes no more pre-releases"
  fi
  newest=$(newest_release)
  if [ -z "$prerelease" ] && [ -n "$newest" ] && newer "$newest" "$version"; then
    fail 1 "v$version is below the newest release, v$newest"
  fi
  while read -r workflow image <&3; do
    [ -f "$workflow" ] || fail 2 "$workflow is listed for the release and missing"
    stamp_file "$workflow" "$workflow" "$image" "$IRONBEE_TMP/stamped"
  done 3<<< "$WORKFLOWS"
  if pushed; then
    notice "$tag is already pushed with this image and version: this run moves nothing, and makes the GitHub release if it is missing"
  else
    say "$tag is new${newest:+; the newest release is v$newest}"
  fi
  say "tag $tag, image tag $image_tag, floating tag $floating"
}

step_index() {
  local image amd64 arm64 named
  tools docker jq
  while read -r _ image <&3; do
    read_index "$image@$digest"
    platform_digest amd64
    amd64=$platform
    platform_digest arm64
    arm64=$platform
    docker buildx imagetools inspect "$image:$image_tag" --format '{{json .Manifest}}' > "$IRONBEE_TMP/tagged.json" 2> "$IRONBEE_TMP/docker.err" \
      || fail 1 "could not read $image:$image_tag: $(tail -n 1 "$IRONBEE_TMP/docker.err")"
    named=$(jq -r '.digest // empty' "$IRONBEE_TMP/tagged.json" 2> /dev/null || true)
    [ "$named" = "$digest" ] || fail 1 "$image:$image_tag names ${named:-nothing}, not $digest"
    say "$image@$digest: linux/amd64 $amd64, linux/arm64 $arm64; $image:$image_tag names it"
  done 3<<< "$WORKFLOWS"
}

step_image() {
  local arch=$1 machine image ref named reported
  case $arch in amd64 | arm64) ;; *) fail 2 "image: amd64 or arm64" ;; esac
  tools docker jq
  machine=$(docker version --format '{{.Server.Arch}}' 2> /dev/null || true)
  [ "$machine" = "$arch" ] || fail 2 "this runner's docker is ${machine:-not running}, not $arch: each image runs on its own architecture"
  while read -r _ image <&3; do
    read_index "$image@$digest"
    platform_digest "$arch"
    ref=$image@$platform
    docker pull --quiet "$ref" > /dev/null 2> "$IRONBEE_TMP/docker.err" || fail 1 "could not pull $ref: $(tail -n 1 "$IRONBEE_TMP/docker.err")"
    named=$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$ref" 2> /dev/null || true)
    [ "$named" = "linux/$arch" ] || fail 1 "$ref is ${named:-no image pulled}, not linux/$arch"
    reported=$(docker run --rm --pull never --network none --entrypoint python "$ref" -c 'from core.runner import VERSION; print(VERSION)' \
      2> "$IRONBEE_TMP/docker.err") || fail 1 "$ref did not run: $(tail -n 1 "$IRONBEE_TMP/docker.err")"
    [ "$reported" = "$version" ] || fail 1 "$ref's runner reports ${reported:-nothing}, not $version"
    say "$ref, linux/$arch, run with no network: its runner reports $version"
  done 3<<< "$WORKFLOWS"
}

step_signature() {
  local image ref result=verified
  tools cosign
  [ -n "${GITHUB_OUTPUT:-}" ] || fail 2 "GITHUB_OUTPUT is not set"
  if [ -z "$prerelease" ] && [ ! -s "$KEY" ]; then
    fail 1 "$KEY is missing: a release's image verifies with IronBee's public key, committed at the repository's root"
  fi
  while read -r _ image <&3; do
    ref=$image@$digest
    if [ -s "$KEY" ] && cosign verify --key "$KEY" "$ref" > /dev/null 2> "$IRONBEE_TMP/cosign.err"; then
      say "$ref: its signature verifies with $KEY"
    elif [ -z "$prerelease" ]; then
      cat "$IRONBEE_TMP/cosign.err" >&2
      fail 1 "$ref: its signature does not verify with $KEY"
    else
      notice "$ref does not verify with $KEY: a pre-release signed for IronBee's own tests"
      result=tests
    fi
  done 3<<< "$WORKFLOWS"
  echo "signature=$result" >> "$GITHUB_OUTPUT"
}

step_stamp() {
  local workflow image n=0
  while read -r workflow image <&3; do
    n=$((n + 1))
    [ -f "$workflow" ] || fail 2 "$workflow is listed for the release and missing"
    stamp_file "$workflow" "$workflow" "$image" "$IRONBEE_TMP/stamped.$n"
    say "stamped $workflow: $image@$digest (was $was_digest), IRONBEE_RUNNER_VERSION $version (was $was_version)"
  done 3<<< "$WORKFLOWS"
  n=0
  while read -r workflow _ <&3; do
    n=$((n + 1))
    cat "$IRONBEE_TMP/stamped.$n" > "$workflow"
  done 3<<< "$WORKFLOWS"
}

# GitHub refuses a push that changes a workflow file from a token without the right to. A classic token's scopes come
# back in the x-oauth-scopes header, the one header read and printed; a fine-grained token sends none back. The token
# goes to curl through its standard input, never as an argument.
step_token() {
  local token=${IRONBEE_PUSH_TOKEN:-} url status scopes
  tools curl
  token=${token//$'\r'/}
  token=${token//$'\n'/}
  [ -n "$token" ] || fail 2 "IRONBEE_PUSH_TOKEN is not set: the publishing job's token (GH_ACCESS_TOKEN) was not given"
  url=${GITHUB_API_URL:-https://api.github.com}
  status=$(printf 'Authorization: Bearer %s\n' "$token" | curl --silent --show-error --connect-timeout 10 --max-time 30 \
    --header @- --header "Accept: application/vnd.github+json" --dump-header "$IRONBEE_TMP/headers" --output /dev/null \
    --write-out '%{http_code}' "${url%/}/" 2> "$IRONBEE_TMP/curl.err") \
    || fail 1 "GitHub could not be asked about the push's token: $(tail -n 1 "$IRONBEE_TMP/curl.err")"
  [ "$status" = 200 ] || fail 1 "GitHub refused the push's token (HTTP $status)"
  if ! grep -qi '^x-oauth-scopes:' "$IRONBEE_TMP/headers"; then
    notice "the push's token names no scopes, as a fine-grained token does: its Workflows permission could not be checked here, and the push will show it"
    return 0
  fi
  scopes=$(grep -i '^x-oauth-scopes:' "$IRONBEE_TMP/headers" | tail -n 1 | cut -d: -f2- | tr -d '\r' | sed 's/^ *//; s/ *$//')
  if printf '%s\n' "$scopes" | tr ',' '\n' | sed 's/^ *//; s/ *$//' | grep -qx workflow; then
    say "the push's token may push a workflow file (its scopes: $scopes)"
  else
    fail 1 "the push's token lacks the workflow scope (its scopes: ${scopes:-none}), and GitHub would refuse its push of a workflow file"
  fi
}

step_publish() {
  local workflow was moved=""
  tools git
  if pushed; then
    notice "$tag is already pushed with this image and version: nothing is moved"
    return 0
  fi
  [ -z "$(git status --porcelain --untracked-files=no)" ] || fail 2 "the working tree holds changes: a release commits its stamp alone"
  step_stamp
  was=$(git rev-parse -q --verify "refs/tags/$floating" || true)
  if [ -n "$was" ]; then
    moved=" from $(git rev-parse --short "$was^{commit}")"
  fi
  while read -r workflow _ <&3; do
    git add -- "$workflow"
  done 3<<< "$WORKFLOWS"
  # The same image and version as main already names (a pre-release promoted as it is) stamp nothing: an empty commit.
  bot commit --quiet --allow-empty -m "chore(release): $tag"
  if [ -n "$prerelease" ]; then
    bot tag -a "$tag" -m "$version-$prerelease: a pre-release for IronBee's own tests"
    bot tag -f -a "$floating" -m "$floating: the newest pre-release ($tag)" > /dev/null
  else
    bot tag -a "$tag" -m "$version: a release"
    bot tag -f -a "$floating" -m "$floating: the newest release of major version $major ($tag)" > /dev/null
  fi
  # All or nothing. main only moves forward; the tag is new; the floating tag moves only from where it was read.
  if ! git push --quiet --atomic --force-with-lease="refs/tags/$floating:$was" origin \
    HEAD:refs/heads/main "refs/tags/$tag" "refs/tags/$floating"; then
    fail 1 "the push was refused and nothing was pushed: main or a tag moved meanwhile; run the release again"
  fi
  say "pushed $(git rev-parse --short HEAD) to main, tagged $tag; $floating moved to it$moved"
}

# The GitHub release's text: the image by digest, its platforms, and how to verify it.
notes() {
  local image
  if [ -n "$prerelease" ]; then
    printf '%s\n\n' "A pre-release of $version for IronBee's own tests, not for production."
  fi
  while read -r _ image <&3; do
    printf '%s\n\n' "Image: \`$image@$digest\`" "Platforms: ${PLATFORMS// /, }"
    if [ "$IRONBEE_SIGNATURE" = verified ]; then
      printf '%s\n\n' "Its signature verifies with cosign v3 and \`$KEY\` from this repository:" "    cosign verify --key $KEY $image@$digest"
    else
      printf '%s\n\n' "It was signed for IronBee's own tests: it does not verify with \`$KEY\` from this repository."
    fi
  done 3<<< "$WORKFLOWS"
}

step_github_release() {
  local status pre=false
  tools git gh jq
  repository
  case ${IRONBEE_SIGNATURE:-} in verified | tests) ;; *) fail 2 "IRONBEE_SIGNATURE is not verified or tests" ;; esac
  [ -n "$prerelease" ] || [ "$IRONBEE_SIGNATURE" = verified ] || fail 2 "a release's image verifies with $KEY"
  git ls-remote --exit-code --tags origin "refs/tags/$tag" > /dev/null || fail 1 "$tag is not pushed: a GitHub release is made for a pushed tag alone"
  status=$(api GET "repos/$IRONBEE_REPO/releases/tags/$tag" "$IRONBEE_TMP/release.json")
  case $status in
    200)
      notice "the GitHub release $tag exists: nothing to do"
      return 0
      ;;
    404) ;;
    *) fail 1 "GitHub did not say whether the release $tag exists (HTTP $status)" ;;
  esac
  notes > "$IRONBEE_TMP/notes.md"
  [ -z "$prerelease" ] || pre=true
  jq -n --arg tag "$tag" --rawfile notes "$IRONBEE_TMP/notes.md" --argjson pre "$pre" \
    '{tag_name: $tag, name: $tag, body: $notes, prerelease: $pre, make_latest: (if $pre then "false" else "true" end)}' \
    > "$IRONBEE_TMP/release.in.json"
  status=$(api POST "repos/$IRONBEE_REPO/releases" "$IRONBEE_TMP/release.json" "$IRONBEE_TMP/release.in.json")
  # A create GitHub made without answering is found by looking again.
  if [ "$status" != 200 ] && [ "$(api GET "repos/$IRONBEE_REPO/releases/tags/$tag" "$IRONBEE_TMP/release.json")" != 200 ]; then
    fail 1 "GitHub did not make the release $tag (HTTP $status)"
  fi
  say "made the GitHub release $tag"
}

usage="usage: release.sh workflows|plan|index|image ARCH|signature|stamp|token|publish|github-release"
step=${1:-}
[ $# -eq 0 ] || shift
if [ "$step" = image ]; then
  [ $# -eq 1 ] || fail 2 "$usage"
else
  [ $# -eq 0 ] || fail 2 "$usage"
fi
case $step in
  workflows) printf '%s\n' "$WORKFLOWS" ;;
  plan) inputs; step_plan ;;
  index) inputs; step_index ;;
  image) inputs; step_image "$1" ;;
  signature) inputs; step_signature ;;
  stamp) inputs; step_stamp ;;
  token) inputs; step_token ;;
  publish) inputs; step_publish ;;
  github-release) inputs; step_github_release ;;
  *) fail 2 "$usage" ;;
esac
