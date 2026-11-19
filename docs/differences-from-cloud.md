# What differs from IronBee's cloud product

| | IronBee's cloud product | The self-hosted runner |
|---|---|---|
| Where the code is read | IronBee's cloud | your CI job |
| Model | IronBee's | yours |
| Comments' and the check's author | IronBee's GitHub App | `github-actions[bot]`, or your own GitHub App |
| The check's name | `IronBee review` | `Code Review Result`: a branch rule moving from the cloud requires it instead ([The pre-releases' name](required-check.md)) |
| Starts on | GitHub's webhooks | the workflow's events: a pull request opened or pushed, a comment |
| Follow-up rounds, fixed and dropped tracking | yes | yes |
| Summary, suggested fixes, diagrams, the Auto depth's note | yes | yes |
| Answers on the reviewer's threads, questions and commands to it, retract | yes | yes |
| A reply that turns a finding down | closed at the next review | the same |
| A thread resolved by a person | the check is refreshed at once | recorded by the next review that reads the pull request again |
| An answer that withdraws a finding | the check follows at once | the check follows at the next review, or when `@ironbee-ai review` restates it |
| What the check means | the findings nobody who counts has turned down | the same |
| A gate, or a refused run, on a new head | no status (a gate), or a neutral one | a `neutral` check |
| A head whose check is an `action_required` and that holds no review of the reviewer's (nothing new was read there) | nothing is posted on that head | a short review with no inline comments is posted there first ([The short review](required-check.md#how-it-concludes)) |
| A bot's push onto a person's pull request | starts nothing; the head has no status | reviewed, when the push raises a workflow run |
| A push while an older push's review still waits | the reviews are coalesced | the run that starts first reviews the newest head; the other finds nothing new |
| A pull request closed or merged while its review waited in the queue | the review already queued still publishes | the run ends before it calls IronBee and writes nothing |
| The same defect at its other end in another file, on a follow-up | recognised as one | may be reported again, without a Jev key ([Jev](jev.md)) |
| A release merge | read only where no reviewed pull request brought the change | the same, read from the reviewer's reviews on the merged pull requests themselves |
| An image in what the model writes | posted as written | neutralised |
| Progress while it runs | the check run's title | the workflow job's log |
| Speed of a reaction to a comment | seconds to start | a job start and an image pull first |
| A push onto a pull request with a merge conflict | reviewed | not reviewed until the conflict is gone |
| Per-repository settings | the console | the console, on the repository's project; the workflow's inputs only for a repository left without one |
| Adjusting a profile | IronBee's alone | your [review file](review-file.md): each task's model and effort, and a closed list of settings |
| How a repository gets its project | by connecting it in the console | the workflow registers it, or its first run does ([Setup](setup.md#3-register-the-repository)) |
| Rules and memories you keep | the repository's `.ironbee/` files | those, and a rules repository for all your repositories ([Settings and rules](settings-and-rules.md)) |
| The licence | credits | an end date and a developer limit ([The licence](licence.md)) |
| Learning from reactions across pull requests | yes | no |
| Console: pull requests, findings, summaries | yes | a list of each repository's pull requests and their runs, from counts; no finding or summary text |
| Credits | charged per review | none |
| Hosts | GitHub, GitLab, Bitbucket | GitHub: github.com, GHE.com and GitHub Enterprise Server, a server not reachable from the internet included ([On GitHub Enterprise](setup.md#on-github-enterprise)); no pull requests from forks |

## What the two "no" rows mean for you

- **Learning across pull requests.** In the cloud product, a finding people turn down (a thumbs-down, a "won't fix", a
  resolved thread) becomes a record in IronBee's database, and later reviews of the same repository drop findings that
  resemble it. Those records quote the finding and its code, so IronBee cannot keep them here, and a CI job has nowhere
  of its own to keep them between pull requests. A self-hosted run still honours what people said on the pull request
  it is reviewing; what it cannot do is remember it for the next one. The same kind of finding can come back on another
  pull request until someone writes a rule or a memory for it.
- **The console's pull-request pages.** The cloud product's pages of findings with their code, summaries and each
  job's history are built from what IronBee stores, and each of them holds text from the code. None of it is sent
  here. A team sees its reviews where they are written, on GitHub; the console shows the settings, the rules, and a
  list of each repository's pull requests and runs with their counts.

## What running in GitHub Actions changes

| GitHub's rule | What it means here |
|---|---|
| A fork's pull-request run has a read-only token and no secrets. | No review and no check can be written on a fork's pull request. A repository that takes them cannot make the check required in this release. |
| Workflows do not run on a pull request with a merge conflict. | A push onto a conflicted pull request gets no review and no check until the conflict is gone. |
| No workflow event is raised when a review thread is resolved. | It is recorded by the next review that reads the pull request again. |
| An inline reply's event runs the pull request's own workflow file; a conversation comment's runs the default branch's. | A change to the workflow file on a pull request's branch applies to that pull request's own events and inline replies, and to its conversation comments only once it is on the default branch. |
| A workflow required by an organization ruleset runs for pull-request and merge-group events only. | It cannot carry the two comment events, so the workflow stays a file of the repository. |
| A check belongs to a commit, and a change of a pull request's base raises no event the workflow listens to. | A head reviewed in one pull request, or against one base, keeps its check in another. |
| A push made with a workflow's own token, or whose commit asks to skip CI, raises no workflow event. | That head gets no run of its own. A run already waiting reviews it, since a run reads the head when it starts; otherwise it has no review and no check until the next push or a command. |
