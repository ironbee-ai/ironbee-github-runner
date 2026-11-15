# Models

The model is yours: your Claude or OpenAI account, or a model you host. A model call never goes to IronBee. You
choose the provider and the endpoint in the workflow; the profiles choose which model does each kind of call, and you
can change that in the workflow (one model for everything) or in the [review file](review-file.md) (task by task).

## The provider and its endpoint

| `model-provider` | Endpoint without `model-url` | With `model-url` | The key (`model-key`) is sent |
|---|---|---|---|
| `anthropic` | `https://api.anthropic.com` | the API's base: a gateway, or a private endpoint | in `x-api-key` |
| `bedrock` | `https://bedrock-runtime.<aws-region>.amazonaws.com` | the endpoint Bedrock's requests go to in place of the region's | as `Authorization: Bearer`; a Bedrock API key |
| `openai` | `https://api.openai.com/v1` | any server that speaks OpenAI's chat-completions API: a gateway, a private endpoint, or the server of a model you host | as `Authorization: Bearer` |

An open-weight model you host is the `openai` provider with your server's URL in `model-url` and its model's name in
`model-name`.

Where the model is reached, and with which credential, is only what these inputs say. The runner ignores the
`ANTHROPIC_*` and `AWS_*` variables of the job's environment, and never uses credentials of the machine it runs on: on
`bedrock` this release takes a Bedrock API key, not a role's credentials.

## Inputs and secrets

| Input or secret | Meaning |
|---|---|
| `model-provider` | `anthropic`, `bedrock` or `openai`. Required |
| `model-url` | the endpoint, when it is not the provider's public one (above) |
| `model-key` (secret) | the key, sent the provider's own way (above). For `bedrock`, a Bedrock API key, with `aws-region`. **Required at a provider's own endpoint. Optional with `model-url`:** an endpoint of your own may take its credential in a header of its own (`model-headers`) or need none. Without a key, the runner sends no credential header of its own |
| `model-headers` (secret) | extra headers for every request to the model's endpoint: what a gateway or a server of yours asks for beside the key (below) |
| `model-ca-certificate` | the certificates of a private authority, in PEM (below). An input, not a secret: a certificate is public |
| `model-name` | one model's name, which then does every task. Optional on `anthropic`, on `bedrock`, and on `openai` at OpenAI's own endpoint, where the profiles name the models. **Required on `openai` with `model-url`** |
| `model-prefix` | `bedrock` only: the inference profile prefix put before a model's name to make Bedrock's model id. `global.anthropic.` (the global inference profile) when not given; give another for a region-bound profile |
| `model-max-output` | the most output tokens a turn may ask for, a whole number, when your model's or your server's limit is under the reviewer's own ([What a model must support](#what-a-model-must-support)) |
| `aws-region` | the Bedrock region. **Required on `bedrock`**, with or without `model-url` |

### `model-headers`

One header a line, written `name=value`:

```
X-Gateway-Tenant=acme
Authorization=Bearer abc123
```

- A line is cut at its first `=`; the name and the value are trimmed. Blank lines are skipped. A line that is neither
  blank nor a header (an HTTP header name, then `=`, then printable ASCII) is a configuration error, which names the
  line's number and never its text.
- The headers are sent with every request to the model's endpoint, and to that endpoint alone: a redirect to another
  address gets none of them, and no key.
- A header of a name the runner sets itself replaces the runner's. With no `model-key`, the runner sends no
  credential header of its own, and a header of that name among yours (such as `Authorization`) still goes.
- Their values are in no log, in neither body sent to IronBee, and in no error text. Store them as a secret.

### `model-ca-certificate`

For an endpoint whose certificate your own certificate authority signed. Give the authority's certificates in PEM.
They are trusted, beside the system's own, for connections to the model's endpoint and for no other connection of
the run.

```yaml
    with:
      model-provider: openai
      model-url: https://llm.internal.acme.example/v1
      model-name: my-model
      model-ca-certificate: |
        -----BEGIN CERTIFICATE-----
        ...
        -----END CERTIFICATE-----
```

### Configuration errors

Each of these stops a run before anything is read. The job's log names the input (`error: <input>: <why>`), the run
reports `failed` / `configuration` to IronBee, a pull request's event leaves a `neutral` check on a head that has no
check and no review of the reviewer's yet, and the runner exits with 2:

