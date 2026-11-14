# The `Code Review Result` check

Each head commit of a pull request gets at most one check run named `Code Review Result`, written with the reviewer's
identity ([Identity](identity.md)). It is the merge gate: you can make it a required check. The workflow's own job,
`Job`, shows beside it as `<your workflow> / <your job> / Job`. With the [setup](setup.md)'s file a pull request
shows `IronBee / Code Review / Job`, and usually `IronBee / Code Review Result`: GitHub places a check the workflow's
token writes, and one your own GitHub App writes shows under the App's name. Require the check by its name alone,
`Code Review Result`. The job's result is green unless the run itself failed, and it is not the check to require.

**Its details link.** A review's conclusion links to the review the reviewer posted on that head (or the short review
below). Its text opens with that link ("The review on this commit"). Under your own GitHub App, GitHub's "Details",
and the "Resolve" an `action_required` shows, open the review too; with the workflow's token GitHub keeps them on the
check's own page, where the text's link is. A `neutral` written because nothing
was reviewed links to no review; one a retract turns from a conclusion keeps the link it had.

**The pre-releases' name.** The pre-releases (`v1.0.0-rc.1` to `-rc.3`) named the check `IronBee review`. A check of
that name written with the reviewer's identity is still read as the reviewer's, so a head that holds one gets no second
check: a later review rewrites it in place, under the new name. A branch rule that requires `IronBee review` (a
pre-release's, or IronBee's cloud product's, whose check keeps that name) must require `Code Review Result` instead:
switch the rule when the workflow file that calls this release reaches the default branch, not before. An open pull
request whose head shows only `IronBee review` then waits until `@ironbee-ai review` or a push rewrites it under the
new name; a re-run of its old run does not, since a re-run runs the release it ran before.

## How it concludes

| What the run did | The head has no `Code Review Result` of the reviewer's | It has one |
|---|---|---|
| **reviewed**: a review, or a command that ran one. On a head the last round already read, the review reads nothing again (or only what a partial round left unread) and concludes from the pull request's texts as they are now | created: `action_required` when findings at or above the team's `mergeBlock` level are open, else `success`; an `action_required` on a head that holds no review of the reviewer's gets a short one there first (below) | rewritten the same way, with the same short review first |
| **a pull request's event that reviewed nothing**: a gate, too large, a release merge already reviewed, refused by IronBee, IronBee unreachable, failed before its review was posted, or no secrets in the run | created: `neutral`, titled "Not reviewed", with the reason in one sentence, when the head is still the event's own and the pull request holds no review of the reviewer's on it. On a head pushed since, nothing: that head's own run decides | left as it is |
| **a `retract`** | nothing written | a review's conclusion becomes `neutral` ("Retracted"); a `neutral` is left as it is |
| **an answer**, or a command that asks for no review (a question, `pause`, `resume`) | nothing written | left as it is: the next review restates it (a push, or `@ironbee-ai review`) |
| **a comment's run that did nothing**: refused, unreachable, not addressed to the reviewer, failed | nothing written | left as it is |
| **failed after its review was posted** | nothing written: the job is red, and nothing writes `neutral` on a head that holds a review of the reviewer's. A re-run of the head's pull-request run, or `@ironbee-ai review`, concludes from the texts | left as it is until then |
| **failed after it began to conclude**: the check's own write failing included | nothing written: once a run begins concluding a head, it writes no `neutral` there, nor does the workflow's fallback step when it reads the run's output or finds a review of the reviewer's on that head. An `action_required` gets the short review first, so the head can be left with no check at all. Only a run killed in the few seconds before that review is posted can still leave a `neutral` there. A re-run of the head's pull-request run, or `@ironbee-ai review`, concludes from the texts | left as it is until then |
| **a merge queue group** (`merge_group`) | `neutral` on the group's commit: the review was made on the pull request | — |

So a conclusion is only ever a review's, on the head that review read. A comment's run can pass a head only by
reviewing it, and nothing but a later review of that head, or a retract, turns an `action_required` into anything weaker.

**The conclusions.** A review concludes `success`, or `action_required` while findings hold the merge, as IronBee's
cloud product does; like `failure`, `action_required` does not pass a required check. The
pre-releases `v1.0.0-rc.1` and `-rc.2` wrote `failure` for a blocking review: such a check is still read as a
review's conclusion, so a `neutral` never replaces it, a retract turns it `neutral`, and the next review rewrites it.

**The short review.** A run that reads nothing new on its head (the branch updated from its base, an empty commit)
posts no review there and restates the check from the texts. When that check is an `action_required` and the head holds no
review of the reviewer's, the reviewer first posts a short review on the head, with no inline comments, saying that
no new change was read there and how many findings stay open. With that review on the head, nothing writes `neutral`
there, even when the run is killed before its check: the check stays missing until a re-run or `@ironbee-ai review`.
A `success` gets no such review. It carries none of the reviewer's state: the next review reads what changed since
the last head a review read, and a retract takes it back with the rest.

**Which findings block.** Open findings whose severity is at or above the team's `mergeBlock` level (`never` blocks
nothing). A finding listed in the review's body instead of commented never blocks, nor does an unrated one, a fixed
one or a dropped one. The check's title gives the counts (for example `1 blocking · 3 open · 1 high · 2 medium`, or
`Nothing open`), and its text lists the blocking findings with links to their comments. Those texts are written to
GitHub, never to IronBee.

