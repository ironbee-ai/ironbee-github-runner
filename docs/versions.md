# Versions

The workflow and the image it runs share one version, `MAJOR.MINOR.PATCH`. A release is tagged `v<version>`, and its
workflow names its image by digest. A release holds two workflow files, `code-review.yml` and
`code-review-no-queue.yml` for a host whose Actions keep one waiting run ([Setup](setup.md#a-host-without-a-queue)):
the same release, the same image. What follows the `@` in your workflow file's `uses:` picks what you run:

| `uses: …/code-review.yml@` | What you run | When it changes |
|---|---|---|
| `v1.0.0` | that release | never: a release's tag is never moved |
| `v1` | the newest release of major version 1 | at each release of 1.x, with nothing to change on your side, since within a major version nothing you set is renamed or removed |
| `<commit id of a release>` | that release, without relying on a tag's word | never: the commit names the image by digest too |

**Pre-releases.** Tags of the form `v<version>-rc.<N>` are builds for IronBee's own tests before the release
`v<version>`, marked as pre-releases on GitHub and not for production. `v0` follows the newest of every release and
pre-release, for IronBee's own demos; name a release or `v<MAJOR>` in production. Their images
are verified the same way, by the digest their workflow file names ([Verifying the image](verifying-the-image.md));
one that does not verify with the key in this repository was signed for IronBee's own tests.

A release named exactly stays in your workflow file until you move it. Meanwhile IronBee's side changes, and the
release you are on keeps working: every change on IronBee's side is tested against each version still served.

**Going back from a release to a pre-release is not supported.** From `v1.0.0` a review that holds the merge concludes
`action_required`; the pre-releases `v1.0.0-rc.1` and `-rc.2` wrote `failure` and know no other word for it, so one of
them run on a pull request a release reviewed would not take that check for a review's: the second look after its
`neutral` could turn it `neutral`, and its retract would leave it as it is. A release reads the pre-releases' `failure`, so moving forward is safe.

## What a version's number tells you

| Part | Raised when | What it means for you |
|---|---|---|
| **MAJOR** | a release would break you if you only moved the tag: an input or a secret renamed or removed, a permission your workflow file must newly grant, a model provider or a setting no longer served, a task or a key of the [review file](review-file.md) renamed, removed or given another meaning; or the format of the state the reviewer keeps in its comments raised | read the release notes before you move: they say what you must change |
| **MINOR** | something is added without breaking: a new optional input, a new feature | move by changing the tag |
| **PATCH** | a fix, and nothing else | move by changing the tag |

Within a major version:

- **Inputs and secrets keep their names.** None is renamed or removed, and a new one is optional.
- **The review file keeps its meaning.** No task and no setting key is renamed, removed or given another meaning, and a
  new one is optional. A release that does not know a key leaves it out and says so, so one file in a rules repository
  serves repositories on different releases.

The release notes say what a customer must change, the [model table](supported-models.md) included.

## Moving to another release

Change the tag (or the commit) in `uses:`, after reading the release notes of every release in between
([CHANGELOG.md](../CHANGELOG.md)). You may move in the middle of a pull request: a later release reads the state an
earlier one wrote in the pull request's comments, and the rounds go on.

Moving back across a change of that state's format (which only a major release makes) leaves the pull requests the
newer release wrote unreviewed until you move forward again. Such a run writes nothing on the pull request, ends as
skipped (`newer_state`), says in the job's log to move the workflow's version forward, and leaves a `neutral` check:

```
A newer release of the IronBee runner wrote this pull request's state: move the workflow to that release or a later one to review it.
```

## When a version stops being served

Service ends by major version, never inside one, and with a dated notice. How long a major version is served is not
fixed yet.

- **The notice.** Every version of a major is given the same last day, together with the version to move to. From the
  day it is set, every run and every registration of such a version prints one warning line in the job's log, naming
  the day and the version:

  ```
  warning: runner 1.1.0 is served until 2028-06-30; move the workflow to 2.0.0 before then
  ```

  The run goes on as before.
- **After the last day**, every run and every registration of that version is refused (`RUNNER_VERSION_UNSUPPORTED`):
  nothing is reviewed, a pull request's event leaves a `neutral` check that says to update, and no merge is held. A
  run already started completes.

  ```
  This version of the IronBee runner is no longer served; move the workflow to 2.0.0.
  ```

- The release in this repository and its image in the registry stay where they are, pullable and unchanged, until the
  version's last day.

**The one exception** is a release that must not run at all, for a fault that would harm its users. That version alone
is stopped at once: its refusal carries the reason, which the runner prints in the job's log and states in its
`neutral` check, and its customers are told directly. The other versions inside their time go on.

**1.0.0 is no longer served.** Release 1.1.0 renamed the profiles a run reports, which 1.0.0 cannot follow, so 1.0.0
stopped inside major version 1 and without a dated notice. Its runs and registrations are refused
(`RUNNER_VERSION_UNSUPPORTED`) and told to move the workflow to 1.1.0.
