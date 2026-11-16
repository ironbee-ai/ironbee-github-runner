#!/usr/bin/env bash
# Makes .github/workflows/code-review-no-queue.yml from .github/workflows/code-review.yml: the reusable workflow for a
# host whose Actions know no concurrency queue (GitHub Enterprise Server), never edited by hand. The two differ in this
# alone: its header; no `queue: max`, so a pull request's group keeps one waiting run, which a newer one replaces; the
# group takes a conversation comment only when it names the reviewer, by the name the decide step reads; and a last
# step (restart.sh) that starts again a review a newer run replaced while it waited.
#
#   scripts/build-no-queue.sh [--check] [SOURCE TARGET]   from the repository's root
#
# --check writes nothing: whether TARGET is what this makes from SOURCE. Exit 0: written, or up to date; 1: not up to
# date; 2: the usage, or a SOURCE this cannot turn into TARGET exactly, rather than a guess.
set -euo pipefail
# shellcheck source=scripts/lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage="usage: build-no-queue.sh [--check] [SOURCE TARGET]"
check=false
if [ "${1:-}" = --check ]; then
  check=true
  shift
fi
case $# in
  0) source=.github/workflows/code-review.yml target=.github/workflows/code-review-no-queue.yml ;;
  2) source=$1 target=$2 ;;
  *) fail 2 "$usage" ;;
esac
[ -f "$source" ] || fail 2 "$source is not a file"

header() {
  cat << 'EOF'
# Generated from code-review.yml by scripts/build-no-queue.sh: do not edit; run `bash scripts/build-no-queue.sh` after
# changing code-review.yml. The same workflow for a host whose Actions know no concurrency queue (every GitHub
# Enterprise Server today): a pull request's group keeps one waiting run, which a newer run replaces; the group takes a
# conversation comment only when it names the reviewer; and the last step starts again a review that a newer run
# replaced while it waited, so the caller grants the job actions: write.
#
EOF
}

# The job's concurrency in SOURCE, with the comment above it, as it stands there.
queued() {
  cat << 'EOF'
    # One run of a pull request at a time, for the events that may run the reviewer: a pull request's event, a person's
    # reply on a review thread, a person's conversation comment that mentions someone. A started run is never cancelled,
    # and every waiting run is kept. Every other event (a bot's comment, ours included, a thread's first comment, a
    # comment that mentions nobody, a merge queue's group, a push, a manual start) has a group of its own: it never waits.
    concurrency:
      group: >-
        ${{
          (github.event_name == 'pull_request' ||
           (github.event_name == 'pull_request_review_comment' && github.event.comment.in_reply_to_id &&
            github.event.comment.user.type != 'Bot' && github.event.sender.type != 'Bot') ||
           (github.event_name == 'issue_comment' && contains(github.event.comment.body, '@') &&
            github.event.comment.user.type != 'Bot' && github.event.sender.type != 'Bot'))
          && format('ironbee-review-{0}', github.event.pull_request.number || github.event.issue.number)
          || format('ironbee-{0}', github.run_id)
        }}
      cancel-in-progress: false
      queue: max
EOF
}

# What takes its place. The name is the decide step's: the app-slug input with an `@` before it, or @ironbee-ai.
one_waiting() {
  cat << 'EOF'
    # One run of a pull request at a time, for the events that may run the reviewer: a pull request's event, a person's
    # reply on a review thread, a person's conversation comment that names the reviewer. A started run is never
    # cancelled; one run waits, a newer one replaces it, and the restart step starts a review so replaced again. Every
    # other event (a bot's comment, ours included, a thread's first comment, a comment that names someone else or
    # nobody, a merge queue's group, a push, a manual start) has a group of its own: it never waits.
    concurrency:
      group: >-
        ${{
          (github.event_name == 'pull_request' ||
           (github.event_name == 'pull_request_review_comment' && github.event.comment.in_reply_to_id &&
            github.event.comment.user.type != 'Bot' && github.event.sender.type != 'Bot') ||
           (github.event_name == 'issue_comment' &&
            contains(github.event.comment.body,
                     inputs.app-slug != '' && (startsWith(inputs.app-slug, '@') && inputs.app-slug || format('@{0}', inputs.app-slug)) || '@ironbee-ai') &&
            github.event.comment.user.type != 'Bot' && github.event.sender.type != 'Bot'))
          && format('ironbee-review-{0}', github.event.pull_request.number || github.event.issue.number)
          || format('ironbee-{0}', github.run_id)
        }}
      cancel-in-progress: false
EOF
}

