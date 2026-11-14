#!/usr/bin/env bash
# The neutral check of jobs 1 and 3, by the check's rule: written on a commit only when that commit holds no check of
# ours and the pull request no review of ours on it, so a neutral never covers a review's conclusion. After its write
# it looks again: when a review's conclusion of ours sits beside it on that commit (a review that ran meanwhile), the
# neutral becomes a copy of that conclusion, never one of its own.
#
#   GITHUB_REPOSITORY            the repository
#   GH_TOKEN                     the job's token, for the reads
#   IRONBEE_APP_SLUG             the customer's own App's slug, when the reviewer writes as that App
#   IRONBEE_APP_TOKEN            that App's installation token with checks: write, for the writes under the App
#   IRONBEE_HEAD                 the commit: the one the event named
#   IRONBEE_PULL_REQUEST         its pull request, whose reviews are read; none for a merge queue's group
#   IRONBEE_REASON               merge_group (a merge queue's group), no_secrets (a run given no secrets), not_run (the
#                                review did not run: the image, the container, a job killed or cancelled)
#   IRONBEE_CONCLUDING           the head the review job began to conclude a review on, when it said so before it
#                                stopped: that head gets no neutral, since a review of it may hold blocking findings
#                                with no review or check of ours there to show it
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
needs jq gh

repository
identity
head=${IRONBEE_HEAD:-}
pr=${IRONBEE_PULL_REQUEST:-}
is_sha "$head" || fail 2 "IRONBEE_HEAD names no commit"
[ -z "$pr" ] || is_number "$pr" || fail 2 "IRONBEE_PULL_REQUEST names no pull request"
if [ -n "${IRONBEE_APP_SLUG:-}" ]; then
  write_token=${IRONBEE_APP_TOKEN:-}
  [ -n "$write_token" ] || fail 2 "the customer's own App gave no token to write the check with"
else
  write_token=${GH_TOKEN:-}
fi

case ${IRONBEE_REASON:-} in
  merge_group)
    title="Reviewed on its pull requests"
    summary="A merge queue's group is not reviewed again: IronBee reviews each pull request on the pull request itself." ;;
  no_secrets)
    title="Not reviewed"
    summary="This run of the workflow lacked the \`ironbee-api-key\` or \`registry-token\` secret, so IronBee did not review it. GitHub gives a pull request Dependabot opens none of the repository's secrets unless Dependabot is given them." ;;
  not_run)
    title="Not reviewed"
    summary="The review did not run; the workflow's log says why. A re-run of the workflow, or \`$IRONBEE_MENTION review\`, reviews this head." ;;
  *) fail 2 "IRONBEE_REASON names no reason for a neutral check" ;;
esac
short=${head:0:7}

if [ "${IRONBEE_CONCLUDING:-}" = "$head" ]; then
  say "check: the review began to conclude on $short before it stopped: nothing written; a re-run of the workflow, or \`$IRONBEE_MENTION review\`, concludes it"
  exit 0
fi

ours_checks "$head" "$IRONBEE_TMP/ours.json"
if [ "$(jq length "$IRONBEE_TMP/ours.json")" != 0 ]; then
  say "check: $short holds a check of ours: left as it is"
  exit 0
fi
if [ -n "$pr" ]; then
  ours_reviews "$pr" "$head" "$IRONBEE_TMP/reviews-ours.json"
  if [ "$(jq length "$IRONBEE_TMP/reviews-ours.json")" != 0 ]; then
    say "check: #$pr holds a review of ours on $short: left as it is"
    exit 0
  fi
fi

jq -n --arg name "$IRONBEE_CHECK" --arg head "$head" --arg title "$title" --arg summary "$summary" \
  '{name: $name, head_sha: $head, status: "completed", conclusion: "neutral", output: {title: $title, summary: $summary}}' \
  > "$IRONBEE_TMP/create.json"
status=$(GH_TOKEN=$write_token api POST "repos/$IRONBEE_REPO/check-runs" "$IRONBEE_TMP/created.json" "$IRONBEE_TMP/create.json")
[ "$status" = 200 ] || fail 1 "GitHub refused the check on $short (HTTP $status)"
own=$(jq -r '.id // empty | tostring' "$IRONBEE_TMP/created.json")
is_number "$own" || fail 1 "GitHub's answer to the check on $short names no check"
say "check: neutral on $short ($title)"

# The second look: a review's conclusion of ours beside this neutral, written while it was being written.
ours_checks "$head" "$IRONBEE_TMP/again.json"
now=$(jq -r --argjson own "$own" '.[] | select(.id == $own) | .conclusion // ""' "$IRONBEE_TMP/again.json")
case $now in
  success | failure)
    say "check: ours on $short already says $now: a review rewrote it"
    exit 0 ;;
esac
jq --argjson own "$own" '[.[] | select(.id != $own and (.conclusion == "success" or .conclusion == "failure"))] | max_by(.id) // empty' \
  "$IRONBEE_TMP/again.json" > "$IRONBEE_TMP/review.json"
if [ ! -s "$IRONBEE_TMP/review.json" ]; then
  exit 0
fi
jq '{status: "completed", conclusion: .conclusion,
     output: {title: (.output.title // "" | if . == "" then "IronBee review" else . end),
              summary: (.output.summary // "" | if . == "" then "IronBee review" else . end)}}' \
  "$IRONBEE_TMP/review.json" > "$IRONBEE_TMP/copy.json"
conclusion=$(jq -r .conclusion "$IRONBEE_TMP/copy.json")
status=$(GH_TOKEN=$write_token api PATCH "repos/$IRONBEE_REPO/check-runs/$own" "$IRONBEE_TMP/copied.json" "$IRONBEE_TMP/copy.json")
[ "$status" = 200 ] || fail 1 "GitHub refused to rewrite the check on $short (HTTP $status)"
say "check: a review's conclusion of ours ($conclusion) was beside it on $short: copied"
