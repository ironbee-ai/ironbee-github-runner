# Setup

This guide takes a repository from nothing to reviewed pull requests. The pages it links to cover each part in full.

## What you need

From IronBee:

- **The self-hosted runner enabled on your IronBee account.** Its licence has an end date and a developer limit
  ([The licence](licence.md)).
- **Your account's API key.** IronBee's API takes it in `X-API-Key`. It is your account's key: it can do on IronBee's
  API everything that key can do, and this feature adds no narrower one.
- **A registry token.** The runner's image is in a private repository on Docker Hub, and IronBee gives each customer a
  read-only token for it. Being able to pull the image entitles you to nothing by itself: every run still asks IronBee
  whether it may run.

From your side:

- repositories on github.com;
- a model, and its key where it needs one ([Models](models.md));
- GitHub's hosted runners, or runners of your own ([Where the job runs](#where-the-job-runs)).

## 1. Store the secrets

Store the API key, the registry token and your model's key as Actions secrets of the repository or of its
organization. Their names are yours to choose; this guide uses `IRONBEE_API_KEY`, `IRONBEE_REGISTRY_TOKEN` and
`ANTHROPIC_API_KEY`.

## 2. Add the workflow file

Add `.github/workflows/ironbee-review.yml` to the repository:

```yaml
name: IronBee
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
  issue_comment:
    types: [created]
  pull_request_review_comment:
    types: [created]
  merge_group:
  push:                           # registers the repository when this file reaches the default branch
    branches: [main]
    paths: ['.github/workflows/ironbee-review.yml']
  workflow_dispatch:              # and when the workflow is started by hand
permissions:
  contents: read
  pull-requests: write
  checks: write
  issues: read
jobs:
  code-review:
    name: Code Review
    uses: ironbee-ai/ironbee-github-runner/.github/workflows/code-review.yml@v1.0.0
    with:
      model-provider: anthropic
      # model-name: one model for every task; required for `openai` with `model-url`
      # runs-on: a self-hosted runner's label, or a JSON list of labels in a string, when the model is inside the network
      # knowledge-repository: your rules repository
      # ignore-paths, target-branches, skip-labels, skip-title-keywords: for a repository without a project
    secrets:
      ironbee-api-key: ${{ secrets.IRONBEE_API_KEY }}
      registry-token: ${{ secrets.IRONBEE_REGISTRY_TOKEN }}
      model-key: ${{ secrets.ANTHROPIC_API_KEY }}
      # knowledge-token: a read-only token for the rules repository, under the job token
```

What each part does:

