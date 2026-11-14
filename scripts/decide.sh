#!/usr/bin/env bash
# Job 1: what a pull request's event asks of the reviewer, decided before any image is pulled and outside the pull
# request's queue. It ends what can never run or may not be asked: a fork's event, a bot's comment, a run without the
# secrets, a comment not addressed to us, a question on a thread that is not ours or from someone who does not count, a
# command from someone who may not write. A merge queue's group, and a pull request's run without the secrets, get a
# neutral check instead where there is a key to write it with (neutral.sh writes it).
#
#   GITHUB_EVENT_NAME, GITHUB_EVENT_PATH, GITHUB_REPOSITORY   the event, as GitHub hands it to the job
#   GH_TOKEN                     the job's token, for the reads: a thread's first comment, a pull request, a permission
#   IRONBEE_APP_SLUG             the customer's own App's slug, when the reviewer writes as that App
#   IRONBEE_HAS_API_KEY, IRONBEE_HAS_REGISTRY_TOKEN, IRONBEE_HAS_APP_ID, IRONBEE_HAS_APP_PRIVATE_KEY
#                                whether each secret is set: true or false. A run has its secrets when the API key and the
#                                registry token are both set; without them the image could not be pulled or start.
#
# GITHUB_OUTPUT gets, for job 2: action (review, answer, respond, retract), pull-request, comment-id, and for job 3 the
# head a pull request's event names; for neutral.sh: write (merge_group, no_secrets), write-head, write-pull-request.
# Nothing at all: the run ends here. Exit 1: a read that failed; 2: the workflow's configuration.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
needs jq gh

event=${GITHUB_EVENT_NAME:-}
[ -r "${GITHUB_EVENT_PATH:-}" ] || fail 2 "GITHUB_EVENT_PATH: the event file cannot be read"
[ -n "${GITHUB_OUTPUT:-}" ] || fail 2 "GITHUB_OUTPUT is not set"
repository
identity

secrets=false
if [ "${IRONBEE_HAS_API_KEY:-}" = true ] && [ "${IRONBEE_HAS_REGISTRY_TOKEN:-}" = true ]; then
  secrets=true
fi

# The App's key is the secrets' to give: a run without them has none to write with, unless they give it the App's.
app_key=true
if [ -n "${IRONBEE_APP_SLUG:-}" ]; then
  if [ "${IRONBEE_HAS_APP_ID:-}" != true ] || [ "${IRONBEE_HAS_APP_PRIVATE_KEY:-}" != true ]; then
    app_key=false
    if [ "$secrets" = true ]; then
      fail 2 "app-slug is given without app-id and app-private-key: the customer's own App needs all three"
    fi
  fi
elif [ "${IRONBEE_HAS_APP_ID:-}" = true ] || [ "${IRONBEE_HAS_APP_PRIVATE_KEY:-}" = true ]; then
  fail 2 "app-id and app-private-key are given without app-slug: the customer's own App needs all three"
fi

ev() {
  local filter=$1
  shift
  ijq -r "$@" "include \"ironbee\"; $filter" "$GITHUB_EVENT_PATH"
}

output() {
  printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"
}

end() {
  say "IronBee: $*; nothing to do"
  exit 0
}

# number FILTER: a whole number of the event as text, empty when it holds none.
number() {
  ev "$1 // empty | tostring"
}

