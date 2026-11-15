# Jev with your own key

The reviewer's stages ask closed questions as they go: which categories a hunk should be read for, how material a
finding is, whether a new finding repeats an earlier one, what a reply on one of its threads asks for, and others. In
IronBee's cloud product a classifier called Jev answers them. On a self-hosted run, by default, your own model answers
them (the `classify` task, [Models](models.md#tasks-and-the-model-each-calls)), and no third party beside your model is
called.

You may bring Jev back for your own runs. Jev's vendor is Typesafe: you open your own account with them and get your
own Jev API key. IronBee is no party to it, and nothing of it passes through IronBee.

## Turning it on

Store the key as a secret and pass it as `jev-key`:

```yaml
    secrets:
      # ...
      jev-key: ${{ secrets.JEV_API_KEY }}
```

With the key set, the classifier's questions go to Jev at its vendor's own endpoint (`api.typesafe.ai`), under your key.
Without it, your model answers them. The run reports which one answered (`classifier`: `jev` or `llm`,
[What reaches IronBee](what-reaches-ironbee.md#complete-post-v1code-review-runsidcomplete)).

## What changes

The profile is the same either way, `ironbee-self-hosted-<depth>`. What depends on the classifier is a small set of
values the profile holds for each: the routing's bars and the material bar, two questions asked of Jev and not of your
model, and how many times the deep profile's priority score is asked. With Jev, each profile resolves to the same
settings as IronBee's cloud product at that depth.

| | Without a Jev key (default) | With your Jev key |
|---|---|---|
| Who answers the classifier's questions | your model, on the `classify` task | Jev, under your account |
| Who sees the code | your model's provider | your model's provider, and Typesafe under your account |
| Quality statement | by [Supported models](supported-models.md), per model | with the Claude models the profiles name: the recipe IronBee's cloud product runs and measures |

Without Jev, two questions are not asked: whether one fix answers a new finding and an open one in another file (so a
follow-up may report again, at its other end, a defect an earlier round reported), and the follow-up prescreen (so
every touched finding gets the follow-up reading, which costs more model calls). The classifier's calls on your model
are your model spend ([Supported models](supported-models.md#what-it-costs-you)).

## What Jev receives

With your key set, Jev's vendor receives, under your account:

- diff hunks;
- the pull request's title and, on the deep profile, the start of its description;
- findings, with the code they quote;
- the push's other changes around a finding;
- what people wrote on the reviewer's threads, and to it in the conversation.

The run connects to Jev's endpoint beside GitHub, your model's endpoint and IronBee's API.
