# Troubleshooting

Where to look first:

- **The `IronBee review` check.** When a pull request's event reviewed nothing, its head gets a `neutral` check titled
  "Not reviewed", with the reason in one sentence. It is written only on a head that has no check and no review of the
  reviewer's yet, so a conclusion already there is never replaced by it. A run that failed after it began to conclude
  a review, its check's write included, leaves no `neutral` either, so its head can have no check at all: a re-run of
  the workflow, or `@ironbee-ai review`, concludes it. A head that shows only a short review saying that no new change
  was read there ([The short review](required-check.md#how-it-concludes)) is such a head: its findings hold the merge.
- **The workflow job's log.** The runner's lines say what it read and decided; a problem starts with `error:`,
  `warning:`, `failed:` or `IronBee`. The runner exits with 0 when the run ended, whatever it found; 1 when it failed;
  2 for a usage or configuration error. A `neutral` check passes a required check, so nothing below holds a merge
  unless it says so.

A healthy review's log reads like this:

```
pull request acme/shop#412 at 9f2c4e1 (pull_request, new_commits)
size M (870 reviewable lines in 14 files): a standard review
profile ironbee-self-hosted-standard, classifier llm
check: success on 9f2c4e1
```

In the sentences below, `@ironbee-ai` is your App's slug under your own App.

## IronBee refused the run, or could not be reached

The log says `IronBee refused the run (<code>): <sentence>`, or `IronBee: no answer after 3 attempts (<why>)`.
Nothing is reviewed. A pull request's event leaves the sentence as its `neutral` check; a comment's run writes
nothing.

| `neutral` check | Code | What to do |
|---|---|---|
| IronBee's self-hosted review is not enabled for this account; contact IronBee. | `SELF_HOSTED_RUNNER_NOT_ENABLED` | contact IronBee |
| IronBee's reviews are suspended for this account; contact IronBee. | `SELF_HOSTED_RUNNER_SUSPENDED` | contact IronBee ([The licence](licence.md#suspension)) |
| The licence for IronBee's self-hosted review has ended; contact IronBee to renew it. | `SELF_HOSTED_RUNNER_LICENCE_ENDED` | renew the licence; IronBee moves the end date, and the next event is reviewed ([The licence](licence.md)) |
| This version of the IronBee runner is no longer served; move the workflow to `<version>`. | `RUNNER_VERSION_UNSUPPORTED` | move the workflow to that version ([Versions](versions.md)). A release stopped at once adds ` Reason: <reason>` |
| IronBee's cloud reviews this repository; turn its code review off in the console before the runner reviews it. | `REPOSITORY_REVIEWED_BY_CLOUD` | turn the repository's code review off in the console, or remove the workflow |
| Missing or invalid credentials | `UNAUTHORIZED` | the `ironbee-api-key` secret is wrong, or a rotated key past its grace period. A code the runner does not know is shown with IronBee's own text, as here |
| IronBee could not be reached, so this pull request was not reviewed. | — | the job is red. Check that the job can reach IronBee's API (`api.service.ironbee.ai`, or the address in `ironbee-api-url`), then re-run the workflow |

An `action_required` an earlier review wrote stays on its head: a refused run never weakens it.

## The `neutral` check names a setting or the pull request

| `neutral` check | Why | What to do |
|---|---|---|
| Automatic reviews are off for this repository: a pull request is reviewed when someone asks `@ironbee-ai review`. | `autoReview: asked` | ask for a review, or change the setting |
| This repository's pull requests are reviewed when they are opened, not on every push. `@ironbee-ai review` reviews this head. | `autoReview: open` | as it says |
| The pull request is a draft: it is reviewed once it is ready for review. | `reviewDrafts` off | mark it ready for review |
| A bot opened this pull request, and this repository's settings leave such pull requests unreviewed. | `reviewBotPullRequests` off | turn the setting on to review them |
| The pull request's target branch is none of the branches this repository's reviews are for. | `targetBranches` | the console's setting, or the `target-branches` input for a repository without a project |
| A label of the pull request says not to review it. | `skipLabels` | as it says |
| The pull request's title says not to review it. | `skipTitleKeywords` | as it says |
| Automatic reviews of this pull request are paused: `@ironbee-ai resume` resumes them, `@ironbee-ai review` reviews this head. | someone wrote `@ironbee-ai pause` | as it says |
| This pull request changes … files (+… −… lines). IronBee reviews pull requests of up to … files and … changed lines, so it read nothing here. Split the change into smaller pull requests to have them reviewed. | too large, by the pull request's own counts | split the change |
| This pull request merges changes that were already reviewed in their own pull requests (#…), each at the head it was merged from. Nothing in it is new to review, so no review was run. | a release merge whose every commit came through a reviewed pull request | nothing |
| A newer release of the IronBee runner wrote this pull request's state: move the workflow to that release or a later one to review it. | the workflow was moved back across a change of the state's format | move the workflow's version forward ([Versions](versions.md)) |
| The workflow's configuration keeps the review from running (`<input>`); the workflow's log says what to change. | a configuration error ([below](#configuration-errors)) | fix the input the log names |
| The review did not run to its end; the workflow's log says why. A re-run of the workflow, or `@ironbee-ai review`, reviews this head. | the run failed before its review was posted | read the log's `failed:` line ([below](#the-run-failed)) |

A review someone asks for by a command passes every gate but the one for forks.

## The workflow's other steps wrote the check

The workflow is one job, `Review`; besides the runner, two of its steps write a `neutral` check.

- **"The review did not run; the workflow's log says why. A re-run of the workflow, or `@ironbee-ai review`, reviews
  this head."**, from the fallback step: the review step did not succeed and could not say why itself. The image
  could not be pulled (the registry down, a wrong or deleted `registry-token`), its container did not start, or the
  step was cancelled or timed out (the review step stops after two hours). Check the job's log and the
  `registry-token` secret, then re-run the workflow.
- **"This run of the workflow lacked the `ironbee-api-key` or `registry-token` secret, so IronBee did not review it.
  GitHub gives a pull request Dependabot opens none of the repository's secrets unless Dependabot is given them."**,
  from the decide step: a pull request whose
  workflow runs without the repository's secrets, such as Dependabot's ([Identity](identity.md#dependabot)), or whose
  workflow file passes no `ironbee-api-key` or no `registry-token` (below).
- **"Reviewed on its pull requests"**, on a merge queue group's commit: the group is not reviewed again, since each
  pull request was reviewed on the pull request itself.

### The `ironbee-api-key` or `registry-token` secret is not given

The decide step knows only whether the API key and the registry token are set, and a run without either one is a run
given no secrets: without the key the runner could not start, and without the token its image could not be pulled.
The runner never starts:

- on a pull request, the decide step writes the `neutral` above ("This run of the workflow lacked the `ironbee-api-key`
  or `registry-token` secret…"); under your own App it writes it only when the App's id and key are given, and otherwise
  nothing;
- on a comment, the run ends with `the run was given no secrets`, and nothing is written.

Check that the workflow file passes both `ironbee-api-key` and `registry-token`, and that the secrets they name
exist. The register step pulls no image and needs only the API key; without it, it says
`ironbee-api-key: no API key was given (IRONBEE_API_KEY)`.

### Your own App's three inputs

`app-id`, `app-private-key` and `app-slug` go together. The workflow's decide step checks them before anything else,
and writes no check:

- **`app-slug` without `app-id` or without `app-private-key`:** in a run that has its secrets, the job fails with
  `app-slug is given without app-id and app-private-key: the customer's own App needs all three`. A run without its
  secrets, such as a Dependabot pull request's, has no App key to write a check with and ends quietly, with no check.
- **`app-id` or `app-private-key` without `app-slug`:** the job fails in any run, with
  `app-id and app-private-key are given without app-slug: the customer's own App needs all three`.

## Configuration errors

The log says `error: <input>: <why>`, nothing is read, a pull request's event leaves the configuration `neutral` above,
and the runner exits with 2. The causes:

| Input | Why |
|---|---|
| `model-key` | no key without `model-url`: a provider's own endpoint needs one |
| `model-name` | `openai` with `model-url` and no `model-name`; or a name that is not 1 to 200 letters, digits and `. _ : / @ -` |
| `model-headers` | a line that is neither blank nor a header's `name=value` (the error names the line's number, never its text) |
| `model-ca-certificate` | no certificate in it |
| `model-provider` | not `anthropic`, `bedrock` or `openai` |
| `aws-region` | missing on `bedrock`, or not a region's name |
| `model-max-output` | not a whole number of 1 or more |
| `app-slug` | not the App's: `app-slug acme-review is not this App's: the key is the App acme-reviewer's` |
| `ironbee-run-reports` | neither `true` nor `false`, in any case; empty is `true` |
| `self-check` | the reviewer's own check of the run's settings failed before anything was cloned; the line names the reason, such as a model your provider cannot serve |

A missing `ironbee-api-key` or `registry-token`, and your own App's inputs given without the others, are caught before
the runner starts ([the secrets](#the-ironbee-api-key-or-registry-token-secret-is-not-given),
[your own App's inputs](#your-own-apps-three-inputs)).

## The run failed

The log says `failed: <code>: …`, the job is red, and the run reports the code to IronBee.

| Code | What happened | What to do |
|---|---|---|
| `model_unreachable` | the model's endpoint could not be reached, or gave no answer | check `model-url`, the network between the job and the endpoint, `model-ca-certificate` for an endpoint a private authority signed, and `runs-on` for a model inside your network ([Setup](setup.md#where-the-job-runs)) |
| `model_refused` | the endpoint answered no: a wrong key, a missing header, a model it does not serve | check `model-key`, `model-headers` and the model's name; an output budget the model refuses is lowered with `model-max-output` ([Models](models.md#what-a-model-must-support)) |
| `host_refused` | GitHub refused a write: the token may not write | check the workflow file's `permissions`; under your own App, its permissions and that it is installed on the repository |
| `clone_failed` | the repository could not be cloned | re-run; check the token's `contents: read` |
| `timeout` | the run ran out of time | re-run; the [review file](review-file.md)'s timeouts and `models.max_concurrency` |
| `reviewer_failed` | anything else | the log's traceback; re-run |

**Some model calls failed** but not all: the review is posted as a partial review that names the hunks it left
unread. A model with a small context or output limit fails calls this way: lower `model-max-output`, or make a reading
call smaller with `reader.chunk.block_lines` in the [review file](review-file.md).

**A classifier call failed or could not be read:** each stage that asked falls back as it does when Jev is
unavailable; the review goes on.

**The job failed after its review was posted.** The check follows the review at once, so a run killed while it
summarizes has already concluded. A run killed between its review and its check leaves the head as it was, and
nothing writes `neutral` over a head that holds a review of the reviewer's: a re-run of the pull request's run, or
`@ironbee-ai review`, concludes from the texts. A run that read nothing new on its head posts no review of its own
there; when its check is an `action_required`, it posts the short review first
([The short review](required-check.md#how-it-concludes)), so the same holds for it. A follow-up killed after its
replies and before its review counts as a round that did not run: the replies stay, the workflow's fallback step
writes `neutral`, and the next run reads them and goes on.

**A pull request's head with no check at all.** A run cancelled before its job started runs none of its steps, the
fallback's included: one cancelled by hand while it waited for the pull request's queue, or by GitHub when more than
100 runs of the pull request were waiting, and a job whose machine was lost. Its head gets no `IronBee review`, and a
required check waits for it: re-run the workflow, or ask `@ironbee-ai review`.

## Warnings in the log

| Line | What to do |
|---|---|
| `warning: this account has more developers this month than its licence covers; reviews go on, and IronBee will be in touch` | nothing: reviews go on ([The licence](licence.md#the-developer-limit)) |
| `warning: the licence for IronBee's self-hosted review ends soon; renew it to keep pull requests reviewed` | renew the licence |
| `warning: runner <version> is served until <day>; move the workflow to <version> before then` | move the workflow before that day ([Versions](versions.md)) |
| `IronBee: dropped <what>: <why>`, `settings: dropped <key>: <why>; the layers under it stand` | nothing: IronBee's answer carried a setting or a value this release does not know, which it leaves out; the review goes on with the value under it. A later release knows it |
| `warning: the rules repository <owner/name> could not be read (…): <why>; the review goes on without it` | check `knowledge-repository`, `knowledge-ref` and `knowledge-token`, or that your App is installed there ([Settings and rules](settings-and-rules.md#the-rules-repository)) |
| `warning: review file: .ironbee/review.yaml in <place> …left out…` | fix the entry the line names ([The review file](review-file.md#what-is-not-applied)) |
| `IronBee: the complete did not land: <why>`, `IronBee refused the complete (<code>): <why>`, `the complete did not land: the run stands as it ended` | nothing: the run stands as it ended. A review's author is still counted ([The licence](licence.md#the-developer-limit)) |

## No run, no review, or no check

- **A comment that is not for the reviewer, a bot's comment, a comment from someone whose words the rules do not
  hear, and anything on a fork's pull request** end in the workflow's decide step: no image is pulled and nothing is
  written. A bot's comment, a review thread's first comment and a conversation comment with no `@` in it take no
  place in the pull request's queue; a person's comment that mentions someone else, and a person's reply on a thread
  that is not the reviewer's, wait for the run before them like any other, then end there. A command counts only from someone who may write to the
  repository; a question on a thread only from the pull request's author and the repository's owners, members and
  collaborators. Under the job token, `@github-actions` is never a command.
- **Words addressed to the reviewer that its own rules turn away** write nothing; the run reports `not_addressed`.
- **`<author> may not write to <owner/name>: the respond is not run, nothing written`**: a command from someone without
  write permission.
- **A pull request from a fork** is not reviewed and gets no check. **A pull request with a merge conflict** gets no
  run until the conflict is gone. **A push made with a workflow's own token, or whose commit asks to skip CI,** gets no
  run of its own ([What running in GitHub Actions changes](differences-from-cloud.md#what-running-in-github-actions-changes)).
- **A push or a comment during a run** waits for it: one run per pull request at a time. The running one is pinned to
  its head and finishes there. The run that starts next reviews the newest head, and a later one for that same head
  finds nothing new.
- **`check: none written; the pull request moved from <head> to <head>, whose own run decides`**: the pull request was
  pushed while this run waited; the newer head's own run writes its check.
- **`@ironbee-ai full review` written while another run of the pull request runs or waits** may be answered by that
  run's review, which read less. Ask again.

## A rule, a reply or a resolve did not take effect

- **A rule from the rules repository did not apply:** the review's body says when the shared rules could not be read.
- **A rule from the repository's own `.ironbee/` files did not apply:** they are read at the pull request's base, and
  only while `repositoryKnowledge` is on.
- **The review file did not apply:** it is read at the pull request's base, never its head; the review's body says when
  a part of it was left out.
- **A thread was not resolved:** resolving needs `contents: write` ([Setup](setup.md#resolving-threads)).
- **A "won't fix", or a thread resolved by hand, did not change the check:** it is recorded by the next review that
  reads the pull request again (a push, or `@ironbee-ai full review`).
- **Someone edited or deleted one of the reviewer's comments:** the state it carried goes with it, and the next round
  reads what is left.

## The register step failed

The step fails with the reason when IronBee refuses the registration (the feature off, suspended, the licence ended, a
wrong key, a version no longer served) or cannot be reached, and nothing else changes. The log says
`IronBee refused the registration (<code>): <sentence>` or `IronBee: no answer after 3 attempts (<why>)`; with no API
key given, `ironbee-api-key: no API key was given (IRONBEE_API_KEY)`. Fix the cause and start the workflow by hand; a
repository that is never registered gets its project from its first run's start.

A registration that leaves the repository without a project (`project_limit`, `project_archived`, `name_taken`) is not
a failure: the repository is reviewed with the account's settings and the workflow's own inputs
([Setup](setup.md#a-repository-left-without-a-project)).
