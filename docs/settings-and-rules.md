# Settings and rules

A self-hosted run takes its settings and the team's rules from the IronBee console, as IronBee's cloud product does:
each run asks IronBee for them when it starts. Rules and memories can also live with you, in the reviewed repository
and in a rules repository that serves all your repositories. Each task's model and effort, and a closed list of the
reviewer's settings, are adjusted in [the review file](review-file.md).

## The console's settings on a self-hosted run

| Setting | On a self-hosted run |
|---|---|
| `depth`, `focusAreas`, `extraChecks`, `commentOn`, `language` | apply |
| `suggestedFixes`, `diagrams`, `summary` | apply |
| `mergeBlock` | applies, through the `Code Review Result` check ([the check](required-check.md)) |
| `answerQuestions` | applies, with the cloud's meaning: questions asked in reply to one of the reviewer's comments |
| `closeFixedThreads` | applies where the token may resolve threads ([Setup](setup.md#resolving-threads)) |
| `autoReview`, `reviewDrafts`, `reviewBotPullRequests` | apply, evaluated by the runner |
| `ignorePaths`, `targetBranches`, `skipLabels`, `skipTitleKeywords` | apply. They exist per repository only: from the repository's project in the console, and from the workflow's inputs for a repository left without one ([Setup](setup.md#a-repository-left-without-a-project)) |
| `repositoryKnowledge` | applies: the switch of the reviewed repository's own `.ironbee/` rules, memories and skills |
| reviewer settings IronBee sets for a project | apply, where there is a project |
| the console's rules and memories | the account's and the repository's project's apply |
| your rules repository | applies when the workflow names one ([below](#the-rules-repository)) |
| the review file | applies when the rules repository or the repository holds one ([the review file](review-file.md)) |
| `learnFromReactions` | this pull request's reactions, replies and resolved threads are read each round; nothing is kept for other pull requests |
| `blockMerges` | does not apply: GitLab's alone |
| `autoEnableNewRepositories` | does not apply: a repository is reviewed when it has the workflow |

A repository's project is an ordinary project of the console: its four per-repository settings and its overrides of
the account's are edited on its page, and its rules and memories in the knowledge pages. The project's own on/off
switch belongs to IronBee's cloud product and is not read by a self-hosted run. Two repositories of one name under
different owners, neither of them connected to IronBee's cloud product, share one project.

### The gates

The runner evaluates the team's gates against the pull request itself, and tells IronBee only the code of the gate
that stopped a run: the title, the labels and the branches are never sent.

| Setting | Stops | Code |
|---|---|---|
| `autoReview: asked` | every review an open or a push started | `asked_only` |
| `autoReview: open` | a review a push started | `open_only` |
| `reviewDrafts` off | a draft | `draft` |
| `reviewBotPullRequests` off | a bot author's own open or push | `bot` |
| `targetBranches` | a pull request whose target branch matches none | `target_branch` |
| `skipLabels` | a pull request with a matching label | `skip_label` |
| `skipTitleKeywords` | a pull request whose title holds one | `skip_title_keyword` |
| — | a pull request from a fork | `fork` |

A review someone asks for by a command passes every gate but `fork`, as in the cloud. A gated run posts nothing; on a
new head its pull request gets a `neutral` check that says why ([the check](required-check.md)).

The workflow's four per-repository inputs take one entry a line, blank lines skipped. In `target-branches` a `*`
matches within one path segment of a branch's name and `**` across segments. `skip-labels` match a label in any case.
A `skip-title-keywords` entry matches anywhere in the title, in any case, but where it starts or ends with a letter or
a digit, not inside a longer word.

## Where a team's rules and memories can live

Three places. The reviewer reads all three the same way, and none overrides another:

| Place | Kept by | Applies to |
|---|---|---|
| the console's rules and memories | IronBee | the account's repositories, or one project's |
| the reviewed repository's own `.ironbee/` files (rules, memories, skills) | you, in that repository | that repository, while `repositoryKnowledge` is on |
| the rules repository's `.ironbee/` files | you, in a repository of your own | every repository whose workflow names it |

The reviewed repository's own files are read at the pull request's base, not its head. A team that wants IronBee to
hold none of its rules writes nothing in the console and uses the two others.

## The rules repository

A repository of yours whose `.ironbee/` rules, memories and skills apply to every repository whose workflow names it.

```yaml
    with:
      model-provider: anthropic
      knowledge-repository: acme/review-rules   # owner/name, on github.com
      knowledge-ref: main                       # a branch or a tag; its default branch when not given
    secrets:
      # ...
      knowledge-token: ${{ secrets.IRONBEE_RULES_TOKEN }}   # see "The credential" below
```

- **When it is read.** When a run starts, the runner fetches the ref's head and nothing of it is run. The files are
  read at that head whatever the pull request is, so a change to the rules takes effect at the next run of every
  repository.
- **How.** In the format, with the path scopes and under the caps of a repository's own `.ironbee/` files.
- **A source of its own.** An item's id carries the rules repository before its path, so a file of the same path in
  the reviewed repository is another item, and both apply. Where a comment cites one of its rules, the link goes to
  the rules repository at the commit read. A line about files left out names the rules repository. Its files are read
  whatever the reviewed repository's `repositoryKnowledge` says: that switch is the reviewed repository's own files'
  alone.
- **The credential.** Under the job token: the job token cannot read another private repository, so you give a
  read-only token for the rules repository as the secret `knowledge-token`; a public rules repository needs no token.
  Under your own GitHub App: whenever no `knowledge-token` is given, the runner reads the rules repository with the
  App's installation token, so install the App on the rules repository, even a public one, or give a
  `knowledge-token`, which is then used in the App's place.
- **When it cannot be read** (the token, the ref, the network), the review goes on without it. The job's log warns:

  ```
  warning: the rules repository acme/review-rules could not be read (<how>): <why>; the review goes on without it
  ```

  and the review's body says in one line that the shared rules could not be read, so that a team sees why a rule did
  not apply.
- **IronBee is sent none of its rules.** The counts a run sends cover the console's rules and memories alone, by
  their ids ([What reaches IronBee](what-reaches-ironbee.md)).

The rules repository can also hold [the review file](review-file.md), which then applies to every repository that
names it.
