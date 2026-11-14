# Identity: the job token or your own GitHub App

The reviewer reads the repository and writes its comments and the `IronBee review` check with one identity. By
default that is the job token GitHub gives every workflow job (`GITHUB_TOKEN`): there is nothing to create. You may run
it as a GitHub App of your own instead. IronBee holds neither credential.

| | The job token (default) | Your own GitHub App |
|---|---|---|
| What you set up | nothing | a GitHub App, installed on the repository; its id and private key as the secrets `app-id` and `app-private-key`, and its slug as the input `app-slug` |
| The reviewer's token | the job's own; it ends with the job | minted by the reviewer from the App's key, and again near the end of its hour |
| The check's token | the job's, in all three jobs that write the check | an installation token of the App with `checks: write`, minted in the step that writes the check and nowhere before it |
| Permissions | `contents: read`, `pull-requests: write`, `checks: write`, `issues: read`, in the workflow file | the same, on the App: Contents read, Pull requests read and write, Checks read and write, Issues read |
| Comments and the check appear as | `github-actions[bot]`, "GitHub Actions" | your App |
| People address it as | `@ironbee-ai`: text the reviewer matches, the only name it answers to, and the name its own texts use | `@<your App's slug>`, a real mention |

To resolve threads, add `contents: write`: to the workflow file under the job token, and to the App under your own
App ([Setup](setup.md#resolving-threads)).

## The job token

The job token's identity is `github-actions[bot]`, which nobody would address, so under it the reviewer answers to
`@ironbee-ai` alone: `@github-actions` is never a command. Other workflows also write as `github-actions[bot]`. The
reviewer tells its own texts by its marker beside the author, and looks only at check runs of its own identity;
[The `IronBee review` check](required-check.md#what-the-check-is-worth) says what that is worth.

## Your own GitHub App

1. Create a GitHub App with the permissions in the table above, and install it on the repositories it reviews. If
   the workflow names a rules repository, install the App there too, even when it is public: with no
   `knowledge-token` given, the App's token reads it
   ([Settings and rules](settings-and-rules.md#the-rules-repository)).
2. Generate a private key for it.
3. Store the App's id and the private key as Actions secrets, and pass them with the App's slug:

   ```yaml
   jobs:
     ironbee:
       uses: ironbee-ai/ironbee-github-runner/.github/workflows/code-review.yml@v1.0.0
       with:
         model-provider: anthropic
         app-slug: acme-review           # your App's slug: the name people call it by
       secrets:
         ironbee-api-key: ${{ secrets.IRONBEE_API_KEY }}
         registry-token: ${{ secrets.IRONBEE_REGISTRY_TOKEN }}
         model-key: ${{ secrets.ANTHROPIC_API_KEY }}
         app-id: ${{ secrets.IRONBEE_APP_ID }}
         app-private-key: ${{ secrets.IRONBEE_APP_PRIVATE_KEY }}
   ```

The three go together. The workflow's first job fails, and writes no check, when `app-id` or `app-private-key` is
given without the slug, and when the slug is given without both of them in a run that has its secrets; a run
without its secrets, such as a Dependabot pull request's, then ends quietly with no check
([Troubleshooting](troubleshooting.md#your-own-apps-three-inputs)).
The slug is an input because the workflow's first job must know the name people call the reviewer by before it may
hold the key. The runner checks it against the App, and a slug that is not the App's is refused as a configuration
error.

What changes under your own App:

- Comments and the check are your App's, out of the identity every other workflow shares. The App's key is still a
  secret that a workflow on a branch can read ([what the check is worth](required-check.md#what-the-check-is-worth)).
- People mention the App, which is a real GitHub mention.
- The App's own replies raise events as a person's do. The workflow ends every event whose comment a bot wrote, so
  the reviewer never starts itself.

## Dependabot

GitHub runs the workflows of Dependabot's pull requests without the repository's Actions secrets, unless you give
Dependabot secrets of its own. Such a run reviews nothing, and its check depends on the identity:

- **Under the job token,** the pull request gets a `neutral` check, which passes a required check.
- **Under your own App,** there is no key to write a check with, so the pull request gets none. Where `IronBee review`
  is a required check, give Dependabot the App's id and key, as Dependabot secrets under the names your workflow file
  reads, so that its pull requests get their `neutral` check.

To have Dependabot's pull requests reviewed, give Dependabot the other secrets too. A pull request a bot opened is
then still skipped unless the team's `reviewBotPullRequests` setting is on; skipped, it gets a `neutral` check.
