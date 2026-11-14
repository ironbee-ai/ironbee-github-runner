# What reaches IronBee

Your code is read in your own job, and your model is called from it. IronBee is called at most twice per run, when
the run starts and when it ends, and once more when a repository is registered. Each call carries ids, fixed codes,
counts and the names of the models the run called. This page prints the three bodies in full.

Every call carries your API key in `X-API-Key`, and the runner's version in `User-Agent` (`ironbee-runner/1.0.0`).

## Registration: `PUT /v1/code-review-repositories`

Made by the register job, or by you ([Setup](setup.md#3-register-the-repository)). A run's start makes the
repository's project itself when it has none, with no registration call.

```json
{ "repository": { "provider": "github", "path": "acme/shop" },
  "runner": { "version": "1.0.0" } }
```

| Member | What it is |
|---|---|
| `repository.provider` | `github` |
| `repository.path` | the repository's `owner/name` |
| `runner.version` | the runner's version; a call made by hand may leave `runner` out |

## Start: `POST /v1/code-review-runs`

Made by a run before it clones or reads the change. Three kinds of run end before it, with no call to IronBee:

- a command from someone who may not write to the repository, which writes nothing;
- a run for a pull request that was closed or merged while its review waited, which writes nothing;
- a run with a configuration error found before the start (no `ironbee-api-key`, or an `app-slug` that is not your
  App's), which on a pull request's event leaves the configuration `neutral` check
  ([Troubleshooting](troubleshooting.md#configuration-errors)).

```json
{ "repository": { "provider": "github", "path": "acme/shop" },
  "pullRequest": 412,
  "head": "9f2c4e1a7b3d5f60812a4c6e8b0d2f4a6c8e0b1d",
  "action": "review",
  "trigger": "github_actions",
  "developer": 5550123,
  "runner": { "version": "1.0.0" } }
```

| Member | What it is |
|---|---|
| `repository` | as in the registration |
| `pullRequest` | the pull request's number |
| `head` | the commit id the run reviews |
| `action` | `review`, `answer` (a question on one of the reviewer's threads), `respond` (words addressed to the reviewer in the conversation) or `retract` |
| `trigger` | the CI: `github_actions` |
| `developer` | the numeric GitHub account id of the pull request's author; `null` when the author is a bot |
| `runner.version` | the runner's version |

**The author's id.** IronBee uses it to count the distinct developers of a month against your licence's limit
([The licence](licence.md)), and for nothing else. It is the numeric id, not the login. It is a number GitHub shows
publicly beside the login, and IronBee could look the login up from it.

The answer carries what the run needs: the run's id, the depth setting with the size classes, the size bounds, the
release-merge rule's long-lived branches, the gates' settings, the merge block, the reviewer's settings, the paths to
ignore, the console's rules and memories, the licence's end date and the month's developers beside the limit, and
whether the runner's version has a last day ([Versions](versions.md)).

## Complete: `POST /v1/code-review-runs/<id>/complete`

Made at the end of every run that started. The body is checked against its schema before it is sent.

```json
{ "status": "succeeded",
  "skip": null,
  "error": null,
  "round": 2,
  "read": "delta",
  "depth": "standard",
  "profile": "ironbee-self-hosted-standard",
  "customized": false,
  "classifier": "llm",
  "size": { "class": "M", "reviewableLines": 870, "files": 14 },
  "durationMs": 214000,
  "usage": { "calls": 31, "in": 412000, "out": 52000, "cacheRead": 0, "cacheWrite": 0,
             "byModel": [ { "model": "claude-sonnet-5-5", "calls": 27, "in": 380000, "out": 47000 },
                          { "model": "claude-opus-5-5", "calls": 4, "in": 32000, "out": 5000 } ] },
  "findings": { "posted": 5, "listed": 2, "open": 6, "fixed": 3, "dropped": 1, "blocking": 1,
                "bySeverity": { "critical": 0, "high": 1, "medium": 3, "low": 2 } },
  "answered": 0,
  "knowledge": { "applied": { "3f6c1d2e-8a4b-4c5d-9e0f-1a2b3c4d5e6f": 4 },
                 "cited": { "3f6c1d2e-8a4b-4c5d-9e0f-1a2b3c4d5e6f": 1 } } }
```

| Member | What it is |
|---|---|
| `status` | `succeeded`, `failed`, `cancelled` or `skipped` |
| `skip` | why a run was skipped: a gate (`asked_only`, `open_only`, `draft`, `bot`, `target_branch`, `skip_label`, `skip_title_keyword`), `fork`, `too_large`, `already_reviewed`, `paused`, `not_addressed`, `newer_state` |
| `error` | why a run failed: `model_unreachable`, `model_refused`, `host_refused`, `clone_failed`, `reviewer_failed`, `timeout`, `configuration`. There is no message field |
| `round` | the review's round on the pull request |
| `read` | what a review read: `whole`, `delta` (what changed since the last round) or `nothing`; `null` when no review ran |
| `depth` | `quick`, `standard` or `deep` |
| `profile` | the profile the run used: `ironbee-self-hosted-quick`, `-standard` or `-deep` |
| `customized` | whether a value of your [review file](review-file.md) was applied |
| `classifier` | `llm` (your model answered the classifier's questions) or `jev` ([Jev](jev.md)) |
| `size` | the size class (`S` to `XXXL`), the reviewable line count, and the file count |
| `durationMs` | the run's duration |
| `usage` | the model calls and their tokens in all, and for each model the run called (eleven at most, one for each task), under the name its task gave it |
| `findings` | the findings' counts: commented and listed in this round, and open, fixed, dropped and blocking on the pull request, the open ones by severity |
| `answered` | the number of questions and messages the run answered |
| `knowledge` | for each of the console's rules and memories the run used, by its id: how many reading calls carried it, and how many comments cite it |

Fields an action does not have are `null`. The schema is strict: integers, the closed lists above, the run's id, ids
of the console's rules and memories, and the models' names. A body with anything else is refused whole.

## What is never sent

File contents or diffs, file paths, branch names, titles, descriptions, labels, commit messages, logins or names of
authors and commenters, comments, finding texts, quotes, summaries, model prompts or replies, logs, error messages.

The models' names are the only strings a body carries beside ids and fixed codes. They are your own configuration (the
profile's, the workflow's or the review file's), bounded in number (eleven), length (200 characters) and alphabet
(letters, digits and `. _ : / @ -`).

The runner can print both bodies of a run in the job's log as it sends them (its `--print-report` option).

## What else leaves your job, and where

- **Docker Hub** sees the image pulls made with your registry token. It is sent nothing about a repository.
- **Your model's endpoint** receives the model calls, and the extra headers of `model-headers`, which go to that
  endpoint alone.
- **Jev's vendor**, only when you set your own Jev key, receives what [Jev](jev.md) lists, under your own account with
  it. None of that passes through IronBee.
- **Your rules repository and the review file** are read by the runner. Of them IronBee learns that the review file
  changed a value and the names of the models called, and nothing else; the counts in `knowledge` cover the console's
  rules and memories alone.

## What stays with you

The clone, the model traffic, the rules repository's files, the review file, every record the reviewer keeps (in the
pull request's comments), the check run's text, the run's working files (deleted with the job's container), and the
job's log (in your CI).

## Credentials

| Credential | Held by | Can do |
|---|---|---|
| IronBee API key | your secrets | everything your account's key can do on IronBee's API; this feature adds no narrower key |
| registry token | your secrets | pull the image |
| `GITHUB_TOKEN`, or your App's key | the job; your secrets | read the repository, write on pull requests, write checks |
| model key, and the endpoint's extra headers when there are any | your secrets | your model account |
| the rules repository's token, when there is one | your secrets | read that one repository |

IronBee holds none of the last three.

## Untrusted input

The reviewer reads a pull request and comments written by anyone who can write them.

- **Nothing in the repository is run.** The head is checked out only to be read; the model's tools only read, inside
  the checkout, and refuse a link that leaves it; the image's git runs no filter and no hook of the repository's.
  Nothing of the rules repository is run either.
- **What a model writes goes to the pull request and nowhere else.** Before it is posted, whatever in it would make
  GitHub load an address is neutralised: a Markdown image, an HTML element that loads one, a diagram that names one.
  A link stays a link. In the description, where the summary follows the author's own text, the author's text is never
  changed.
- **Who is obeyed.** A command only from someone who may write to the repository, a question on the reviewer's thread
  only from people who count, and a bot's comment starts nothing.
- **Who sets how a review runs.** The review file is read from the rules repository and from the pull request's base,
  never from its head. The workflow file is the branch's own, with the limits
  [what the check is worth](required-check.md#what-the-check-is-worth) names.

A prompt injection can therefore at most make a review or an answer wrong, or make it quote the repository's own code
into the repository's own pull request. Where the job may connect is your network's policy.
