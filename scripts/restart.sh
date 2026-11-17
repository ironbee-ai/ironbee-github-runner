#!/usr/bin/env bash
# The restart step of code-review-no-queue.yml, for a host whose Actions keep one waiting run of a pull request: a newer
# run replaces the one waiting, and a run cancelled while it waited runs none of its steps, so a review a reply or a
# command replaced would leave its head with no review and no check. A run of the pull request's group that handed on
# no review ends here, and starts that review again:
#
#   1. the pull request, read: a closed one, or one from a fork, ends the step;
#   2. a check or a review of ours on its head, by the neutral check's own test, ends the step;
#   3. the newest run of this workflow for a `pull_request` event on that head that was cancelled; none ends the step;
#   4. that run started again, when ours is its only job: a re-run starts every job of a run again.
#
#   GITHUB_EVENT_PATH, GITHUB_REPOSITORY, GITHUB_RUN_ID   as Actions gives them
#   GH_TOKEN                     the job's token: the reads, and the re-run, which needs actions: write
#   IRONBEE_APP_SLUG             the customer's own App's slug, when the reviewer writes as that App
#
# Exit 0: a review started again, or none to start; 1: a read or the re-run failed or was refused; 2: the configuration.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
needs jq gh

[ -r "${GITHUB_EVENT_PATH:-}" ] || fail 2 "GITHUB_EVENT_PATH: the event file cannot be read"
repository
identity
run=${GITHUB_RUN_ID:-}
is_number "$run" || fail 2 "GITHUB_RUN_ID names no run"
ACTIONS_WRITE="the calling workflow file must grant the job actions: write to start a review again"

end() {
  say "restart: $*; nothing started again"
  exit 0
}

# said: what GitHub answered the last call that failed, in gh's words, on one line.
said() {
  tail -n 1 "$IRONBEE_TMP/gh.err" 2> /dev/null | sed 's/^gh: //; s/ (HTTP [0-9]*)$//' | cut -c1-200
}

pr=$(jq -r '(.pull_request.number // .issue.number) // empty | tostring' "$GITHUB_EVENT_PATH")
is_number "$pr" || end "the event names no pull request"
status=$(api GET "repos/$IRONBEE_REPO/pulls/$pr" "$IRONBEE_TMP/pull.json")
case $status in
  200) ;;
  404) end "#$pr is no pull request" ;;
  *) fail 1 "GitHub could not give #$pr (HTTP $status)" ;;
esac
[ "$(jq -r '.state // ""' "$IRONBEE_TMP/pull.json")" = open ] || end "#$pr is closed"
if [ "$(ijq -r 'include "ironbee"; forked' "$IRONBEE_TMP/pull.json")" = true ]; then
  end "#$pr comes from a fork"
fi
head=$(jq -r '.head.sha // empty' "$IRONBEE_TMP/pull.json")
is_sha "$head" || fail 1 "GitHub's #$pr names no head"
short=${head:0:7}

ours_checks "$head" "$IRONBEE_TMP/ours.json"
[ "$(jq length "$IRONBEE_TMP/ours.json")" = 0 ] || end "$short holds a check of ours"
ours_reviews "$pr" "$head" "$IRONBEE_TMP/reviews-ours.json"
[ "$(jq length "$IRONBEE_TMP/reviews-ours.json")" = 0 ] || end "#$pr holds a review of ours on $short"

# This run's workflow: the calling repository's file, whose runs are listed by its id.
status=$(api GET "repos/$IRONBEE_REPO/actions/runs/$run" "$IRONBEE_TMP/run.json")
case $status in
  200) ;;
  403) fail 1 "GitHub refused to give this run (HTTP 403: $(said)): $ACTIONS_WRITE" ;;
  *) fail 1 "GitHub could not give this run (HTTP $status)" ;;
esac
workflow=$(jq -r '.workflow_id // empty | tostring' "$IRONBEE_TMP/run.json")
is_number "$workflow" || fail 1 "GitHub's answer for this run names no workflow"

status=$(api GET "repos/$IRONBEE_REPO/actions/workflows/$workflow/runs?event=pull_request&head_sha=$head&status=cancelled&per_page=100" "$IRONBEE_TMP/runs.json")
[ "$status" = 200 ] || fail 1 "GitHub did not list this workflow's runs on $short (HTTP $status)"
cancelled=$(jq -r --arg head "$head" '[.workflow_runs[]? | select(.event == "pull_request" and .head_sha == $head and .conclusion == "cancelled")]
  | max_by(.id) | .id // empty | tostring' "$IRONBEE_TMP/runs.json")
is_number "$cancelled" || end "no review of $short was cancelled"

status=$(api --paginate GET "repos/$IRONBEE_REPO/actions/runs/$cancelled/jobs?per_page=100" "$IRONBEE_TMP/jobs.json")
[ "$status" = 200 ] || fail 1 "GitHub did not list the jobs of run $cancelled (HTTP $status)"
jobs=$(jq -s '[.[] | .jobs[]?] | length' "$IRONBEE_TMP/jobs.json")
if [ "$jobs" -gt 1 ]; then
  end "run $cancelled, the review of $short a newer run replaced while it waited, holds $jobs jobs, and a re-run would start every one of them again; a re-run of it by hand, or \`$IRONBEE_MENTION review\`, reviews $short"
fi

status=$(api POST "repos/$IRONBEE_REPO/actions/runs/$cancelled/rerun" "$IRONBEE_TMP/rerun.json")
case $status in
  200) say "restart: run $cancelled, the review of $short a newer run replaced while it waited, started again" ;;
  403) fail 1 "GitHub refused to start run $cancelled again (HTTP 403: $(said)): $ACTIONS_WRITE" ;;
  *) fail 1 "GitHub did not start run $cancelled again (HTTP $status: $(said))" ;;
esac
