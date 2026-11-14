# The review file

`.ironbee/review.yaml` is your own adjustment of the review profiles: the model and the effort of each task, and a
closed list of the reviewer's settings. Every part of it is optional. What it does not name stays as the profile has
it at each depth, and a value it names holds at every depth: no part of the file is for one depth alone.

```yaml
models:                           # a task's model, its effort, or both
  read.security:
    model: claude-opus-5-5
    effort: xhigh
  summary:
    effort: low
settings:                         # a closed list; each key written whole, with its dots
  reader.floor: 5
  models.max_concurrency: 8
```

## Where it is read

The runner reads it for every run, from two places:

- **your rules repository**, when the workflow names one, at the head the run fetched
  ([Settings and rules](settings-and-rules.md#the-rules-repository));
- **the reviewed repository, at the base commit the pull request names**, by one read through GitHub's API with the
  run's token.

Where both give a task's `model`, a task's `effort` or a setting, the reviewed repository's stands, entry by entry.
The file is never read from the pull request's head, so a pull request cannot adjust its own review through it: a
pull request that changes the file is reviewed with the file of its base.

**Where it sits among the layers.** Over the profile, and over the workflow's `model-name`. Under the settings
IronBee returns when a run starts: where IronBee has set one of these keys for the repository's project, its value
stands over the file's. And under the runner's own settings (where the model is reached, posting, and the state the
reviewer keeps on the pull request), which no file can change.

## `models`

A key is one of the eleven tasks ([Models](models.md#tasks-and-the-model-each-calls)): `read.correctness`,
`read.security`, `read.editorial`, `read.minor`, `read.second`, `follow_up`, `answer`, `converse`, `summary`,
`translate`, `classify`.

- `model` is a model's name as your provider knows it: 1 to 200 letters, digits and `. _ : / @ -`. On `bedrock` the
  inference profile prefix is put before it, as for every name.
- `effort` is `low`, `medium`, `high` or `xhigh`.

Either may stand alone. A task whose `model` the file names calls that model whatever `model-name` says. A task
whose model and effort stay empty still takes the other task's values: naming `follow_up` alone changes the answers too, and turning
the second reading on at quick or standard with `reader.priority.passes` reads each priority hunk again with its own
reading task's model and effort, unless the file names `read.second`.

A task's model and effort set what its calls cost you and how long they take. A model that is not the profile's, or
an effort that is not, falls outside the [measured statements](supported-models.md).

## `settings`

These sixteen keys of the reviewer, and no others. Each is written whole, with its dots, directly under `settings:`.

| Key | Takes | quick | standard | deep | What it sets |
|---|---|---|---|---|---|
| `reader.floor` | an integer from 1 to 20, or null | null | 3 | 8 | the least findings a first reading is asked for. The reading is told never to invent one, and the cut (`selector.rank.limit`) never goes under it |
| `reader.max_tool_calls` | an integer of 1 or more, or null | 12 | null | null | the most tool calls one reading call makes; null is no limit. With a number, the reading is also told its budget up front, as on quick |
| `reader.chunk.block_lines` | an integer from 100 to 2,000 | 1000 | 1000 | 1000 | the changed lines one reading call holds |
| `reader.chunk.dependency_lines` | an integer from 0 to 2,000 | 500 | 500 | 1000 | the lines of related code given beside them |
| `reader.priority.passes` | 0, 1 or 2 | 0 | 0 | 1 | the extra readings of the priority hunks (`read.second`). Without Jev, a value above 0 has the score that picks those hunks asked once a hunk, as on deep |
| `reader.minor.classes` | a list of `tests`, `docs`, each once | both | none | none | the file classes read cheaply (`read.minor`). A finding in such a file is never rated above medium, unless a team rule it cites sets a higher severity; but for that, it cannot hold a merge that `mergeBlock: high` holds |
| `reader.timeout` | seconds, 60 to 3,600 | 1800 | 1800 | 1800 | a reading call |
| `selector.rank.limit` | 0; a positive integer; a share (`30%`); a rate (`1/block`, `1/hunk`, `2/file`, `1/50lines`) | 0 | 0 | 0 | how many findings survive the cut; 0 is no cut. The cut never goes under eight findings, nor under what `reader.floor` asked for |
| `selector.rank.over_limit` | `drop` or `summary` | `drop` | `drop` | `drop` | what the cut leaves out: dropped, or listed in the review's body |
| `selector.comment_material` | a number from 0 to 1, or null | 0.2; with Jev 0.4 | the same | the same | the material score under which a low finding is listed in the review's body instead of commented; null comments every low finding |
| `tracker.full_above` | a number from 0 to 1 | 0.75 | 0.75 | 0.75 | the share of the change pushed since the last review above which the whole change is read again |
| `tracker.reading.timeout` | seconds, 60 to 3,600 | 1500 | 1500 | 1500 | a follow-up reading |
| `tracker.answer.timeout` | seconds, 60 to 3,600 | 1500 | 1500 | 1500 | an answer on a thread |
| `tracker.converse.timeout` | seconds, 60 to 3,600 | 1500 | 1500 | 1500 | an answer in the conversation |
| `summarizer.timeout` | seconds, 60 to 3,600 | 900 | 900 | 900 | a summary call |
| `models.max_concurrency` | an integer from 1 to 64 | 16 | 16 | 16 | the model calls in flight at once |

Everything else stays out of reach here: the prompts, the routing's bars, the clustering and ranking of findings, the
follow-up's rules, the backends, and the runner's own settings. What the console sets stays in the console
([Settings and rules](settings-and-rules.md)).

### What each setting trades

| Key | Raised, or set | Lowered, or null |
|---|---|---|
| `reader.floor` | each first reading is asked for more findings: more comments to read, and longer readings | fewer findings asked for; null asks for no number |
| `reader.max_tool_calls` | a number caps a reading's tool calls: its cost and time are bounded, and it sees no more of the code around the change than the cap lets it look up | null: a reading looks up what it needs, at the cost of those calls |
| `reader.chunk.block_lines` | more changed lines in one call: fewer calls, each needing a larger context | more, smaller calls, for a model with a smaller context |
| `reader.chunk.dependency_lines` | more related code beside the change: more context for each reading, more input tokens | less context and fewer tokens; 0 gives none |
| `reader.priority.passes` | extra readings of the hunks most likely to hold a defect, each at the cost of a reading | 0: each hunk is read once |
| `reader.minor.classes` | tests and docs are read with `read.minor`'s model and effort, and their findings capped at medium | tests and docs are read like code |
| the timeouts | slow endpoints and long calls can finish, and a stuck call holds the job longer | the job's time is bounded; a call past its timeout fails, and a reading that fails leaves its hunks unread, named in the review |
| `selector.rank.limit` | a cap: fewer comments; what is past the cap is dropped or listed (`over_limit`) | 0: no cut |
| `selector.rank.over_limit` | `summary`: what the cut leaves out is still listed in the body | `drop`: it is not shown |
| `selector.comment_material` | more low findings listed in the body instead of commented: fewer comments | more low findings commented; null comments every one |
| `tracker.full_above` | a follow-up reads only what changed since the last review unless more of the change is new | a follow-up reads the whole change again more often: more model calls |
| `models.max_concurrency` | more calls at once: shorter runs, more load at once on your endpoint and its rate limits | fewer calls at once: gentler on your endpoint, longer runs |

The material bar decides how many low findings become lines in the body, not which are right: neither classifier
tells a true low finding from a false one ([Supported models](supported-models.md#the-classifiers-questions)).

## What is not applied

- **An entry the schema does not take** is left out, and the rest applies: a part other than `models` and `settings`,
  a task or a setting key the schema does not have, a value it does not take, and a model's name outside the pattern.
- **A file that cannot be read, or that is not a YAML mapping, is left out whole.** A key written twice in one mapping
  makes the file invalid. A file that is not there is no fault, and an empty file sets nothing.

The job's log names each entry left out:

```
warning: review file: .ironbee/review.yaml in this repository settings.reader.floor left out: it must be at most 20
warning: review file: .ironbee/review.yaml in the rules repository left out whole: it is no YAML (ScannerError)
```

and the review's body says in one line that the review file, or a part of it, was not applied; the job's log says
what. That line is shared with the one for a rules repository that could not be read, since the review's body shows
three such notes at most.

## What IronBee learns of it

That a value of it was applied (`customized` in the run's report), and the names of the models the run called.
Nothing else: the file is read by the runner, never by IronBee ([What reaches IronBee](what-reaches-ironbee.md)).

## What is promised

Within a major version no task and no setting key is renamed, removed or given another meaning, and a new one is
optional; a release that does not know a key leaves it out and says so. One file in a rules repository can therefore
serve repositories on different releases of the same major version ([Versions](versions.md)).

What [Supported models](supported-models.md) states is stated of the profiles as shipped. What the review file
changes is your own.
