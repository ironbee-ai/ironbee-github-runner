# Verifying the image

Each release's image is signed with a key IronBee holds. The signature is kept in the registry beside the image, with
the image's bill of materials (SPDX). IronBee's public key is in this repository. A release of the workflow names its
image by digest, and its tag is never moved, so the digest you verify is the one your workflow runs.

> **The public key.** IronBee's public key is published in this repository as `ironbee-code-review-runner.pem`
> <!-- PLACEHOLDER: the key's file name and path in this repository are filled in when the key is published. -->
> with the first release. The commands below expect it saved under that name in the current directory.

## What you need

- [cosign](https://github.com/sigstore/cosign) **v3**. An earlier cosign is not supported for these commands.
- Docker with `buildx`.
- Your registry token: the image is private, so reading its signature and its bill of materials needs the same login
  as pulling it.

## The digest

The image's digest is the one the workflow file of your release names, in `.github/workflows/code-review.yml` of this
repository at that release's tag. It is the digest of the image's index, which covers both of its platforms,
`linux/amd64` and `linux/arm64`.

## Verify

1. Log in to Docker Hub with your registry token, under the user name IronBee gave you with it:

   ```sh
   echo "$IRONBEE_REGISTRY_TOKEN" | docker login docker.io --username <user name> --password-stdin
   ```

2. Verify the image's signature by its digest:

   ```sh
   cosign verify --key ironbee-code-review-runner.pem docker.io/<namespace>/<repository>@sha256:<digest>
   ```

3. List the image's platforms and the digest of each:

   ```sh
   docker buildx imagetools inspect docker.io/<namespace>/<repository>@sha256:<digest>
   ```

4. Verify the bill of materials of the platform you run, by that platform's digest from step 3:

   ```sh
   cosign verify-attestation --key ironbee-code-review-runner.pem --type spdxjson docker.io/<namespace>/<repository>@sha256:<platform digest>
   ```

`<namespace>/<repository>` and `<digest>` are as the workflow file names them.

## What the image holds

The reviewer with its profiles, its grammars and its embedding weights; `git`, with no filter or LFS configuration;
`zstd`; and the runner. It holds no key of any kind, and no Node. The reviewer's own Python is compiled to bytecode with
its source files removed, except for its rule files; the prompt texts and the profiles are data and stay as they are,
since they go to your model in any case.

Being able to pull the image entitles you to nothing by itself: every run still asks IronBee whether it may run.