- **The triggers.** A pull request opened, pushed, reopened or marked ready for review starts a review. A reply in a
  thread the reviewer started starts an answer. A comment in the pull request's conversation that addresses the
  reviewer starts a command or an answer to a question ([On a pull request](#on-a-pull-request)). `merge_group` is
  for GitHub's merge queue: the group's commit gets a `neutral` check, since the review was made on the pull request.
  The last two triggers register the repository with IronBee (step 3). Set `branches` to your default branch and
  `paths` to this file's own path.
- **The permissions.** `contents: read` to clone and read, `pull-requests: write` to post the review and its replies,
  `checks: write` for the `Code Review Result` check, and `issues: read` for the issues a pull request links. Once a
  workflow sets `permissions`, a scope it does not list is none. Resolving threads needs one more
  ([Resolving threads](#resolving-threads)).
- **The version.** `@v1.0.0` names an exact release. Its tag is never moved, and the release names its image by
  digest. To rely on more than a tag, pin the workflow's commit in its place, and with it the image
  ([Versions](versions.md)).
- **The inputs and secrets.** Listed below. `model-provider` is required. `ironbee-api-key` and `registry-token` are
  needed for every review, though the workflow does not mark them required: GitHub gives a Dependabot run empty
  secrets, and that run must still reach the decide step, which counts a run as having its secrets only when both are
  set. `model-key` is needed at a model provider's own endpoint; every other one only for what it names.

The reusable workflow is one job, `Job`, so a pull request's checks show it once, beside the `Code Review Result`
check it writes. With the file above they read `IronBee / Code Review / Job (pull_request)` and
`IronBee / Code Review Result (pull_request)`: the workflow's `name`, then the job's `name`. Its steps:

1. **The workflow's scripts**, fetched from the workflow's own repository at the commit your file names.
2. **Register**, for the last two triggers alone: the repository's project at IronBee (step 3).
3. **Decide**, for a pull request's events: what the event asks for, without the image. Nothing for the reviewer ends
   the run here.
4. **A `neutral` check**, for a merge queue's group and a pull request's run given no secrets.
5. **Review**: the runner's image, pulled from Docker Hub by its digest and run, for the review, the answer or the
   command. It is stopped after two hours; every other step after a few minutes, so a run holds the pull request's
   queue a bounded time.
6. **Fallback**: a pull request's review that did not succeed (failed, cancelled, timed out, or the image not pulled
   or started) leaves a `neutral` check on the event's head, unless the review had begun to conclude there.

One run per pull request at a time, for the events that may run the reviewer: a pull request's events, a person's
reply on a review thread, and a person's conversation comment that mentions someone (`@`). A run that has started is
never cancelled, and the runs that wait are kept and run in turn, each reading what the one before it wrote. Every
other event never waits: a bot's comment (the reviewer's own included), a review thread's first comment, a comment
that mentions nobody, a merge queue's group, a push and a manual start.

## Every input and secret

The names below are part of each release's contract: within a major version none is renamed or removed, and a new
one is optional ([Versions](versions.md)).

| Input | For |
|---|---|
| `model-provider` | the model's provider: `anthropic`, `bedrock` or `openai`. Required ([Models](models.md)) |
| `model-url` | the model's endpoint, when it is not the provider's public one |
| `model-name` | one model for every task. Required for `openai` with `model-url` |
| `model-ca-certificate` | the certificates, in PEM, of a private authority that signed the endpoint's certificate |
| `model-prefix` | `bedrock` only: the inference profile prefix |
| `model-max-output` | the most output tokens a turn may ask for, when your model or server allows fewer than the reviewer asks |
| `aws-region` | the Bedrock region. Required for `bedrock` |
| `runs-on` | where the job runs, when not on GitHub's own runners (`ubuntu-latest` when not given): one runner label, or a JSON list of labels in a string such as `'["self-hosted","linux"]'`; a YAML list is refused ([Where the job runs](#where-the-job-runs)) |
| `ironbee-api-url` | IronBee's API address; empty means the default public API. Only for a regional or test endpoint IronBee gives you |
| `ironbee-run-reports` | `true` when not given. `false` tells IronBee only that a run started, with nothing of the pull request and no complete, and the console then lists no pull requests or runs for the repository ([What reaches IronBee](what-reaches-ironbee.md#with-run-reports-off)) |
| `knowledge-repository` | your rules repository, `owner/name` ([Settings and rules](settings-and-rules.md#the-rules-repository)) |
| `knowledge-ref` | a branch or a tag of the rules repository; its default branch when not given |
| `ignore-paths` | the paths to ignore, for a repository left without a project in IronBee; one a line |
| `target-branches` | the branches pull requests are reviewed for, for a repository left without a project; one a line |
| `skip-labels` | the labels that keep a pull request from being reviewed, for a repository left without a project; one a line |
| `skip-title-keywords` | the words in a title that keep a pull request from being reviewed, for a repository left without a project; one a line |
| `app-slug` | your own GitHub App's slug ([Identity](identity.md)) |

| Secret | For |
|---|---|
| `ironbee-api-key` | IronBee's API. Needed for every review, and for the register step |
| `registry-token` | the image's registry. Needed for every review |
| `model-key` | the model's key. Required at a provider's own endpoint, optional with `model-url` ([Models](models.md)) |
| `model-headers` | extra headers for the model's endpoint, one `name=value` a line |
| `knowledge-token` | a read-only token for the rules repository: needed for a private one under the job token; under your own App, used in place of the App's token |
| `jev-key` | Jev with your own key ([Jev](jev.md)) |
| `app-id` | your own GitHub App's id |
| `app-private-key` | your own GitHub App's private key |

The four per-repository inputs carry what the IronBee console holds for a repository's project. They are used only
for a repository that IronBee left without a project ([step 3](#a-repository-left-without-a-project)); for every
other repository the console's values apply, even when they are empty.

**How the workflow treats them.** A comment's body, a title or a branch name reaches a step of the workflow only
through an environment variable or GitHub's event file, never pasted into a script. The decide step is told whether
the API key and the registry token are set, never given either. The registry token reaches only the review step,
which signs in to Docker Hub with it through standard input, for the pull alone. Your App's key reaches the review
step and, beside it, only the two steps that mint a token for a `neutral` check. The model's key, its headers and its
certificates reach the runner's container as environment variables, by name, never on a command line, and the rules
repository's input, ref and token reach the runner alone.

## 3. Register the repository

A registered repository has a project in IronBee: its settings, rules and memories are edited in the console, and
the console lists its pull requests and their runs. Registering is one call to IronBee's API with the repository's
path, and there are three ways to make it:

- **The workflow file reaching the default branch.** The `push` trigger runs the register step when the file is
  pushed to the default branch, and `workflow_dispatch` runs it when you start the workflow by hand. The step reads
  nothing of the event but the repository's path and writes nothing to GitHub. Its log says the project's id and
  whether it was made, or why the repository was left without one. Of the licence, it prints only the warnings a run
  prints: the log of a public repository is public, and your contract's numbers are not for it.
- **By hand or from a script**, at any time and for as many repositories as you like (below).
- **The first run**, when neither of the others has: a run's start gets or makes the project the same way.

The call may be repeated: a repository already registered keeps its project.

### What comes first

A workflow file pushed straight to the default branch registers the repository before any pull request. A file added
by a pull request, the usual way and the only one under branch protection, runs on that pull request first: GitHub
runs a pull request's events with the workflow file the pull request brings, a start by hand needs the file on the
default branch, and the `push` trigger fires only at the merge. So the pull request that adds the file is itself
reviewed first, with your account's settings, and its start makes the project.

To have a repository's settings in place before any review, register it beforehand with one call, or push the file
straight to the default branch.

### Registering with one call

With an `ironbee-api-url` from IronBee, use that address in place of the default one.

```sh
curl --fail-with-body -X PUT https://api.service.ironbee.ai/v1/code-review-repositories \
  -H "X-API-Key: $IRONBEE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"repository": {"provider": "github", "path": "acme/shop"}}'
```

The answer:

```json
{ "project": { "id": "<uuid>", "created": true },
  "noProject": null,
  "licence": { "developers": { "limit": 50, "used": 41 }, "endsAt": "2027-11-13" },
  "runner": { "supportedUntil": null, "moveTo": null } }
```

`created` is `false` when the project was already there. The runner adds its version to the call
(`"runner": {"version": "1.0.0"}`); a call made by hand may leave it out.

The call is refused, and nothing changes, when the self-hosted runner is not enabled on the account
(`SELF_HOSTED_RUNNER_NOT_ENABLED`), when the account is suspended (`SELF_HOSTED_RUNNER_SUSPENDED`), when the licence
has ended (`SELF_HOSTED_RUNNER_LICENCE_ENDED`), when IronBee's cloud product already reviews the repository
(`REPOSITORY_REVIEWED_BY_CLOUD`), and, from the register step, when its runner version is no longer served
(`RUNNER_VERSION_UNSUPPORTED`). The register step then fails with the reason, so a wrong setup is found on the day of
the install. A repository the register step could not register is registered by its first run.

### A repository left without a project

Three cases leave a repository without a project. `noProject` names the case, and `project` is `null`:

| `noProject` | Why |
|---|---|
| `project_limit` | the account has reached its limit of 100 live projects |
| `project_archived` | the repository's project is archived; an archived project is never revived |
| `name_taken` | the name belongs to another repository's GitHub project in your account, connected to IronBee's cloud product or once connected |

Such a repository is still reviewed, with your account's settings, and with its four per-repository settings taken
from the workflow's inputs (`ignore-paths`, `target-branches`, `skip-labels`, `skip-title-keywords`). Its runs are in
no project's list in the console.

### A repository IronBee's cloud product reviews

A repository connected to IronBee's cloud product, with code review on, is refused
(`REPOSITORY_REVIEWED_BY_CLOUD`): two reviewers on one pull request would both post. Turn its code review off in the
console before the runner reviews it. A connected repository whose code review is off is reviewed by its workflow.

## 4. Where the repository's settings are

In the IronBee console, on the repository's project: its four per-repository settings, its overrides of the
account's settings, and its rules and memories. The account's settings are on the account's code-review settings
page, beside a line for the licence. [Settings and rules](settings-and-rules.md) says which settings apply to a
self-hosted run and how.

The console shows a registered repository as reviewed by its workflow, and its code-review page lists its pull
requests and their runs, built from the counts IronBee is sent: no title, author or text, since none is sent.

## 5. Make `Code Review Result` a required check

Optional. Add `Code Review Result` as a required status check of the branch. A gate, a licence problem or a run that could
not start leaves a `neutral` check, which passes, so it never blocks a merge; open findings at or above the team's
`mergeBlock` level do. Before you rely on it, read
[what the check is worth](required-check.md#what-the-check-is-worth): the check is a team's own discipline made
visible, not a control over its members, and in this release anyone who can push a branch can forge it. The same page
covers the merge queue, forks and Dependabot.

## On a pull request

| What happens | What the reviewer does |
|---|---|
| A pull request is opened, pushed, reopened or marked ready for review | reviews it: a first round reads the whole change, a later round what changed since the last |
| Someone who counts replies in one of the reviewer's threads | answers a question, when the team's `answerQuestions` setting is on. Who counts: the pull request's author and the repository's owners, members and collaborators |
| Someone who may write to the repository addresses the reviewer in the conversation | obeys a command, or answers a question |

The commands, under the job token (under your own App, `@` and your App's slug in place of `@ironbee-ai`):

| Command | What it does |
|---|---|
| `@ironbee-ai review` | reviews what was pushed since the last round. With nothing pushed, it reads nothing again (or only what a partial round left unread) and restates the check from the pull request's texts |
| `@ironbee-ai full review` | reads the whole pull request again |
| `@ironbee-ai pause` | pauses automatic reviews of the pull request: a review a push starts stops as paused |
| `@ironbee-ai resume` | resumes them |
| `@ironbee-ai retract` | takes back every comment of the reviewer's on the pull request; the check becomes `neutral` |

A command counts only from someone with write, maintain or admin permission on the repository. A comment written
by a bot, the reviewer's own included, starts nothing. A reply that turns a finding down ("won't fix"), and a thread
someone resolves, are recorded by the next review that reads the pull request again, after a push or
`@ironbee-ai full review`.

Pull requests from forks are not reviewed, and nothing on one starts a run. When the team's `summary` setting is on,
a review's summary is written in the pull request's description, after the author's own text, which is left as it
was.

## Resolving threads

Resolving a thread on GitHub (`closeFixedThreads`, and the thread of a finding the reviewer withdraws) needs
`contents: write`. The workflow does not grant it by default. A team that wants threads resolved adds the
permission to its workflow file; without it the reply is still written, the thread stays open, and the job's log
says that the resolve was refused and what it needs.

## Where the job runs

On GitHub's own runners or on your self-hosted ones.

- A model reachable from the internet, such as your Anthropic, Bedrock or OpenAI account, works from GitHub's own
  runners.
- **A model inside your network needs a self-hosted runner there.** Name it in `runs-on`: one label
  (`runs-on: my-runner`), or a JSON list of labels in a string (`runs-on: '["self-hosted","linux"]'`). A YAML list is
  refused by the workflow's validation. Such a runner connects outward only.
- A self-hosted runner needs Linux with Docker, on `amd64` or `arm64`, and `bash`, `jq`, `gh`, `curl` and `docker`.
  The job uses those, the image, `actions/checkout` and, under your own App, GitHub's own action that mints an App
  token. The review step runs the image with `docker run` as the runner's own user, and mounts the event file and the
  step's outputs file into it by their paths on the runner: a runner that is itself a container must reach a Docker
  daemon that sees those paths at the same place. A proxy set on the runner's machine (`HTTPS_PROXY`, `NO_PROXY` and
  their lowercase forms) is handed on to the runner.
- **Rootless Docker** works: the container then runs as its own root, which is the runner's user on the machine.
  **Docker with `userns-remap`** is not supported: the container's users could not write the step's outputs file, so
  the review step fails at once, naming it, before it pulls anything.
- **On a public repository,** a fork's pull request runs its own copy of the workflow file on the runner that file
  names, so use a self-hosted runner only on private repositories, or require approval before workflows from forks
  run.

What the runner connects to: GitHub, your model's endpoint and IronBee's API (`api.service.ironbee.ai`, or the
address in `ironbee-api-url`), and nothing else; with your Jev key, also Jev's endpoint ([Jev](jev.md)). The image is
pulled from Docker Hub by the review step, by its digest. Where the job may connect beyond that is your network's
policy.

An organization that does not allow workflows from outside its own repositories must copy this whole repository at
a release, the workflow file and `scripts/`, into a repository the calling job's token can read: the calling
repository itself, or a public one. The job fetches `scripts/` from the workflow's own repository with that token,
and a private copy elsewhere cannot be read by the caller's `GITHUB_TOKEN`. Call the copy in place of
`ironbee-ai/ironbee-github-runner`.

## Next

- [Identity](identity.md): run the reviewer as your own GitHub App instead of the job token.
- [The review file](review-file.md): adjust each task's model and effort, and a closed list of settings.
- [Settings and rules](settings-and-rules.md): keep rules for all your repositories in a repository of your own.
- [The `Code Review Result` check](required-check.md): make it required, and know what it is worth.
