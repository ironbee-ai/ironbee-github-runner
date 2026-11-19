# Setup

This guide takes a repository from nothing to reviewed pull requests. The pages it links to cover each part in full.

## What you need

From IronBee:

- **The self-hosted runner enabled on your IronBee account.** Its licence has an end date and a developer limit
  ([The licence](licence.md)).
- **Your account's API key.** IronBee's API takes it in `X-API-Key`.
- **A registry token.** The runner's image is in a private repository on Docker Hub, and IronBee gives each customer a
  read-only token for it. Being able to pull the image entitles you to nothing by itself: every run still asks IronBee
  whether it may run.

From your side:

- repositories on github.com, on a GHE.com tenant or on GitHub Enterprise Server
  ([On GitHub Enterprise](#on-github-enterprise));
- a model, and its key where it needs one ([Models](models.md));
- GitHub's hosted runners, or runners of your own ([Where the job runs](#where-the-job-runs)).

## With IronBee's CLI

IronBee's CLI takes the steps below for you: `ironbee runner setup --host github` registers the repositories, stores
the secrets and adds the workflow file. The steps stay written out below for doing by hand; a setup made by hand and
one made by the command are the same objects, and `ironbee runner check` reads either.

```sh
npm install -g @ironbee-ai/cli
export IRONBEE_API_KEY IRONBEE_REGISTRY_TOKEN IRONBEE_MODEL_KEY   # or let the command ask
ironbee runner setup --host github --repos acme/shop,acme/payments --model-provider anthropic
```

It needs Node.js 22 or later. Inside a clone of a github.com repository, `--host github` may be left out: the command
takes the host from the directory's git remote.

**Its sign-in to GitHub** is your own, through GitHub's CLI, `gh` (`gh auth login`; a `GH_TOKEN` in the environment
serves the same way). The command stores no GitHub credential and sends none to IronBee: it calls GitHub through `gh`,
and IronBee's API only to register the repositories. You must be able to administer each repository (its Actions
secrets) and to push a workflow file there (the token's `workflow` scope); for organization secrets, an owner of the
organization.

**The secrets** come from their environment variables, or are asked for and typed unseen; the command writes none of
them to disk and prints none of them. `IRONBEE_API_KEY` and `IRONBEE_REGISTRY_TOKEN` are needed, `IRONBEE_MODEL_KEY` is
asked for (empty for an endpoint that takes none), and `IRONBEE_MODEL_HEADERS`, `IRONBEE_KNOWLEDGE_TOKEN` and
`IRONBEE_JEV_KEY` are taken from the environment when set. Each is stored as the Actions secret of the same name, and
the workflow file passes it.

| Flag | What |
|---|---|
| `--host github` | this host (else the directory's git remote, else asked) |
| `--repos <list>` | the repositories, `owner/name`, separated by commas |
| `--org <organization>` | every repository of the organization that you administer and that is not archived, in place of `--repos` |
| `--org-secrets` | the organization's secrets, visible to the repositories named, in place of each repository's own (below) |
| `--direct` | commit the workflow file to the default branch, in place of a pull request |
| `--model-provider`, `--model-url`, `--model-name`, `--model-prefix`, `--model-max-output`, `--aws-region` | the model's inputs ([Models](models.md)) |
| `--model-ca-certificate <file>` | a PEM file: the private authority that signed your model endpoint's certificate |
| `--runs-on <label>` | a self-hosted runner's label, or a JSON list of labels ([Where the job runs](#where-the-job-runs)) |
| `--knowledge-repository <owner/name>`, `--knowledge-ref <ref>` | the rules repository ([Settings and rules](settings-and-rules.md#the-rules-repository)) |
| `--ignore-paths`, `--target-branches`, `--skip-labels`, `--skip-title-keywords` | for a repository left without a project; each a list separated by commas |
| `--run-reports false` | a run tells IronBee only that it started ([What reaches IronBee](what-reaches-ironbee.md#with-run-reports-off)) |
| `--version <version>` | the release a new workflow file names; the latest release of `ironbee-ai/ironbee-github-runner` when not given |
| `--update` | move the release an existing workflow file names, to the latest or to `--version` |
| `--component <owner/name>@<ref>` | another workflow repository and ref than this one, such as a copy of yours; no release is read |

What the command is not given by a flag it asks for, in a terminal; without one it stops and names the flag.

**What it does, in this order.** Each step first reads what exists, so the command can be run again:

1. **Registers the repositories** with IronBee ([step 3](#3-register-the-repository)). A refusal (the feature not
   enabled, the licence ended or suspended, a repository IronBee's cloud product reviews) ends the command before
   anything is changed on GitHub.
2. **The secrets**, written through `gh`, each repository's own by default. A secret that is already there is kept.
   With `--org-secrets` they are the organization's, visible to selected repositories:
   - the command first checks what that needs, and says what is missing: the sign-in's `admin:org` scope, which `gh`'s
     default sign-in lacks (`gh auth refresh -s admin:org`), and a plan on which the repositories can read an
     organization's secrets: a private repository on GitHub Free cannot, and the command then refuses `--org-secrets`
     and names repository secrets instead;
   - a secret that is not there is made with the repositories named as its list;
   - a secret that is already there is never set again, which would need its value typed and would replace its list:
     the command adds each repository named to that secret's list.
3. **The workflow file**, `.github/workflows/ironbee-review.yml`, as [step 2](#2-add-the-workflow-file) shows it, at
   the release given, with the model's inputs, the repository's default branch in its `push` trigger, and
   `ironbee-api-url` when the CLI is set to an API other than `https://api.service.ironbee.ai`. By default on a branch
   of its own, `ironbee/runner-setup`, with a pull request opened for it: a protected default branch takes it no other
   way, and that pull request is the first one reviewed, with the settings step 1 put in place. With `--direct`,
   committed to the default branch. A workflow file that is already there is left as it is; `--update` moves only the
   release it names, by a pull request too unless `--direct` is given.
4. **Prints** what it made and kept, never a secret, and that `Code Review Result` becomes a required check by your
   branch protection or ruleset ([step 5](#5-make-code-review-result-a-required-check)), which the command does not set.

**More repositories:** `ironbee runner add acme/billing --host github`: the same steps for the repositories named.

**`ironbee runner check`** changes nothing. For each repository it reads the workflow file on the default branch and
its release against the latest; that the secrets the file passes exist (by name: GitHub shows no value), as the
repository's own or as an organization secret with the repository on its list; that GitHub Actions is on and the
repository may call a workflow of `ironbee-ai/ironbee-github-runner`; the registration; and whether `Code Review Result`
is required, as information. `--fix` takes the setup's steps for what is missing.

```sh
ironbee runner check --host github --repos acme/shop,acme/payments
```

The command ends with exit code 0 when nothing it found is an error, 1 otherwise, 2 for a flag it cannot read. Your own
GitHub App ([Identity](identity.md)), a self-hosted runner, the rules repository's content and branch protection are
not the command's.

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
check it writes. With the file above the job reads `IronBee / Code Review / Job (pull_request)`: the workflow's
`name`, then the job's `name`. The check is named `Code Review Result`; written with the workflow's token it usually
shows under the workflow, as `IronBee / Code Review Result (pull_request)` (GitHub picks its place), and under your
own GitHub App under the App's name. Its steps:

1. **The workflow's scripts**, fetched from the workflow's own repository at the commit your file names; on GitHub
   Enterprise Server, from the copy `runner-repository` names, at the release's tag
   ([A copy of this repository](#a-copy-of-this-repository)).
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
that mentions nobody, a merge queue's group, a push and a manual start. A host whose Actions keep only one waiting
run calls the workflow without a queue instead ([A host without a queue](#a-host-without-a-queue)).

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
| `runner-repository` | your copy of this repository, `owner/name`, on a host whose jobs do not name their workflow's repository: GitHub Enterprise Server. Elsewhere the job names it, and this input is not read ([A copy of this repository](#a-copy-of-this-repository)) |
| `github-ca-certificate` | the certificates, in PEM, of a private authority that signed your GitHub Enterprise Server's certificate ([On GitHub Enterprise Server](#on-github-enterprise-server)) |

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
| `runner-token` | a read-only token for your copy of this repository, which the job's token cannot read: needed on GHE.com and GitHub Enterprise Server, and on github.com for a copy that is not public ([A copy of this repository](#a-copy-of-this-repository)) |

The four per-repository inputs carry what the IronBee console holds for a repository's project. They are used only
for a repository that IronBee left without a project ([step 3](#a-repository-left-without-a-project)); for every
other repository the console's values apply, even when they are empty.

**How the workflow treats them.** A comment's body, a title or a branch name reaches a step of the workflow only
through an environment variable or GitHub's event file, never pasted into a script. The decide step is told whether
the API key and the registry token are set, never given either. The registry token reaches only the review step,
which signs in to Docker Hub with it through standard input, for the pull alone. Your App's key reaches the review
step and, beside it, only the two steps that mint a token for a `neutral` check. The model's key, its headers and its
certificates, and your server's certificates, reach the runner's container as environment variables, by name, never on
a command line, and the rules repository's input, ref and token reach the runner alone. `runner-token` reaches only the
step that fetches the workflow's scripts.

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

On a GitHub Enterprise host the path carries the host: `"path": "ghes.acme.com:acme/shop"` on a server,
`"acme.ghe.com:acme/shop"` on a GHE.com tenant, as the runner sends it. A bare `acme/shop` names github.com's
repository, a different project. `scripts/register.sh` run by hand adds the host only when `GITHUB_SERVER_URL` names it.

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
`mergeBlock` level do. [Making it required](required-check.md#making-it-required) covers the merge queue, forks and
Dependabot.

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
  The job uses those, the image, `actions/checkout` and GitHub's own action that mints an App token: a runner fetches
  every action a job names before its first step, the App token's one too when no App is given. The review step runs
  the image with `docker run` as the runner's own user, and mounts the event file and the step's outputs file into it
  by their paths on the runner: a runner that is itself a container must reach a Docker daemon that sees those paths at
  the same place. A proxy set on the runner's machine (`HTTPS_PROXY`, `NO_PROXY` and
  their lowercase forms) is handed on to the runner.
- **Rootless Docker** works: the container then runs as its own root, which is the runner's user on the machine.
  **Docker with `userns-remap`** is not supported: the container's users could not write the step's outputs file, so
  the review step fails at once, naming it, before it pulls anything.

What the runner connects to: GitHub, your model's endpoint and IronBee's API (`api.service.ironbee.ai`, or the
address in `ironbee-api-url`), and nothing else; with your Jev key, also Jev's endpoint ([Jev](jev.md)). The image is
pulled from Docker Hub by the review step, by its digest. Where the job may connect beyond that is your network's
policy.

An organization that does not allow workflows from outside its own repositories keeps a copy of this repository and
calls the copy in place of `ironbee-ai/ironbee-github-runner`
([A copy of this repository](#a-copy-of-this-repository)).

## On GitHub Enterprise

The runner serves repositories on github.com under GitHub Enterprise Cloud, on a GHE.com tenant (`<name>.ghe.com`,
GitHub Enterprise Cloud with data residency) and on GitHub Enterprise Server 3.19 or later with GitHub Actions on, from
release `v1.0.0`; the pre-releases before it serve github.com alone. IronBee never calls your host for these
repositories: there is no host to register with IronBee, no address of IronBee's to allow and no certificate to give
IronBee. The job reads your host, calls your model and calls IronBee's API as it does on github.com, so a server that is
not reachable from the internet is served when its runners reach IronBee's API, Docker Hub and your model.

| | Enterprise Cloud on github.com | GHE.com | GitHub Enterprise Server |
|---|---|---|---|
| The workflow file you call | `code-review.yml` | `code-review.yml`, or `code-review-no-queue.yml` where your tenant refuses `queue` ([below](#on-ghecom)) | `code-review-no-queue.yml` ([A host without a queue](#a-host-without-a-queue)) |
| Where it is | this repository, or your copy where a policy asks for one | your copy on the tenant | your copy on the server |
| `runner-repository` | not read | not read | your copy, `owner/name` |
| `runner-token` | for a copy that is not public | always | always |
| `runs-on` | any runner | GitHub's Linux runners or yours | your own runners, with Docker |
| `github-ca-certificate` | — | — | when a private authority signed the server's certificate |
| `knowledge-token`, under the job token | for a private rules repository | for any rules repository | for a private one, and for any on a server in private mode |

IronBee files the repository as `<host>:owner/name` (`acme.ghe.com:acme/shop`), apart from a github.com repository of
the same name, and the repository gets its own project. IronBee refuses a host it cannot name as one: a server named by
an IP address or by a single label. Its registration fails, and its pull requests get a `neutral` check that holds no
merge.

### A copy of this repository

On GHE.com and GitHub Enterprise Server the workflow is called from a copy of this repository on your host (a reusable
workflow on github.com cannot be called from a server); on a tenant the copy is private or internal, the only kinds its
organizations hold. On github.com a copy is what an enterprise keeps when it allows no workflows from outside.

- **Make it** from a release, with this repository's tags: the workflow file names its release's tag, and on a server
  the scripts are fetched at that tag. On a server, `actions-sync` copies the repository from github.com; elsewhere,
  mirror it (`git clone --mirror https://github.com/ironbee-ai/ironbee-github-runner.git`, then `git push --mirror` to
  your copy). To move to a later release, copy again, then move the tag in `uses:`.
- **Call it** in place of `ironbee-ai/ironbee-github-runner`, at a release: `uses:
  <owner>/<name>/.github/workflows/<file>@v1.0.0`. On a server, name it again in `runner-repository`: a server's jobs
  do not name their workflow's repository, and the first step fails, naming the input, when neither names it.
- **Who may call it.** A public copy serves every repository. An internal copy serves the enterprise's private and
  internal repositories once its Actions access setting allows them (**Settings → Actions → General → Access**:
  accessible from repositories in the enterprise). A private copy's workflow can be called from private repositories
  only. A public repository on a server needs a public copy.
- **`runner-token`**, a read-only token that can read the copy: the job's token reads the calling repository alone. Give
  it as an Actions secret, and as a Dependabot secret of the same name, since GitHub gives Dependabot's runs none of
  the repository's secrets. Without it the first step cannot fetch the scripts, nothing else runs, and a required
  `Code Review Result` holds the merge. On a server it is needed for a public copy too. A classic token reads a private
  or internal copy with the `repo` scope; where the organization uses SAML single sign-on, authorize the token for it
  as well (**Configure SSO** beside the token), or GitHub answers the scripts' fetch with 403.

```yaml
    uses: acme/ironbee-github-runner/.github/workflows/code-review.yml@v1.0.0
    with:
      model-provider: anthropic
    secrets:
      # ironbee-api-key, registry-token, model-key, as above
      runner-token: ${{ secrets.IRONBEE_RUNNER_TOKEN }}
```

### On GHE.com

- Your tenant takes `actions/checkout` and `actions/create-github-app-token` from github.com, and GitHub's Linux runners
  run the job.
- `code-review.yml` names `concurrency.queue`. Where your tenant refuses the workflow for that key, call
  `code-review-no-queue.yml` as a server does ([A host without a queue](#a-host-without-a-queue)).
- **The rules repository** is read with `knowledge-token` under the job token: your tenant refuses the anonymous read
  the runner makes without one. Under your own App, install the App there, as on github.com.

### On GitHub Enterprise Server

- **The runners are yours.** A server has no hosted runners: name yours in `runs-on`. Linux with Docker, `amd64` or
  `arm64`, with `bash`, `jq`, `gh`, `curl` and `docker`, and GitHub Actions Runner 2.327.1 or later: `actions/checkout`
  v6 runs on Node 24. They reach your server, Docker Hub, IronBee's API and your model.
- **The actions, at the commits this workflow pins:** `actions/checkout` v6.0.2 and
  `actions/create-github-app-token` v3.3.0, both needed with or without your own App: a runner fetches every action the
  job names before its first step, and a job naming one the server lacks fails there. A site admin makes them
  available on the server: with `actions-sync`, or through GitHub Connect once the server's own older copy of the action
  is removed, since the server's copy wins.
- **A private authority.** When one signed the server's certificate, give its certificates in
  `github-ca-certificate`, in PEM: the reviewer's container adds them to its own roots for its calls to the server and
  its clone. The runner's machine must trust the server already: Actions itself, the workflow's other steps and `gh`
  use the machine's trust.
- **Your own App** is registered on the server, and its slug is the server's ([Identity](identity.md)).

```yaml
jobs:
  code-review:
    name: Code Review
    uses: acme/ironbee-github-runner/.github/workflows/code-review-no-queue.yml@v1.0.0
    with:
      model-provider: anthropic
      runner-repository: acme/ironbee-github-runner
      runs-on: '["self-hosted","linux"]'
      # github-ca-certificate: ${{ vars.GHES_CA_CERTIFICATE }}
    secrets:
      ironbee-api-key: ${{ secrets.IRONBEE_API_KEY }}
      registry-token: ${{ secrets.IRONBEE_REGISTRY_TOKEN }}
      model-key: ${{ secrets.ANTHROPIC_API_KEY }}
      runner-token: ${{ secrets.IRONBEE_RUNNER_TOKEN }}
```

The whole file, with its permissions, is in [examples/ironbee-review-enterprise-server.yml](../examples/ironbee-review-enterprise-server.yml).

### A host without a queue

`code-review-no-queue.yml` is the same workflow, of the same release, for a host whose Actions keep only one waiting
run of a concurrency group: every GitHub Enterprise Server today. There a newer run replaces the one that waits:

- a review that waited, replaced by a review, loses nothing: the run that replaces it reads the newest head;
- a command or a question that waited is lost: its author asks again;
- a review that waited, replaced by a reply or a command, is started again by the run that replaced it, at its end:
  that run's last step re-runs the newest review of the pull request's head that was cancelled, once the head holds no
  check and no review of the reviewer's. A review started again takes the waiting place like any newer run. A review
  someone cancelled by hand while it waited is started again the same way.

So that fewer runs replace a waiting one, a conversation comment waits only when it names the reviewer (`@ironbee-ai`,
or `@<app-slug>` under your own App); one that names someone else runs on its own and ends at the decide step.

Two things the calling file must hold:

- **`actions: write`** in its `permissions`, for the re-run. Without it that last step fails, naming the permission.
- **The review's job alone.** A re-run starts every job of a run again, so a run whose file also builds, tests or
  deploys is not started again; the step's log says so, and the head waits for a push, a re-run or
  `@ironbee-ai review`.

### Enterprise Cloud on github.com

Nothing changes in the workflow. What your enterprise's policies ask of it:

- **An IP allow list.** GitHub accepts the job's token only from runners whose address is on the list: run the job on
  your own runners or on GitHub's larger runners with static addresses, and put their addresses on the list.
- **Workflows from outside not allowed.** Keep a copy ([A copy of this repository](#a-copy-of-this-repository)).
  Under Enterprise Managed Users your organizations hold private and internal repositories only, so the copy is one of
  those, and needs `runner-token`.
- **Only the enterprise's own actions and workflows allowed.** That policy also blocks the actions GitHub authors,
  which the workflow names: `actions/checkout` and `actions/create-github-app-token`, both fetched for every run. Choose
  **Allow enterprise, and select non-enterprise, actions and reusable workflows** with **Allow actions created by
  GitHub**, and keep the copy. A copy of GitHub's actions does not serve: the workflow names them under `actions/`.
- **A repository a managed user owns** (its owner's login ends in `_<short code>`) is not served: IronBee refuses its
  path.

### With IronBee's CLI on these hosts

`ironbee runner setup`, `add` and `check` take the host from the clone's remote, or from `--host github` with your
`GH_HOST`. Off github.com they also need `--component <owner>/<name>@<tag>`, your copy and its release, and on a server
`--runs-on`. They ask for `runner-token`, which they store as `IRONBEE_RUNNER_TOKEN`, an Actions secret and a
Dependabot secret, and write the file your host needs: the workflow file of the table above, `runner-repository`,
and with the workflow without a queue, `actions: write`. `check` also reads your copy's visibility and Actions access,
and says when a file that calls the workflow without a queue lacks `actions: write` or holds other jobs.

## Next

- [Identity](identity.md): run the reviewer as your own GitHub App instead of the job token.
- [The review file](review-file.md): adjust each task's model and effort, and a closed list of settings.
- [Settings and rules](settings-and-rules.md): keep rules for all your repositories in a repository of your own.
- [The `Code Review Result` check](required-check.md): how it concludes, and how to make it required.
