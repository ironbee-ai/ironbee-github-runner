#!/usr/bin/env bash
# The review step: the runner's image pulled by its digest and run, for the action the decide step handed on. The
# registry token goes into a docker configuration of this step's own, written from the shell with no command line
# carrying it and no credential helper asked, and removed once the image is pulled. The container gets every variable
# below by name (`-e NAME`, its value from this step's environment), so no secret is ever on a command line; the event
# file read-only and the step's outputs file, where the runner writes `concluding`. It runs as the job's own user (the
# image's entry point fits its home to any uid), or under rootless Docker as the container's root, which is that user;
# Docker with userns-remap is refused, since the container could not write the outputs file.
#
# Signals: the workflow's step execs this script, and this script execs the docker client once the image is pulled, so
# a cancel or the step's timeout signals the docker client itself, which hands it to the image's init and the runner.
# One that comes earlier stops the pull it waits for and ends the step: nothing runs.
#
#   IRONBEE_IMAGE                the image: docker.io/<namespace>/<name>@sha256:<64 hex>, the release's; its namespace is
#                                the name Docker Hub's organization token signs in with
#   IRONBEE_REGISTRY_TOKEN       the read-only token that pulls it (secret registry-token)
#   GITHUB_EVENT_PATH, GITHUB_OUTPUT, RUNNER_TEMP   as Actions gives them
#   and each of PASSED below, for the runner (its core/runner/environment.yaml)
#
# review.sh stop: the container a run left, stopped and removed (a runner killed before docker could stop it); nothing
# when there is none. It never fails: it runs after every run, a successful one included.
#
# Exit: the runner's own (0 the run ended, 1 it failed, 2 a usage or configuration error); 1 when the image could not
# be pulled or the daemon reached; 2 for this step's configuration; 130 or 143 when stopped before the image ran.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# What the runner reads, handed on by name: the workflow's inputs and secrets, the job's token, the decide step's
# action, Actions' own names for the event and the repository, and a proxy where the runner's machine has one.
PASSED=(
  IRONBEE_MODEL_PROVIDER IRONBEE_MODEL_URL IRONBEE_MODEL_KEY IRONBEE_MODEL_HEADERS IRONBEE_MODEL_CA_CERTIFICATE
  IRONBEE_MODEL_NAME IRONBEE_MODEL_PREFIX IRONBEE_MODEL_MAX_OUTPUT AWS_REGION IRONBEE_JEV_KEY
  IRONBEE_API_KEY IRONBEE_API_URL IRONBEE_RUN_REPORTS
  IRONBEE_KNOWLEDGE_REPOSITORY IRONBEE_KNOWLEDGE_REF IRONBEE_KNOWLEDGE_TOKEN
  IRONBEE_IGNORE_PATHS IRONBEE_TARGET_BRANCHES IRONBEE_SKIP_LABELS IRONBEE_SKIP_TITLE_KEYWORDS
  GITHUB_TOKEN IRONBEE_APP_ID IRONBEE_APP_PRIVATE_KEY IRONBEE_APP_SLUG IRONBEE_GITHUB_CA_CERTIFICATE
  IRONBEE_ACTION IRONBEE_PULL_REQUEST IRONBEE_COMMENT_ID
  GITHUB_EVENT_NAME GITHUB_REPOSITORY GITHUB_API_URL
  HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy
)
EVENT=/github/event.json                                        # where the container reads the event file
OUTPUT=/github/output                                           # and writes the step's outputs
IMAGE='^docker\.io/([a-z0-9]+([._-][a-z0-9]+)*)/[a-z0-9]+([._-][a-z0-9]+)*@sha256:[0-9a-f]{64}$'

cid=${RUNNER_TEMP:-}/ironbee-review.cid                         # the container's id, for the stop

