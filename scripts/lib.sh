# Shared by the workflow's scripts, sourced and never run: the log, GitHub's API through gh, who we are, and what of
# ours a commit holds. Needs bash, jq and gh (curl for the registration). Every value of an event or of an answer is
# read with jq from a file; none is ever evaluated as code.

IRONBEE_SCRIPTS=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
IRONBEE_CHECK="IronBee review"                                  # the check's name: the gate a repository requires
IRONBEE_JOB_SLUG=github-actions                                 # the job token's App, which writes as github-actions[bot]
IRONBEE_ALIAS=ironbee-ai                                        # what people call the reviewer under the job token
export GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1

IRONBEE_TMP=$(mktemp -d)
trap 'rm -rf "$IRONBEE_TMP"' EXIT

say() { printf '%s\n' "$*"; }

# fail CODE TEXT...: an error annotation, then the exit: 1 a failure, 2 the workflow's configuration.
fail() {
  local code=$1
  shift
  printf '::error::%s\n' "$(printf '%s' "$*" | sed 's/%/%25/g')"
  exit "$code"
}

# needs TOOL...: each on the runner's PATH, or a configuration error naming it.
needs() {
  local tool
  for tool in "$@"; do
    command -v "$tool" > /dev/null || fail 2 "$tool is not installed on this runner; the workflow's jobs need bash, jq, gh and curl"
  done
}

# ijq ARGS...: jq with the rules of ironbee.jq; the filter names them after `include "ironbee";`.
ijq() { jq -L "$IRONBEE_SCRIPTS" "$@"; }

is_number() { case ${1:-} in '' | 0* | *[!0-9]*) return 1 ;; *) return 0 ;; esac; }

is_sha() {
  case ${#1} in 40 | 64) ;; *) return 1 ;; esac
  case $1 in *[!0-9a-f]*) return 1 ;; *) return 0 ;; esac
}

# The identity the reviewer writes as, from IRONBEE_APP_SLUG: the customer's own App when it is set, else the job's
# token. Sets IRONBEE_SLUG (whose checks are ours), IRONBEE_LOGIN (whose texts are ours) and IRONBEE_MENTION. An App's
# slug is lowercase on GitHub, its bot's login with it, whatever case the workflow gives it in.
identity() {
  local slug=${IRONBEE_APP_SLUG:-}
  slug=${slug#@}
  if [ -n "$slug" ]; then
    case $slug in *[!A-Za-z0-9-]*) fail 2 "app-slug is no GitHub App's slug" ;; esac
    slug=$(printf '%s' "$slug" | tr '[:upper:]' '[:lower:]')
    IRONBEE_SLUG=$slug
    IRONBEE_LOGIN="$slug[bot]"
    IRONBEE_MENTION="@$slug"
  else
    IRONBEE_SLUG=$IRONBEE_JOB_SLUG
    IRONBEE_LOGIN="$IRONBEE_JOB_SLUG[bot]"
    IRONBEE_MENTION="@$IRONBEE_ALIAS"
  fi
}

repository() {
  IRONBEE_REPO=${GITHUB_REPOSITORY:-}
  case $IRONBEE_REPO in */*/* | /* | */ | *[[:space:]]* | '') fail 2 "GITHUB_REPOSITORY names no repository (owner/name)" ;; esac
  case $IRONBEE_REPO in */*) ;; *) fail 2 "GITHUB_REPOSITORY names no repository (owner/name)" ;; esac
}

# api [--paginate] METHOD PATH OUT [IN]: one call of GitHub's REST API through gh, as GH_TOKEN; the answer's body in
# OUT (with --paginate every page's, one after the other) and its HTTP status printed: 200 for any success, 000 when
# no answer came. No answer, a 429 or a 5xx is tried three times in all. IN is the request's JSON body.
api() {
  local page="" method path out in n status=000
  if [ "$1" = --paginate ]; then
    page=--paginate
    shift
  fi
  method=$1 path=$2 out=$3 in=${4:-}
  for n in 1 2 3; do
    case $n in 2) sleep 2 ;; 3) sleep 5 ;; esac
    # shellcheck disable=SC2086  # $page is one flag or none
    if gh api $page --method "$method" ${in:+--input "$in"} "$path" > "$out" 2> "$IRONBEE_TMP/gh.err"; then
      echo 200
      return 0
    fi
    status=$(grep -o 'HTTP [0-9][0-9][0-9]' "$IRONBEE_TMP/gh.err" | tail -n 1 | cut -c6-)
    status=${status:-000}
    case $status in 000 | 429 | 5??) ;; *) break ;; esac
  done
  echo "$status"
}

# ours_checks HEAD OUT: the checks named IronBee review that our identity's App wrote on the commit, oldest first.
ours_checks() {
  local status
  status=$(api --paginate GET "repos/$IRONBEE_REPO/commits/$1/check-runs?check_name=IronBee%20review&filter=all&per_page=100" "$IRONBEE_TMP/check-runs.json")
  [ "$status" = 200 ] || fail 1 "GitHub did not list the checks on ${1:0:7} (HTTP $status)"
  ijq -s --arg slug "$IRONBEE_SLUG" 'include "ironbee"; [.[] | .check_runs[]? | select(ours_check($slug))] | sort_by(.id)' \
    "$IRONBEE_TMP/check-runs.json" > "$2"
}

# ours_reviews NUMBER HEAD OUT: the pull request's reviews of ours on the commit (our identity and our marker).
ours_reviews() {
  local status
  status=$(api --paginate GET "repos/$IRONBEE_REPO/pulls/$1/reviews?per_page=100" "$IRONBEE_TMP/reviews.json")
  case $status in
    200) ijq -s --arg login "$IRONBEE_LOGIN" --arg head "$2" 'include "ironbee"; [.[] | .[]? | select(ours_review($login; $head))]' \
           "$IRONBEE_TMP/reviews.json" > "$3" ;;
    404) echo '[]' > "$3" ;;                                     # no such pull request: no review of ours
    *) fail 1 "GitHub did not list the reviews of #$1 (HTTP $status)" ;;
  esac
}