**When it follows a change of mind.** An answer that withdraws a finding is in the pull request's texts at once and
does not move the check by itself; `@ironbee-ai review` restates the check from the texts, with nothing read again. A
reply that turns a finding down ("won't fix") and a thread someone resolves are recorded by the next review that reads
the pull request again (a push, or `@ironbee-ai full review`).

In every review the check is written before the summary is made, whether the summary is on or off, so a run killed
while it summarizes has already concluded.

## Making it required

Add `Code Review Result` as a required status check in the branch's protection rule or ruleset.

- **`neutral` passes a required check.** A gate, a licence problem or a run that could not start never blocks a
  merge. An `action_required` an earlier review wrote stays until a later review of that head, a retract, or a push.
- **A run cancelled before its job started leaves no check.** A run cancelled while it waited for the pull request's
  queue (by hand, or by GitHub past 100 waiting runs), or one whose machine was lost, runs none of its steps, the
  fallback included: a required check then waits until a re-run, the next push or `@ironbee-ai review`.
- **Merge queue.** Keep the `merge_group` trigger in the workflow file: the group's commit then gets its `neutral`.
- **Pull requests from forks get no check:** GitHub gives a fork's pull-request run a read-only token and no secrets,
  so nothing can be written there. A repository that takes pull requests from forks cannot make the check required in
  this release.
- **Dependabot under your own App:** give Dependabot the App's id and key, or its pull requests get no check
  ([Identity](identity.md#dependabot)).
- **A pull request with a merge conflict:** GitHub runs no workflow on it, so a push onto it gets no review and no
  check until the conflict is gone.
- **A push that raises no workflow event** (one made with a workflow's own token, or whose commit asks to skip CI) gets
  no run of its own. A run already waiting reviews it, since a run reads the head when it starts; otherwise it has no
  review and no check until the next push or a command.
- **A check belongs to a commit.** A head reviewed in one pull request, or against one base, keeps its check in
  another; a change of the base raises no event the workflow listens to.

## What the check is worth

**What the check says, in IronBee's cloud product and here.** The check (`IronBee review` in the cloud, `Code Review
Result` here) reflects the findings that nobody who counts has turned down. The pull request's author, and anyone else who counts, can close a finding with a reply or a
thumbs-down; someone who may write to the repository can hide a comment, resolve a thread, `retract`, or `pause` and
then push. The check is a team's own discipline made visible, not a control over its members: a team that must hold
merges against its own developers requires a human approval beside it.

**What a self-hosted run adds to that.** The state the reviewer keeps lives in its comments, unsigned, so anyone with
write access can edit it; in the cloud product it is in IronBee's database. And anyone who can push a branch can
change the workflow file on that branch, since a pull request's and an inline reply's events run the branch's own
file, and so read the secrets the job is given; and can add a workflow of their own that writes a check run named
`Code Review Result`, or comments carrying the reviewer's state, as `github-actions[bot]`, which GitHub does not tell from
the reviewer's. That is GitHub's rule for every workflow secret and every check a workflow writes, not this
feature's.

Running the reviewer as your own GitHub App takes the check and the comments out of that shared identity; the App's
key is still a secret a branch's workflow can read. A setup whose check and secrets hold against people who can push
is not part of this release.
