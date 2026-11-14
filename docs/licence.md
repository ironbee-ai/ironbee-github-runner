# The licence

A self-hosted runner's licence is annual, priced by the number of developers, with unlimited reviews; a run charges no
credits. A trial is a licence with a near end date. The licence lives in IronBee's cloud alone: the runner has no
licence file and keeps nothing of one. Every run asks IronBee when it starts, and prints what the answer tells it.

The console shows the licence in one line on the account's code-review settings page: its state, its end date, and
the month's developers beside the limit.

## The end date

Every licence has an end date. It is good through that day, in UTC.

- **In its last fourteen days** (the end day and the thirteen before it), every run prints one warning line in the
  job's log, and so does the register job:

  ```
  warning: the licence for IronBee's self-hosted review ends soon; renew it to keep pull requests reviewed
  ```

  The line names no date: the log of a public repository is public. IronBee's team is alerted once, so that someone
  talks to you before the licence lapses.
- **After it**, every run and every registration is refused (`SELF_HOSTED_RUNNER_LICENCE_ENDED`). Nothing is
  reviewed, answered or retracted. A pull request's event leaves a `neutral` check that says so:

  ```
  The licence for IronBee's self-hosted review has ended; contact IronBee to renew it.
  ```

  `neutral` passes a required check, so no merge is held. A `failure` an earlier review wrote stays on its head until
  the head moves. The register job fails with the same reason.
- **There is no grace period.** When the licence is renewed, or a trial extended, IronBee moves the date, and nothing
  changes on your side: the next event is reviewed.

## The developer limit

The contract names how many developers a month it covers.

**Who counts.** A developer of a month is a distinct pull-request author among your account's runs of that calendar
month (UTC) that read the change: a review that read the whole change or what changed since the last round, or a
review or a conversation command's run that started and never reported its end. So a review a push started and one a
command asked for both count. A run a gate skipped, one that failed before reading, a review that had nothing new to read, and an answer do
not. Bots count nobody. The author is known to IronBee by the numeric GitHub account id alone
([What reaches IronBee](what-reaches-ironbee.md#start-post-v1code-review-runs)).

**Over the limit, nothing stops.** Reviews go on. While the month's count is above the limit, every run prints one
warning line in the job's log, and IronBee's team is alerted once that month, so that someone talks to you:

```
warning: this account has more developers this month than its licence covers; reviews go on, and IronBee will be in touch
```

Nothing is written on the pull request, and the line names no number of the contract. The numbers are on the
console's licence line.

## Suspension

IronBee can suspend an account's self-hosted use from its side, for example for non-payment or a leaked key. From the
next run on, every run and every registration is refused (`SELF_HOSTED_RUNNER_SUSPENDED`): nothing is reviewed,
answered or retracted, and a run already past its start finishes. A pull request's event leaves a `neutral` check:

```
IronBee's reviews are suspended for this account; contact IronBee.
```

As with an ended licence, no merge is held, and a `failure` an earlier review wrote stays until the head moves:
suspending an account does not clear findings. Lifting the suspension needs nothing on your side.

The runner cannot review without IronBee's answer at its start: the settings, the gates and the rules come from it,
and nothing on your side keeps an earlier answer. So a refusal, or IronBee unreachable, means no review, and a
`neutral` check ([Troubleshooting](troubleshooting.md)).
