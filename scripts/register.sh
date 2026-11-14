#!/usr/bin/env bash
# The register job: the repository's project at IronBee got or made (PUT /v1/code-review-repositories), so that the
# repository and its settings are in IronBee's console before its first pull request. It sends the repository's path
# and the runner's version and reads nothing of the event; it writes nothing to GitHub. A person or a script can run it
# too, for any repository: scripts/register.sh [OWNER/NAME].
#
#   IRONBEE_API_KEY              the account's API key: sent as X-API-Key, through curl's standard input, never as an argument
#   IRONBEE_RUNNER_VERSION       the runner's version, MAJOR.MINOR.PATCH: the workflow's release
#   GITHUB_REPOSITORY            the repository, when no OWNER/NAME is given
#   IRONBEE_API_URL              IronBee's API; https://api.service.ironbee.ai when unset
#
# The log says the project and whether it was made, or which case left the repository without one, and of the licence
# only the warnings a review's run prints: no count, limit or end date of the contract, since a public repository's log
# is public. Exit 0: registered, with a project or without; 1: refused, or no answer; 2: the configuration.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
needs jq curl

ATTEMPTS=3
if [ $# -gt 1 ]; then
  fail 2 "usage: register.sh [OWNER/NAME]"
fi
if [ $# -eq 1 ]; then
  GITHUB_REPOSITORY=$1
fi
repository
version=${IRONBEE_RUNNER_VERSION:-}
[[ $version =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || fail 2 "IRONBEE_RUNNER_VERSION is not MAJOR.MINOR.PATCH"
key=${IRONBEE_API_KEY:-}
key=${key//$'\r'/}
key=${key//$'\n'/}
[ -n "$key" ] || fail 2 "ironbee-api-key: no API key was given (IRONBEE_API_KEY)"
url=${IRONBEE_API_URL:-https://api.service.ironbee.ai}
url="${url%/}/v1/code-review-repositories"

jq -cn --arg path "$IRONBEE_REPO" --arg version "$version" \
  '{repository: {provider: "github", path: $path}, runner: {version: $version}}' > "$IRONBEE_TMP/body.json"
say "report: register $(cat "$IRONBEE_TMP/body.json")"

# Each attempt's answer: its HTTP status, or 000 with why there was none. A connection that fails, a timeout, a 429 or a
# 5xx is tried again, after two seconds and then five; any other answer is the answer.
status=000
why=""
for n in 1 2 3; do
  case $n in 2) sleep 2 ;; 3) sleep 5 ;; esac
  rc=0
  status=$(printf 'X-API-Key: %s\n' "$key" | curl --silent --show-error --request PUT \
    --connect-timeout 10 --max-time 30 \
    --header @- --header "Content-Type: application/json" --header "Accept: application/json" \
    --user-agent "ironbee-runner/$version" \
    --data-binary @"$IRONBEE_TMP/body.json" --output "$IRONBEE_TMP/answer.json" --write-out '%{http_code}' \
    "$url" 2> "$IRONBEE_TMP/curl.err") || rc=$?
  if [ "$rc" != 0 ]; then
    status=000
    why="no connection (curl exit $rc)"
    continue
  fi
  case $status in
    429 | 5??) why="HTTP $status" ;;
    *) break ;;
  esac
done
case $status in
  000 | 429 | 5??) fail 1 "IronBee: no answer after $ATTEMPTS attempts ($why)" ;;
esac

answer=$IRONBEE_TMP/answer.json
[ -s "$answer" ] || echo null > "$answer"
if ! jq -e . "$answer" > /dev/null 2>&1; then
  echo null > "$answer"
fi
if [ "$status" -ge 400 ]; then
  code=$(ijq -r --argjson status "$status" 'include "ironbee"; refusal($status) | .code' "$answer")
  sentence=$(ijq -r --argjson status "$status" 'include "ironbee"; refusal($status) | .sentence' "$answer")
  fail 1 "IronBee refused the registration ($code): $sentence"
fi
if [ "$(jq -r 'type' "$answer")" != object ]; then
  fail 1 "IronBee: the registration's answer could not be read"
fi

today=$(jq -n 'now / 86400 | floor')
ijq -r --arg version "$version" --argjson today "$today" 'include "ironbee"; warnings($version; $today)' "$answer"
ijq 'include "ironbee"; registered' "$answer" > "$IRONBEE_TMP/registered.json"
dropped=$(jq -r '.dropped // empty' "$IRONBEE_TMP/registered.json")
if [ -n "$dropped" ]; then
  say "IronBee: dropped noProject \"$dropped\": a value this release does not know"
fi
if [ "$(jq -r '.project != null' "$IRONBEE_TMP/registered.json")" = true ]; then
  id=$(jq -r .project.id "$IRONBEE_TMP/registered.json")
  if [ "$(jq -r .project.created "$IRONBEE_TMP/registered.json")" = true ]; then
    say "registered $IRONBEE_REPO: project $id, made now"
  else
    say "registered $IRONBEE_REPO: project $id, found"
  fi
else
  case_=$(jq -r '.why // "no case given"' "$IRONBEE_TMP/registered.json")
  say "registered $IRONBEE_REPO without a project ($case_): its pull requests are reviewed with the account's settings and the workflow's own inputs"
fi