- no `model-key` without `model-url`;
- `openai` with `model-url` and no `model-name`;
- a `model-name` that is not 1 to 200 letters, digits and `. _ : / @ -`;
- a line of `model-headers` that is neither blank nor a header's `name=value`;
- a `model-ca-certificate` with no certificate in it;
- a `model-provider` other than the three;
- `bedrock` without `aws-region`, or with one that is not a region's name;
- a `model-max-output` that is not a whole number of 1 or more.

## Tasks and the model each calls

The reviewer makes eleven kinds of model call, its **tasks**. For each, the profile of each depth names a model and an
effort:

| Task | The call | Model | Effort: quick / standard / deep |
|---|---|---|---|
| `read.correctness` | the first reading of the hunks routed to correctness | `claude-sonnet-5-5` | medium / high / xhigh |
| `read.security` | the same, for security | `claude-sonnet-5-5` | medium / high / xhigh |
| `read.editorial` | the same, for editorial | `claude-sonnet-5-5` | low / low / medium |
| `read.minor` | the reading of the file classes read cheaply (tests and docs on quick, none on the others) | `claude-sonnet-5-5` | low / medium / medium |
| `read.second` | the second reading of the priority hunks (on deep alone) | on deep `claude-opus-5-5`; on the others empty | on deep xhigh; on the others empty |
| `follow_up` | what became of an earlier finding whose code changed | `claude-opus-5-5` | high |
| `answer` | the answer to a question on one of the reviewer's threads | empty | empty |
| `converse` | the answer to words addressed to the reviewer in the conversation | empty | empty |
| `summary` | the summary | `claude-sonnet-5-5` | medium |
| `translate` | texts put into the review's language | `claude-sonnet-5-5` | low |
| `classify` | the classifier's questions, without a Jev key ([Jev](jev.md)) | `claude-sonnet-5-5` | low |

No planner model is called: the hunks are routed among the reading tasks by the classifier's answers.

**An empty task takes another task's values.** `answer` and `converse` take `follow_up`'s. `read.second` on quick and
standard takes the values of the reading task that owns the hunk (`read.correctness`, `read.security` or
`read.editorial`). This holds for the model and for the effort separately, with whatever values the other task ends
up with.

**Which model a task calls** is the first of these that is given:

1. the [review file](review-file.md)'s model for that task;
2. the workflow's `model-name`, for every task that is not empty;
3. the profile's: the Claude model of the table, and on `openai` at OpenAI's own endpoint its counterpart there,
   `gpt-5.6-terra` for `claude-sonnet-5-5` and `gpt-5.6-sol` for `claude-opus-5-5`.

A task's effort is the review file's, else the profile's. So on Claude or on OpenAI's own models you set nothing; with
a model of your own you set `model-name`; and with two models you name the second in the review file for the tasks it
should do. With one model for every task, the deep profile's second reading is a second reading by that same model,
where the profile means another model's.

A name goes to the provider as it is written. On `bedrock` the prefix comes first: `claude-sonnet-5-5` is called as
`global.anthropic.claude-sonnet-5-5` with the default prefix.

The depth (quick, standard or deep) is the team's `depth` setting in the console. On Auto, the runner picks it from
the size of the change, and a review read lighter than standard says so in a note.

## What a model must support

| Need | Why | If missing |
|---|---|---|
| Tool calling (function calling) | the reviewer's read tools in the readings, the follow-up reading, the summary and the answers | not supported in this release |
| An output budget on top of the prompt: 32,000 tokens a turn, and 128,000 for any call at the `xhigh` effort on `anthropic` and `bedrock` (the deep profile's readings, or a task the review file sets to `xhigh`) | the runner asks for it on every turn and does not lower it when a model refuses it | every call is refused. `model-max-output` lowers it to what your model or server allows |
| A context that holds one reading call, and one classifier question with its state of up to 32,000 tokens | a block of up to a thousand changed lines, its related code and the tool reads; a hunk and its routing questions | calls fail, their hunks stay unread, and the review is partial. The review file can make a reading call smaller (`reader.chunk.block_lines`, `reader.chunk.dependency_lines`) |
| Streamed chat completions with usage in the stream (`openai`) | the runner streams, and counts a call from its usage | the run works; the counts sent to IronBee miss those calls and their tokens |

Structured output, thinking and prompt caching are used where the model has them, and are not required. An effort a
model refuses is dropped, and the call goes on without it.

Which models were measured, and what a measurement says, is in [Supported models](supported-models.md).