if [ "${1:-}" = stop ]; then
  if [ -z "${RUNNER_TEMP:-}" ] || [ ! -s "$cid" ] || ! command -v docker > /dev/null; then
    exit 0
  fi
  id=$(cat "$cid")
  rm -f "$cid"
  case $id in '' | *[!0-9a-f]*) exit 0 ;; esac
  if docker container inspect "$id" > /dev/null 2>&1; then
    docker stop --time 15 "$id" > /dev/null 2>&1 || true
    docker rm --force "$id" > /dev/null 2>&1 || true
    say "review: the run's container was still there: stopped and removed"
  fi
  exit 0
fi
[ $# = 0 ] || fail 2 "usage: review.sh [stop]"
needs docker
[ -d "${RUNNER_TEMP:-}" ] || fail 2 "RUNNER_TEMP is not a directory"

image=${IRONBEE_IMAGE:-}
[[ $image =~ $IMAGE ]] || fail 2 "IRONBEE_IMAGE names no image of Docker Hub by digest"
namespace=${BASH_REMATCH[1]}
[ -n "${IRONBEE_REGISTRY_TOKEN:-}" ] || fail 2 "the registry-token secret is not set"
event=${GITHUB_EVENT_PATH:-}
output=${GITHUB_OUTPUT:-}
for file in "$event" "$output"; do
  case $file in /*) ;; *) fail 2 "GITHUB_EVENT_PATH and GITHUB_OUTPUT must name files by absolute paths" ;; esac
  case $file in *,*) fail 2 "$file: a path with a comma cannot be mounted" ;; esac
  [ -f "$file" ] || fail 2 "$file is not a file"
done

# A cancel before the image runs stops what is waited for; the exit removes the docker configuration with the rest.
child=""
cancelled() {
  [ -z "$child" ] || kill "$child" 2> /dev/null || true
  say "review: stopped before the image ran; nothing was run"
  exit "$1"
}
trap 'cancelled 130' INT
trap 'cancelled 143' TERM

# watched OUT ERR COMMAND...: COMMAND in the background and waited for, so that a signal is taken at once.
watched() {
  local out=$1 err=$2 code=0
  shift 2
  "$@" > "$out" 2> "$err" &
  child=$!
  wait "$child" || code=$?
  child=""
  return "$code"
}

# Who the container runs as: the job's user; under rootless Docker the container's root, which is that user.
if ! watched "$IRONBEE_TMP/info" "$IRONBEE_TMP/info.err" docker info --format '{{json .SecurityOptions}}'; then
  fail 1 "docker could not reach its daemon: $(tail -n 1 "$IRONBEE_TMP/info.err")"
fi
security=$(cat "$IRONBEE_TMP/info")
case $security in
  *'"name=userns'*) fail 2 "Docker runs with userns-remap, which the review step does not support: the container's users could not write the step's outputs file" ;;
  *'"name=rootless'*) user=0:0 ;;
  *) user="$(id -u):$(id -g)" ;;
esac

# The token for the pull alone, in a configuration that names it for Docker Hub and no credential helper.
config=$IRONBEE_TMP/docker
mkdir -m 700 "$config"
auth=$(printf '%s:%s' "$namespace" "$IRONBEE_REGISTRY_TOKEN" | base64 | tr -d '\n')
printf '{"auths":{"https://index.docker.io/v1/":{"auth":"%s"}}}\n' "$auth" > "$config/config.json"
unset auth IRONBEE_REGISTRY_TOKEN
if ! watched /dev/null "$IRONBEE_TMP/pull.err" env DOCKER_CONFIG="$config" docker pull --quiet "$image"; then
  fail 1 "the runner's image could not be pulled ($image): $(tail -n 1 "$IRONBEE_TMP/pull.err")"
fi
rm -rf "$config"
say "review: $image pulled"

args=(run --rm --cidfile "$cid" --user "$user"
  --mount "type=bind,source=$event,target=$EVENT,readonly" -e "GITHUB_EVENT_PATH=$EVENT"
  --mount "type=bind,source=$output,target=$OUTPUT" -e "GITHUB_OUTPUT=$OUTPUT")
for name in "${PASSED[@]}"; do
  args+=(-e "$name")
done
rm -f "$cid"
rm -rf "$IRONBEE_TMP"
trap - INT TERM EXIT
exec docker "${args[@]}" "$image" ironbee-runner --print-report