case $event in
  merge_group)
    head=$(ev '.merge_group.head_sha // empty')
    is_sha "$head" || end "the merge group names no commit"
    if [ "$app_key" != true ]; then
      end "no App key in this run, so the group's commit gets no check"
    fi
    say "IronBee: a merge queue's group: neutral on ${head:0:7}"
    output write merge_group
    output write-head "$head"
    ;;

  pull_request)
    act=$(ev '.action // ""')
    case $act in
      opened | synchronize | reopened | ready_for_review) ;;
      *) end "a pull request's $act starts no review" ;;
    esac
    pr=$(number .pull_request.number)
    is_number "$pr" || end "the event names no pull request"
    head=$(ev '.pull_request.head.sha // empty')
    is_sha "$head" || end "the pull request names no head"
    if [ "$(ev '.pull_request | forked')" = true ]; then
      end "#$pr comes from a fork, which is not reviewed"
    fi
    if [ "$secrets" != true ]; then
      if [ "$app_key" != true ]; then
        end "#$pr's run was given no secrets, and without the App's key no check can be written"
      fi
      say "IronBee: #$pr's run was given no secrets: neutral on ${head:0:7}"
      output write no_secrets
      output write-head "$head"
      output write-pull-request "$pr"
      exit 0
    fi
    say "IronBee: #$pr $act: review ${head:0:7}"
    output action review
    output pull-request "$pr"
    output head "$head"
    ;;

  pull_request_review_comment)
    [ "$(ev '.action // ""')" = created ] || end "only a new comment asks anything"
    if [ "$(ev 'bot_comment($login)' --arg login "$IRONBEE_LOGIN")" = true ]; then
      end "a bot wrote the comment"
    fi
    pr=$(number .pull_request.number)
    comment=$(number .comment.id)
    is_number "$pr" && is_number "$comment" || end "the event names no pull request and comment"
    if [ "$(ev '.pull_request | forked')" = true ]; then
      end "#$pr comes from a fork, where nothing is answered"
    fi
    [ "$secrets" = true ] || end "the run was given no secrets"
    root=$(number .comment.in_reply_to_id)
    is_number "$root" || end "comment $comment opens a thread, and asks nothing of us"
    if [ "$(ev 'counts')" != true ]; then
      end "comment $comment is from someone whose word does not count on our threads"
    fi
    status=$(api GET "repos/$IRONBEE_REPO/pulls/comments/$root" "$IRONBEE_TMP/root.json")
    case $status in
      200) ;;
      404) end "the first comment of comment $comment's thread is gone" ;;
      *) fail 1 "GitHub could not give the first comment of comment $comment's thread (HTTP $status)" ;;
    esac
    if [ "$(ijq -r --arg login "$IRONBEE_LOGIN" 'include "ironbee"; ours_post($login)' "$IRONBEE_TMP/root.json")" != true ]; then
      end "comment $comment is on a thread that is not ours"
    fi
    say "IronBee: comment $comment on #$pr: answer"
    output action answer
    output pull-request "$pr"
    output comment-id "$comment"
    ;;

  issue_comment)
    [ "$(ev '.action // ""')" = created ] || end "only a new comment asks anything"
    [ "$(ev '.issue.pull_request != null')" = true ] || end "the comment is on an issue, not on a pull request"
    if [ "$(ev 'bot_comment($login)' --arg login "$IRONBEE_LOGIN")" = true ]; then
      end "a bot wrote the comment"
    fi
    pr=$(number .issue.number)
    comment=$(number .comment.id)
    is_number "$pr" && is_number "$comment" || end "the event names no pull request and comment"
    [ "$secrets" = true ] || end "the run was given no secrets"
    if [ "$(ev '.comment.body // "" | addressed([$name])' --arg name "$IRONBEE_MENTION")" != true ]; then
      end "comment $comment does not address $IRONBEE_MENTION"
    fi
    status=$(api GET "repos/$IRONBEE_REPO/pulls/$pr" "$IRONBEE_TMP/pull.json")
    case $status in
      200) ;;
      404) end "#$pr is gone" ;;
      *) fail 1 "GitHub could not give #$pr (HTTP $status)" ;;
    esac
    if [ "$(ijq -r 'include "ironbee"; forked' "$IRONBEE_TMP/pull.json")" = true ]; then
      end "#$pr comes from a fork, where no command is obeyed"
    fi
    # A login is letters, digits and `-`; an Enterprise Managed User's adds `_` and its enterprise's short code.
    login=$(ev '.comment.user.login // ""')
    case $login in '' | *[!A-Za-z0-9_-]*) end "comment $comment names no author GitHub can be asked about" ;; esac
    status=$(api GET "repos/$IRONBEE_REPO/collaborators/$login/permission" "$IRONBEE_TMP/permission.json")
    case $status in
      200) ;;
      404) end "$login may not write to the repository" ;;
      *) fail 1 "GitHub could not say what $login may do in $IRONBEE_REPO (HTTP $status)" ;;
    esac
    if [ "$(ijq -r 'include "ironbee"; .permission | writer' "$IRONBEE_TMP/permission.json")" != true ]; then
      end "$login may not write to the repository"
    fi
    action=respond
    if [ "$(ev '.comment.body // "" | asks_retract([$name])' --arg name "$IRONBEE_MENTION")" = true ]; then
      action=retract
    fi
    say "IronBee: comment $comment on #$pr: $action"
    output action "$action"
    output pull-request "$pr"
    output comment-id "$comment"
    ;;

  *)
    end "a $event event is no pull request's"
    ;;
esac
