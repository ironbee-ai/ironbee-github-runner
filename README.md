# IronBee code review: the self-hosted runner for GitHub

This repository holds IronBee's reusable GitHub Actions workflow for code review on your own compute, with your own
model. A job in your GitHub Actions runs IronBee's reviewer, from a container image IronBee ships, on your pull
requests: first reviews and follow-up rounds after each push, answers to questions on its threads, and commands
addressed to it in the conversation. It writes its review on the pull request and a check run named `Code Review Result`
that you can make a required check.

- **Your code stays with you.** The repository is cloned and read inside your job. Model calls go from your job to
  your own model: your Anthropic, Amazon Bedrock or OpenAI account, or a model you host behind an OpenAI-compatible
  server.
- **Your settings and rules stay in the IronBee console**, as for IronBee's cloud product. Each run asks IronBee for
  them, and for the licence, when it starts.
- **github.com, GHE.com and GitHub Enterprise Server.** github.com includes GitHub Enterprise Cloud's organizations,
  with their policies and managed users. A GHE.com tenant or a GitHub Enterprise Server (3.19 or later) calls a copy of
  this repository on its own host ([On GitHub Enterprise](docs/setup.md#on-github-enterprise)). Pull requests from
  forks are not reviewed.

## What reaches IronBee

A run calls IronBee's API at most twice, when it starts and when it ends, and registering a repository is a third
call. They carry ids, fixed codes, counts and the names of the models the run called; nothing else. Never your code, diffs, file paths, branch names,
titles, descriptions, labels, commit messages, comments, findings, summaries, prompts, logins or logs. Of the pull
request's author, the numeric GitHub account id is sent, to count your licence's developers. GitHub shows that number
publicly beside the login, and IronBee could look the login up from it.
[What reaches IronBee](docs/what-reaches-ironbee.md) prints the bodies in full.

## Quick start

You need, from IronBee: the self-hosted runner enabled on your account, your account's API key, and a registry token
for the image. From your side: a key for your model.

1. Store three secrets in the repository or its organization: `IRONBEE_API_KEY`, `IRONBEE_REGISTRY_TOKEN` and your
   model's key (here `ANTHROPIC_API_KEY`).
2. Add `.github/workflows/ironbee-review.yml`:

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
       branches: [main]              # your default branch
       paths: ['.github/workflows/ironbee-review.yml']   # this file's own path
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
       secrets:
         ironbee-api-key: ${{ secrets.IRONBEE_API_KEY }}
         registry-token: ${{ secrets.IRONBEE_REGISTRY_TOKEN }}
         model-key: ${{ secrets.ANTHROPIC_API_KEY }}
   ```

3. Commit it. Pushed straight to the default branch, it registers the repository in the IronBee console before any
   pull request. Added by a pull request, that pull request is the first one reviewed.
4. Optionally, make `Code Review Result` a required check. Read [The `Code Review Result` check](docs/required-check.md)
   first: it says what the check is worth. A pull request usually shows it as `IronBee / Code Review Result`, beside
   the workflow's job as `IronBee / Code Review / Job`; the name to require is `Code Review Result`.

The [setup guide](docs/setup.md) explains each step and every input.

## Documentation

| Page | What it covers |
|---|---|
| [Setup](docs/setup.md) | the workflow file, every input and secret, registering a repository, where the job runs, commands |
| [On GitHub Enterprise](docs/setup.md#on-github-enterprise) | GHE.com, GitHub Enterprise Server and its workflow without a queue, a copy of this repository, Enterprise Cloud's policies and managed users |
| [Identity: the job token or your own GitHub App](docs/identity.md) | who the comments and the check are written as; Dependabot |
| [Models](docs/models.md) | the model's inputs and secrets, the tasks and the model each calls, what a model must support |
| [Supported models](docs/supported-models.md) | what was measured, and on which models |
| [Settings and rules](docs/settings-and-rules.md) | the console's settings on a self-hosted run, and a rules repository for all your repositories |
| [The review file](docs/review-file.md) | `.ironbee/review.yaml`: each task's model and effort, and the settings you can adjust |
| [The `Code Review Result` check](docs/required-check.md) | how it concludes, making it required, and what it is worth |
| [What reaches IronBee](docs/what-reaches-ironbee.md) | the bodies sent, what is never sent, what stays with you |
| [The licence](docs/licence.md) | the end date, the developer limit, and what happens past each |
| [Verifying the image](docs/verifying-the-image.md) | the image's signature and bill of materials |
| [Versions](docs/versions.md) | what a version number means to you, and how to move |
| [Jev with your own key](docs/jev.md) | the option, and what it sends to Jev's vendor |
| [What differs from the cloud product](docs/differences-from-cloud.md) | the two products side by side |
| [Troubleshooting](docs/troubleshooting.md) | what you see when something goes wrong, and what to do |

## Versions

Pin an exact release, as above (`@v1.0.0`), or follow the newest 1.x release with `@v1`. A release's tag is never
moved, and it names its image by digest. Within a major version, inputs and secrets keep their names.
[Versions](docs/versions.md) explains the rest.