# The last step, for a run of the pull request's group (the group's own test) that handed on no review.
restart() {
  cat << 'EOF'

      # A run of the pull request's group that handed on no review may have replaced a waiting review, which then ran
      # no step: that review is started again, whatever the steps before this one did.
      - name: Start a replaced review again
        id: restart
        if: >-
          always() && steps.scripts.outcome == 'success' && steps.decide.outputs.action != 'review' &&
          (github.event_name == 'pull_request' ||
           (github.event_name == 'pull_request_review_comment' && github.event.comment.in_reply_to_id &&
            github.event.comment.user.type != 'Bot' && github.event.sender.type != 'Bot') ||
           (github.event_name == 'issue_comment' &&
            contains(github.event.comment.body,
                     inputs.app-slug != '' && (startsWith(inputs.app-slug, '@') && inputs.app-slug || format('@{0}', inputs.app-slug)) || '@ironbee-ai') &&
            github.event.comment.user.type != 'Bot' && github.event.sender.type != 'Bot'))
        timeout-minutes: 10
        shell: bash
        run: bash .ironbee-github-runner/scripts/restart.sh
        env:
          GH_TOKEN: ${{ github.token }}
          IRONBEE_APP_SLUG: ${{ inputs.app-slug }}
EOF
}

# lines_of FUNCTION: the function's text, one line an element of `got`.
lines_of() {
  local line
  got=()
  while IFS= read -r line || [ -n "$line" ]; do
    got+=("$line")
  done < <("$1")
}

lines=()
while IFS= read -r line || [ -n "$line" ]; do
  lines+=("$line")
done < "$source"
lines_of queued
want=("${got[@]}")

at=""
for i in "${!lines[@]}"; do
  if [ "${lines[$i]}" = "${want[0]}" ]; then
    [ -z "$at" ] || fail 2 "$source holds the concurrency's first comment line twice"
    at=$i
  fi
done
[ -n "$at" ] || fail 2 "$source's job holds no concurrency this replaces: scripts/build-no-queue.sh names the one it replaces"
for k in "${!want[@]}"; do
  if [ "${lines[$((at + k))]:-}" != "${want[$k]}" ]; then
    fail 2 "$source line $((at + k + 1)) is not the concurrency this replaces: update scripts/build-no-queue.sh with the new one"
  fi
done
last=$((${#lines[@]} - 1))
[[ ${lines[$last]} == '        '* ]] || fail 2 "$source does not end with the job's steps, after which the restart step goes"

made=$IRONBEE_TMP/made.yml
{
  header
  for ((i = 0; i < at; i++)); do
    printf '%s\n' "${lines[$i]}"
  done
  one_waiting
  for ((i = at + ${#want[@]}; i <= last; i++)); do
    printf '%s\n' "${lines[$i]}"
  done
  restart
} > "$made"
if grep -Eq '^[[:space:]]+queue:' "$made"; then
  fail 2 "$source names a concurrency queue outside the job's concurrency this replaces"
fi

if [ "$check" = true ]; then
  if [ ! -f "$target" ] || ! cmp -s "$made" "$target"; then
    fail 1 "$target is not what scripts/build-no-queue.sh makes from $source: run \`bash scripts/build-no-queue.sh\` and commit the result"
  fi
  say "$target is up to date"
  exit 0
fi
cat "$made" > "$target"
say "wrote $target"
