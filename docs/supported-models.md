# Supported models

> **To be updated.** This page gives the measurements made so far. Follow-up rounds have not been measured end to
> end yet, and the classifier's routing bars and its material bar (below) are being measured again under the
> classifier's final instruction. The page will be updated with those results, and with each release's notes. Until
> then, read "provisional" as it says.

IronBee's published quality numbers belong to one recipe: its cloud product's, with the Claude models and the Jev
classifier. A self-hosted run without a Jev key puts the classifier's questions to your own model instead
([Jev](jev.md)), and may call other models for the other tasks ([Models](models.md)). So a model is listed as supported
only where it was measured on the self-hosted profiles and the profiles' bars hold for it.

**A model outside this table runs, with no statement about its quality.** The table speaks of the profiles as shipped:
what your [review file](review-file.md) changes is your own.

## The table

| Model | Tasks it was measured in | Measured result | Supported |
|---|---|---|---|
| `claude-sonnet-5-5`, at low effort | `classify`: the routing of the hunks, the material question, the deep profile's priority score, the same-defect and one-fix pair questions, people's replies | [the classifier's questions](#the-classifiers-questions) | **provisional**: its bars are set from these measurements; the routing bars and the material bar are being measured again |
| `claude-sonnet-5-5` | `read.correctness`, `read.security`, `read.editorial`, on the standard profile's first rounds | [first rounds end to end](#first-rounds-end-to-end) | **provisional**, for first rounds |
| `claude-opus-5-5` | `follow_up`, and through it `answer` and `converse`; `read.second` on deep | not measured yet on these profiles | not yet stated |
| The Claude models with your own Jev key | every task, Jev answering the classifier's questions | the recipe IronBee's cloud product runs and measures ([Jev](jev.md)) | the cloud product's statement |
| `gpt-5.6-terra`, `gpt-5.6-sol` (the profiles' counterparts on OpenAI's own endpoint) | not measured yet | — | no statement |
| Open-weight models behind an OpenAI-compatible server | not measured yet; to be chosen with the customers who host one | — | no statement |

## The classifier's questions

Measured with `claude-sonnet-5-5` at low effort as the classifier, beside Jev on the same items.

| Question | Measured on | Jev | The classifier on your model | In the self-hosted profiles |
|---|---|---|---|---|
| Same defect at the same site | 98 hand-labelled pairs of findings (87 repeats, 11 different) | † separates the two at 0.920 (AUC); at the bar 0.6, 65 of 87 repeats caught, 1 of 11 different called a repeat | 0.986; 70 of 87 caught, 0 of 11 | the bar stays 0.6 |
| One fix for findings in two files | 166 hand-labelled pairs (56 one fix, 110 not) | † 0.986; at 0.5, 48 of 56 caught, 3 of 110 wrongly | 0.995; 53 of 56, 0 of 110 | not asked (cost) |
| A reply on the reviewer's thread | 26 hand-written replies with the action wanted | † 26 of 26 as wanted | 26 of 26, on each of three draws | the bars stay 0.85 and 0.90 |
| | 150 real replies to review bots in four open-source repositories, no labels (agreement with Jev, not correctness) | the reference | the same action on 122 (81.3 %), the same most likely class on 140. It closes no finding Jev leaves open; it leaves open, or answers, 8 that Jev closes | |
| Routing a hunk | 1,564 hunks of the benchmark, no labels (agreement with Jev, not correctness) | the reference | at Jev's bars it routes a third fewer readings (security on 112 hunks against 317). At bars of its own: the same skip decision on 98.0 % of hunks, the same owning category on 87.2 %, 1,133 hunks read against 1,130, 1,714 category readings against 1,923 (security on 239 hunks against 317) | correctness 0.4, security 0.3, editorial 0.5, skip 0.7 |
| How material a finding is | 467 findings of one judged benchmark run (443 with a verdict), 262 of them low | separates true from false at 0.670, and among the low ones at 0.526; at its bar 0.4 it lists 117 of the 262 (16 of them true) | 0.641 and 0.515; its scores follow Jev's (rank correlation 0.908) but sit lower, so the bar moves: under 0.2 it lists 76 (10 true), under 0.3 it lists 148 (23 true) | 0.2 |
| The deep profile's priority score | 1,130 read hunks, 194 of them holding a known defect; the top fifth (244) gets the second reading | 105 of the 194 in its top fifth (three calls a hunk, averaged); 0.825 | 113 (one call a hunk); 0.798. Chance is 44; the two top fifths share 62.7 % | one call a hunk |

† Jev's answers on the labelled pairs and on the hand-written replies are the ones recorded when those sets were
labelled, in September 2026, by the Jev version of that time. The cloud's profiles use a later version, which gave the
answers in the rows without the mark.

**How far these go.** The rows with labels (the two kinds of pairs, the hand-written replies, the material question,
the priority score) say how well each classifier answers; the rows without labels say only how often the classifier
on your model decides as Jev does. On the labelled pairs and replies it is level with Jev's recorded answers or ahead
of them. On the material question and on the ranking of the priority score it is a little behind (0.641 against
0.670, 0.798 against 0.825), and with bars of its own it still routes fewer readings than Jev, a quarter fewer to
security. Neither classifier tells a true low finding from a false one (0.526 and 0.515 are a coin's), so the
material bar decides how many low findings become lines in the review's body instead of comments, not which are
right.

## First rounds end to end

The benchmark's 50 pull requests, read once by each recipe with the same Claude models, scored by the benchmark's own
measure with one judge (Claude Opus 5.5). A finding listed in the review's body counts as no finding.

| Recipe | Precision | Recall | F1 | F2 | Comments per pull request |
|---|---|---|---|---|---|
| IronBee's cloud product: Jev routing, Jev's material bar at 0.4 | 31.8 | 67.7 | 43.2 | 55.2 | 7.2 |
| The self-hosted standard profile without Jev: the classifier on `claude-sonnet-5-5` at its own bars, its material bar at 0.2 | 34.1 | 79.7 | 47.7 | 62.9 | 7.7 |

On this draw the self-hosted recipe is not behind the cloud's. It is one draw of each: the two are separate readings
of the pull requests, and how far a second reading by the same recipe moves the score was not measured, so the gap
is not a ranking.

## What it costs you

A classifier call on `claude-sonnet-5-5` at low effort cost between a quarter and four tenths of a US cent. On the
benchmark's pull requests that came to about 8 cents a review for the routing, 2 for the material question, and 9 more
on the deep profile for its score. In all, the self-hosted standard profile's first rounds cost 50 cents a pull
request in model calls, its classifier calls included, where the cloud's recipe cost 39 cents in model calls, Jev's
own price aside. Your costs depend on your pull requests and your provider's prices.

## What is not measured yet

- **Follow-up rounds end to end**, with the follow-up reading on every touched finding, the answers, the remark on a
  fix, and what the missing across-files question lets through.
- The follow-up prescreen and the remark on a fix: there are too few recorded cases of each.
- A message to the reviewer in the conversation.
- How steady an answer is from one call to the next. Only the hand-written replies were asked more than once, and many
  answers sit at a bar or one step under it.
- OpenAI's models, and open-weight models.

## What differs without Jev

The classifier's answers are a general model's, not a calibrated classifier's. Those bars drop findings silently, so a
model is supported only where they hold for it, and another model needs its own measurement. Two questions are not
asked: whether one fix answers findings in two files (so a follow-up may report again, at its other end, a defect an
earlier round reported), and the follow-up prescreen (so every touched finding gets the follow-up reading, which costs
more model calls). With your own Jev key, a run has the cloud's recipe ([Jev](jev.md)).
