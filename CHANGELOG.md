# Changelog

What each release changes for you. Read every entry between your release and the one you move to
([Versions](docs/versions.md#moving-to-another-release)). A release's page on GitHub names its image by digest and how
to verify it ([Verifying the image](docs/verifying-the-image.md)).

## 1.1.0

- **IronBee's API serves 1.1.0 and later.** A run or a registration of 1.0.0 is refused (`RUNNER_VERSION_UNSUPPORTED`):
  nothing is reviewed, and a pull request's event leaves a `neutral` check that says to move the workflow to 1.1.0. Move
  `uses:` to `@v1.1.0` or `@v1`; nothing else in your workflow file changes. 1.0.0 stopped inside major version 1 and
  without a dated notice ([Versions](docs/versions.md#when-a-version-stops-being-served)).
- **The profiles are renamed** `self-hosted-quick`, `self-hosted-standard` and `self-hosted-deep`, from
  `ironbee-self-hosted-<depth>`. The job's log (`profile self-hosted-standard, classifier llm`) and the `profile` of the
  run's report ([What reaches IronBee](docs/what-reaches-ironbee.md#complete-post-v1code-review-runsidcomplete)) name
  the new one. No input, secret or key of the [review file](docs/review-file.md) is renamed.
- **An account whose code review is turned off in the console is refused** (`CODE_REVIEW_DISABLED`), at the
  registration and at every run: nothing is reviewed, and the `neutral` check says to turn it on
  ([Troubleshooting](docs/troubleshooting.md#ironbee-refused-the-run-or-could-not-be-reached)).
- **The reviewer.** An answer the model cut short, at its output limit or, on Claude, at its context window, is no
  longer taken as a finished one: the review keeps the findings it holds and is posted as partial. On
  `model-provider: openai`, a broken or unfinished stream is sent again as a failed attempt, a tool call with malformed
  arguments is answered as not run, and a retry waits at least the server's `retry-after`.

## 1.0.0

The first release.
