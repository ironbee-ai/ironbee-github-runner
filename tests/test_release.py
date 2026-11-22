"""The release (scripts/release.sh), step by step, in a repository of its own whose origin is a local one: the inputs and
the names they give, the plan over the tags, the stamp (of the real workflows), the image against a stub registry and
daemon (tests/stubs/docker), the signature against a stub cosign (tests/stubs/cosign), the commit, the tags and the
push, and the GitHub release against the stub GitHub. No network."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest

from support import REPO, ROOT, ScriptTest, StubApi

WORKFLOW = ".github/workflows/code-review.yml"
NO_QUEUE = ".github/workflows/code-review-no-queue.yml"     # made from WORKFLOW, stamped beside it
STAMPED = (WORKFLOW, NO_QUEUE)
IMAGE = "docker.io/ironbeeai/ironbee-code-review-runner"
DIGEST = "sha256:" + "a" * 64                                # the index the release names
OTHER = "sha256:" + "b" * 64                                 # another index
AMD64, ARM64 = "sha256:" + "1" * 64, "sha256:" + "2" * 64   # the index's two platforms' images
KEY = "ironbee-image-signing.pem"
PEM = "-----BEGIN PUBLIC KEY-----\nIronBee's\n-----END PUBLIC KEY-----\n"
TESTS_PEM = "-----BEGIN PUBLIC KEY-----\nIronBee's own tests'\n-----END PUBLIC KEY-----\n"
BOT = "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
GIT = {"GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@example.com", "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@example.com",
       "GIT_CONFIG_NOSYSTEM": "1"}


def index(**platforms) -> dict:
    return {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": d, "platform": {"os": "linux", "architecture": a}}
                          for a, d in platforms.items()]}


def stamped(text: str, digest: str, version: str, tag: str) -> str:
    text = re.sub(rf"(IRONBEE_IMAGE: {re.escape(IMAGE)}@)sha256:[0-9a-f]{{64}}", rf"\g<1>{digest}", text)
    text = re.sub(r"(ref: \$\{\{ job\.workflow_sha \|\| ')[^']*(' \}\})", rf"\g<1>{tag}\g<2>", text)
    return re.sub(r"(IRONBEE_RUNNER_VERSION: )\d+\.\d+\.\d+", rf"\g<1>{version}", text)


def tag_line(text: str) -> str:
    return next(line for line in text.splitlines() if "job.workflow_sha ||" in line)


class Release(ScriptTest):
    def setUp(self) -> None:
        super().setUp()
        self.origin, self.work = self.tmp / "origin.git", self.tmp / "work"
        self.git("init", "--quiet", "--bare", "--initial-branch=main", str(self.origin), cwd=self.tmp)
        self.git("init", "--quiet", "--initial-branch=main", str(self.work), cwd=self.tmp)
        (self.work / ".github" / "workflows").mkdir(parents=True)
        for path in STAMPED: shutil.copy(ROOT / path, self.work / path)
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "the workflow")
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "--quiet", "origin", "main")
        self.registry = {"arch": "amd64", "manifests": {f"{IMAGE}@{DIGEST}": index(amd64=AMD64, arm64=ARM64)},
                         "tags": {f"{IMAGE}:1.0.0-rc.2": DIGEST, f"{IMAGE}:1.0.0": DIGEST},
                         "images": {f"{IMAGE}@{AMD64}": {"os": "linux", "architecture": "amd64", "version": "1.0.0"},
                                    f"{IMAGE}@{ARM64}": {"os": "linux", "architecture": "arm64", "version": "1.0.0"}}}
        self.signed = {f"{IMAGE}@{DIGEST}": [PEM]}

    def git(self, *args, cwd=None) -> str:
        env = {"PATH": os.environ["PATH"], "HOME": str(self.tmp), **GIT}
        return subprocess.run(["git", *args], cwd=cwd or self.work, env=env, capture_output=True, text=True, check=True).stdout.strip()

    def ref(self, name: str, where=None) -> str:
        """The commit a ref names in the origin (or in `where`), or "" when there is no such ref."""
        p = subprocess.run(["git", "rev-parse", "-q", "--verify", f"{name}^{{commit}}"], cwd=where or self.origin, capture_output=True, text=True)
        return p.stdout.strip()

    def refs(self) -> str:
        return self.git("for-each-ref", "--format=%(refname) %(objectname)", cwd=self.origin)

    def tag(self, name: str, digest: str = DIGEST, version: str = "1.0.0") -> None:
        """A tag as a release writes it: a commit on main whose workflows name `digest`, `version` and the tag, tagged and
        pushed."""
        for each in STAMPED:
            path = self.work / each
            path.write_text(stamped(path.read_text(), digest, version, name))
        self.git("commit", "--quiet", "--allow-empty", "-am", f"chore(release): {name}")
        self.git("tag", "-a", name, "-m", name)
        self.git("push", "--quiet", "origin", "main", f"refs/tags/{name}")

    def release(self, step: str, *args, tag: str = "1.0.0-rc.2", digest: str = DIGEST, **env):
        """A step as the workflow runs it: `tag` the image-tag input, `digest` what the digest step read for it."""
        files = {k: self.tmp / k for k in ("docker.json", "docker.calls", "cosign.json", "cosign.calls")}
        files["docker.json"].write_text(json.dumps(self.registry)); files["cosign.json"].write_text(json.dumps(self.signed))
        files["docker.calls"].write_text(""); files["cosign.calls"].write_text("")
        e = {"IRONBEE_IMAGE_TAG": tag, "IRONBEE_IMAGE_DIGEST": digest, "GITHUB_REF": "refs/heads/main",
             "GIT_CONFIG_NOSYSTEM": "1", "STUB_DOCKER_STATE": str(files["docker.json"]), "STUB_DOCKER_CALLS": str(files["docker.calls"]),
             "STUB_COSIGN_STATE": str(files["cosign.json"]), "STUB_COSIGN_CALLS": str(files["cosign.calls"]), **env}
        ran = self.run_script("release.sh", e, args=(step, *args), cwd=self.work)
        self.docker = [json.loads(line) for line in files["docker.calls"].read_text().splitlines()]
        self.cosign = [json.loads(line) for line in files["cosign.calls"].read_text().splitlines()]
        return ran


STEPS = (("digest", ()), ("plan", ()), ("index", ()), ("image", ("amd64",)), ("signature", ()), ("stamp", ()), ("token", ()), ("publish", ()),
         ("github-release", ()))
BY_DIGEST = ("plan", "index", "image", "signature", "stamp", "publish", "github-release")    # the steps after the digest is read


class Inputs(Release):
    def test_the_image_tag_by_its_form(self):
        for tag in ("", "1.0", "v1.0.0", "01.0.0", "1.00.0", "1.0.0-rc", "1.0.0-rc.0", "1.0.0-rc.01", "1.0.0-RC.1", "1.0.0-beta.1", "1.0.0rc.1",
                    "1.0.0-rc.1-rc.2", "1.0.0-rc.1.2", "latest", "1.0.0 ", "1.0.0\n", "1.0.0-rc.1\nx", "1.0.0;id", "$(id)"):
            with self.subTest(tag=tag):
                ran = self.release("digest", tag=tag)
                self.assertEqual(ran.code, 2, ran.out)
                self.assertTrue(ran.out.startswith("::error::image-tag is not MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-rc.<N>"), ran.out)
                self.assertEqual(self.docker, [])

    def test_every_step_checks_the_image_tag_first(self):
        for step, args in STEPS:
            with self.subTest(step):
                ran = self.release(step, *args, tag="1.0")
                self.assertEqual(ran.code, 2, ran.out)
                self.assertIn("image-tag is not MAJOR.MINOR.PATCH", ran.out)
                self.assertEqual((self.docker, self.cosign, ran.calls), ([], [], []))

    def test_the_steps_after_the_digest_step_take_its_digest_by_its_form(self):
        for digest in ("", "a" * 64, "sha256:" + "A" * 64, "sha256:" + "a" * 63, "sha256:" + "a" * 65, "sha512:" + "a" * 64, "sha256:" + "0" * 64):
            for step, args in STEPS:
                if step not in BY_DIGEST: continue
                with self.subTest(digest=digest, step=step):
                    ran = self.release(step, *args, digest=digest)
                    self.assertEqual(ran.code, 2, ran.out)
                    self.assertIn("::error::IRONBEE_IMAGE_DIGEST is ", ran.out)
                    self.assertEqual((self.docker, self.cosign, ran.calls), ([], [], []))
        ran = self.release("token", digest="", IRONBEE_PUSH_TOKEN="")                             # the token's own check, not the digest's
        self.assertIn("IRONBEE_PUSH_TOKEN is not set", ran.out)
        ran = self.release("digest", digest="")
        self.assertEqual(ran.code, 0, ran.out)

    def test_what_comes_from_the_image_tag(self):
        names = {"1.2.3-rc.4": "tag v1.2.3-rc.4, version 1.2.3 (rc.4), floating tag v0",
                 "0.3.0-rc.1": "tag v0.3.0-rc.1, version 0.3.0 (rc.1), floating tag v0",
                 "1.2.3-rc.12": "tag v1.2.3-rc.12, version 1.2.3 (rc.12), floating tag v0",
                 "1.2.3": "tag v1.2.3, version 1.2.3, floating tag v1 and v0",
                 "12.0.10": "tag v12.0.10, version 12.0.10, floating tag v12 and v0"}
        for tag, line in names.items():
            with self.subTest(tag=tag):
                ran = self.release("plan", tag=tag)
                self.assertEqual(ran.code, 0, ran.out)
                self.assertTrue(any(out_line.endswith(line) for out_line in ran.out.splitlines()), ran.out)   # the whole line: nothing after the tag

    def test_major_version_0_is_never_released(self):
        ran = self.release("plan", tag="0.9.0")
        self.assertEqual(ran.code, 2)
        self.assertIn("v0 is the tag of the newest release or pre-release", ran.out)

    def test_the_steps_and_their_arguments(self):
        for args in ((), ("nope",), ("plan", "x"), ("image",), ("image", "amd64", "x")):
            with self.subTest(args):
                ran = self.run_script("release.sh", {"IRONBEE_IMAGE_TAG": "1.0.0", "IRONBEE_IMAGE_DIGEST": DIGEST}, args=args, cwd=self.work)
                self.assertEqual(ran.code, 2)
                self.assertIn("usage: release.sh", ran.out)
        self.assertEqual(self.release("image", "s390x").code, 2)

    def test_the_list_of_workflows(self):
        ran = self.run_script("release.sh", args=("workflows",))
        self.assertEqual((ran.code, ran.out), (0, f"{WORKFLOW} {IMAGE}\n{NO_QUEUE} {IMAGE}\n"))


class Plan(Release):
    def test_a_new_pre_release(self):
        ran = self.release("plan")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("v1.0.0-rc.2 is new", ran.out)
        self.assertNotIn("::notice::", ran.out)

    def test_from_main_alone(self):
        ran = self.release("plan", GITHUB_REF="refs/heads/feat/something")
        self.assertEqual(ran.code, 2)
        self.assertIn("a release runs from main", ran.out)

    def test_a_tag_that_names_another_image_or_version_is_never_moved(self):
        for digest, version in ((OTHER, "1.0.0"), (DIGEST, "0.9.0")):
            with self.subTest(digest=digest, version=version):
                self.setUp()
                self.tag("v1.0.0-rc.2", digest, version)
                ran = self.release("plan")
                self.assertEqual(ran.code, 1, ran.out)
                self.assertIn("v1.0.0-rc.2 exists and names", ran.out)
                self.assertIn("a tag is never moved", ran.out)

    def test_a_run_again_after_its_push(self):
        self.tag("v1.0.0-rc.2")
        ran = self.release("plan")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("::notice::v1.0.0-rc.2 is already pushed with this image and version: this run moves nothing", ran.out)

    def test_a_release_is_never_below_the_newest_one(self):
        self.tag("v1.9.0"); self.tag("v1.10.0")                  # by number, not by text
        ran = self.release("plan", tag="1.9.5")
        self.assertEqual(ran.code, 1, ran.out)
        self.assertIn("v1.9.5 is below the newest release, v1.10.0", ran.out)
        ran = self.release("plan", tag="1.10.1")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("v1.10.1 is new; the newest release is v1.10.0", ran.out)
        self.assertEqual(self.release("plan", tag="1.9.5-rc.1").code, 0)   # a pre-release is not held to it

    def test_pre_releases_and_floating_tags_are_no_release(self):
        self.tag("v2.0.0-rc.1"); self.tag("v3")
        self.git("tag", "-a", "v0", "-m", "v0", "v2.0.0-rc.1^{commit}"); self.git("push", "--quiet", "origin", "v0")   # where a release leaves v0
        self.assertEqual(self.release("plan", tag="1.0.0").code, 0)

    def test_a_released_version_takes_no_more_pre_releases(self):
        self.tag("v1.0.0")
        ran = self.release("plan", tag="1.0.0-rc.3")
        self.assertEqual(ran.code, 1)
        self.assertIn("v1.0.0 is released: it takes no more pre-releases", ran.out)

    def test_a_workflow_the_release_could_not_stamp(self):
        path = self.work / WORKFLOW
        path.write_text(path.read_text().replace("IRONBEE_RUNNER_VERSION", "IRONBEE_VERSION"))
        ran = self.release("plan")
        self.assertEqual(ran.code, 2)
        self.assertIn(f"{WORKFLOW}: the IRONBEE_RUNNER_VERSION line is there 0 times, not once", ran.out)

    def test_the_workflow_without_a_queue_is_what_its_script_makes(self):
        path = self.work / NO_QUEUE
        path.write_text(path.read_text().replace("timeout-minutes: 10\n        shell: bash\n        run: bash .ironbee-github-runner/scripts/restart.sh",
                                                 "timeout-minutes: 30\n        shell: bash\n        run: bash .ironbee-github-runner/scripts/restart.sh"))
        ran = self.release("plan")
        self.assertEqual(ran.code, 2, ran.out)
        self.assertIn(f"{NO_QUEUE} is not what scripts/build-no-queue.sh makes from {WORKFLOW}", ran.out)

    def test_a_tag_that_names_another_tag_is_never_moved(self):
        self.tag("v1.0.0-rc.1"); self.git("tag", "v1.0.0-rc.2", "v1.0.0-rc.1"); self.git("push", "--quiet", "origin", "v1.0.0-rc.2")
        ran = self.release("plan")
        self.assertEqual(ran.code, 1, ran.out)
        self.assertIn("v1.0.0-rc.2 exists and names", ran.out)
        self.assertIn("tag v1.0.0-rc.1: a tag is never moved", ran.out)

    def test_a_run_again_of_a_release_before_the_workflow_without_a_queue(self):
        """The releases to v1.0.0-rc.8 tagged code-review.yml alone, its checkout naming no tag: such a tag of this image
        and version is this release, pushed."""
        main = self.ref("main")
        path = self.work / WORKFLOW
        text = stamped(path.read_text(), DIGEST, "1.0.0", "x")
        path.write_text(text.replace(tag_line(text), "          ref: ${{ job.workflow_sha }}"))
        self.git("rm", "--quiet", NO_QUEUE)
        self.git("commit", "--quiet", "-am", "chore(release): v1.0.0-rc.2"); self.git("tag", "-a", "v1.0.0-rc.2", "-m", "old")
        self.git("push", "--quiet", "origin", "refs/tags/v1.0.0-rc.2")
        self.git("checkout", "--quiet", main, "--", "."); self.git("commit", "--quiet", "-m", "main moves on"); self.git("push", "--quiet", "origin", "HEAD:main")
        ran = self.release("plan")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("::notice::v1.0.0-rc.2 is already pushed with this image and version", ran.out)
        ran = self.release("plan", digest=OTHER)
        self.assertEqual(ran.code, 1, ran.out)
        self.assertIn("a tag is never moved", ran.out)

    def test_a_tag_whose_first_workflow_names_its_tag_and_lacks_the_workflow_without_a_queue(self):
        """Its first workflow is of a release that tags both, so the missing one is no release's doing."""
        main = self.ref("main")
        path = self.work / WORKFLOW
        path.write_text(stamped(path.read_text(), DIGEST, "1.0.0", "v1.0.0-rc.2"))
        self.git("rm", "--quiet", NO_QUEUE)
        self.git("commit", "--quiet", "-am", "chore(release): v1.0.0-rc.2"); self.git("tag", "-a", "v1.0.0-rc.2", "-m", "by hand")
        self.git("push", "--quiet", "origin", "refs/tags/v1.0.0-rc.2")
        self.git("checkout", "--quiet", main, "--", "."); self.git("commit", "--quiet", "-m", "main moves on"); self.git("push", "--quiet", "origin", "HEAD:main")
        ran = self.release("plan")
        self.assertEqual(ran.code, 1, ran.out)
        self.assertIn(f"v1.0.0-rc.2 exists without {NO_QUEUE}: a tag is never moved", ran.out)
        ran = self.release("publish")
        self.assertEqual(ran.code, 1, ran.out)
        self.assertIn(f"v1.0.0-rc.2 exists without {NO_QUEUE}: a tag is never moved", ran.out)

    def test_a_tag_whose_first_workflow_names_its_tag_and_whose_later_one_names_none(self):
        """The later workflow is no stamp of this release, so the tag is refused, not taken as pushed."""
        main = self.ref("main")
        for name in (WORKFLOW, NO_QUEUE):
            path = self.work / name
            path.write_text(stamped(path.read_text(), DIGEST, "1.0.0", "v1.0.0-rc.2"))
        later = self.work / NO_QUEUE
        later.write_text(later.read_text().replace(tag_line(later.read_text()), "          ref: ${{ job.workflow_sha }}"))
        self.git("commit", "--quiet", "-am", "chore(release): v1.0.0-rc.2"); self.git("tag", "-a", "v1.0.0-rc.2", "-m", "by hand")
        self.git("push", "--quiet", "origin", "refs/tags/v1.0.0-rc.2")
        self.git("checkout", "--quiet", main, "--", "."); self.git("commit", "--quiet", "-m", "main moves on"); self.git("push", "--quiet", "origin", "HEAD:main")
        for step in ("plan", "publish"):
            with self.subTest(step=step):
                ran = self.release(step)
                self.assertEqual(ran.code, 1, ran.out)
                self.assertIn(f"v1.0.0-rc.2 exists and its {NO_QUEUE} names no tag: a tag is never moved", ran.out)


class Stamp(Release):
    def test_the_digest_the_version_and_the_tag_and_nothing_else(self):
        for tag in ("1.10.0", "1.10.0-rc.12"):
            for path in STAMPED:
                with self.subTest(tag=tag, path=path):
                    (self.work / path).write_text((ROOT / path).read_text())
                    before = (ROOT / path).read_text().splitlines()
                    ran = self.release("stamp", tag=tag, digest=OTHER)
                    self.assertEqual(ran.code, 0, ran.out)
                    after = (self.work / path).read_text().splitlines()
                    self.assertEqual(len(after), len(before))
                    changed = {a.split(":")[0].strip(): (a, b) for a, b in zip(before, after) if a != b}
                    self.assertEqual(set(changed), {"IRONBEE_IMAGE", "IRONBEE_RUNNER_VERSION", "ref"}, changed)
                    self.assertEqual(changed["IRONBEE_IMAGE"][1].strip(), f"IRONBEE_IMAGE: {IMAGE}@{OTHER}")
                    old, new = changed["IRONBEE_RUNNER_VERSION"]
                    self.assertRegex(new, r"^\s+IRONBEE_RUNNER_VERSION: 1\.10\.0\s+# ")
                    self.assertEqual(new.index("#"), old.index("#"))      # the comment keeps its column
                    old, new = changed["ref"]
                    self.assertEqual(new.split("#")[0].strip(), f"ref: ${{{{ job.workflow_sha || 'v{tag}' }}}}")
                    self.assertEqual(new.index("#"), old.index("#"))
                    self.assertIn(f"stamped {path}: {IMAGE}@{OTHER}", ran.out)
                    self.assertIn(f"tag v{tag} (was ", ran.out)

    def test_the_stamped_workflow_without_a_queue_is_still_what_its_script_makes(self):
        self.assertEqual(self.release("stamp", tag="1.10.0", digest=OTHER).code, 0)
        p = subprocess.run(["bash", str(ROOT / "scripts" / "build-no-queue.sh"), "--check"], cwd=self.work, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout)

    def test_twice_is_once(self):
        self.release("stamp")
        once = [(self.work / path).read_text() for path in STAMPED]
        self.assertEqual(self.release("stamp").code, 0)
        self.assertEqual([(self.work / path).read_text() for path in STAMPED], once)

    def test_another_image_is_left_as_it_is(self):
        path = self.work / WORKFLOW
        other = f"      image: docker.io/acme/other@{OTHER}"
        path.write_text(path.read_text() + f"  other:\n    runs-on: ubuntu-latest\n    container:\n{other}\n")
        self.assertEqual(self.release("stamp").code, 0)
        self.assertIn(other + "\n", path.read_text())
        self.assertIn(f"IRONBEE_IMAGE: {IMAGE}@{DIGEST}", path.read_text())

    def test_a_job_containers_image_line_of_the_releases_before_the_one_job(self):
        """v1.0.0-rc.1 and -rc.2 named the image as a job container's `image:`: a run again of such a release reads it."""
        path = self.work / WORKFLOW
        text = path.read_text().replace(f"IRONBEE_IMAGE: {IMAGE}@", f"image: {IMAGE}@")
        path.write_text(text)
        ran = self.release("stamp", digest=OTHER)
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn(f"image: {IMAGE}@{OTHER}", path.read_text())

    def test_a_line_to_stamp_found_twice_or_never(self):
        text = (ROOT / WORKFLOW).read_text()
        image = next(line for line in text.splitlines() if f"IRONBEE_IMAGE: {IMAGE}@" in line)
        version = next(line for line in text.splitlines() if "IRONBEE_RUNNER_VERSION:" in line)
        held = re.search(r"IRONBEE_RUNNER_VERSION: (\S+)", version).group(1)
        tag = tag_line(text)
        variants = {"the image twice": (text.replace(image, image + "\n" + image), "the image line naming"),
                    "no image": (text.replace(image, ""), "the image line naming"),
                    "the image quoted": (text.replace(image, image.replace("IRONBEE_IMAGE: ", 'IRONBEE_IMAGE: "') + '"'), "the image line naming"),
                    "the image under both keys": (text.replace(image, image + "\n" + image.replace("IRONBEE_IMAGE:", "image:")), "the image line naming"),
                    "a short digest": (text.replace(image, image[:-1]), "the image line naming"),
                    "the version twice": (text.replace(version, version + "\n" + version), "IRONBEE_RUNNER_VERSION line"),
                    "the version quoted": (text.replace(version, version.replace(f": {held}", f': "{held}"')), "IRONBEE_RUNNER_VERSION line"),
                    "the tag twice": (text.replace(tag, tag + "\n" + tag), "the scripts' tag line"),
                    "no tag": (text.replace(tag, "          ref: ${{ job.workflow_sha }}"), "the scripts' tag line"),
                    "the tag not a tag": (text.replace(tag, tag.replace("|| 'v", "|| '")), "the scripts' tag line")}
        for name, (variant, says) in variants.items():
            with self.subTest(name):
                (self.work / WORKFLOW).write_text(variant)
                ran = self.release("stamp")
                self.assertEqual(ran.code, 2, ran.out)
                self.assertIn(says, ran.out)
                self.assertEqual((self.work / WORKFLOW).read_text(), variant)


class Digest(Release):
    def test_the_tag_is_read_once_for_its_digest(self):
        for tag in ("1.0.0-rc.2", "1.0.0"):
            with self.subTest(tag=tag):
                ran = self.release("digest", tag=tag, digest="")
                self.assertEqual(ran.code, 0, ran.out)
                self.assertEqual(ran.outputs, {"digest": DIGEST})
                self.assertEqual(self.docker, [["buildx", "imagetools", "inspect", f"{IMAGE}:{tag}", "--format", "{{json .Manifest}}"]])
                self.assertIn(f"{IMAGE}:{tag} is {IMAGE}@{DIGEST}: the release works by this digest from here on", ran.out)

    def test_the_digest_is_the_one_the_tag_names_now(self):
        self.registry["tags"][f"{IMAGE}:1.0.0"] = OTHER                       # a release's signature then shows whose it is
        ran = self.release("digest", tag="1.0.0", digest="")
        self.assertEqual((ran.code, ran.outputs), (0, {"digest": OTHER}))

    def test_a_tag_not_in_the_registry(self):
        ran = self.release("digest", tag="1.0.0-rc.9", digest="")
        self.assertEqual(ran.code, 1)
        self.assertIn(f"could not read {IMAGE}:1.0.0-rc.9", ran.out)
        self.assertEqual(ran.outputs, {})


class Index(Release):
    def test_both_platforms_by_the_digest_alone(self):
        for tag in ("1.0.0-rc.2", "1.0.0"):
            with self.subTest(tag=tag):
                self.registry["tags"] = {}                                        # the tag is never read again
                ran = self.release("index", tag=tag)
                self.assertEqual(ran.code, 0, ran.out)
                self.assertIn(f"{IMAGE}@{DIGEST}: linux/amd64 {AMD64}, linux/arm64 {ARM64}", ran.out)
                self.assertEqual(self.docker, [["buildx", "imagetools", "inspect", "--raw", f"{IMAGE}@{DIGEST}"]])

    def test_platforms_other_than_the_two(self):
        manifest = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json", "config": {}, "layers": []}
        for held, says in ((index(amd64=AMD64), "holds linux/amd64, not"), (index(amd64=AMD64, arm64=ARM64, s390x=OTHER), "holds linux/amd64 linux/arm64 linux/s390x, not"),
                           (index(amd64=AMD64, arm64=ARM64, arm=OTHER), "holds linux/amd64 linux/arm linux/arm64, not"), (manifest, "holds no platform"),
                           ("not json", "is no image index")):
            with self.subTest(says):
                self.registry["manifests"][f"{IMAGE}@{DIGEST}"] = held
                ran = self.release("index")
                self.assertEqual(ran.code, 1, ran.out)
                self.assertIn(says, ran.out)

    def test_an_index_not_in_the_registry(self):
        ran = self.release("index", digest=OTHER)
        self.assertEqual(ran.code, 1)
        self.assertIn(f"could not read {IMAGE}@{OTHER}", ran.out)


class Image(Release):
    def test_each_platform_runs_on_its_own_architecture_with_no_network(self):
        for arch, digest in (("amd64", AMD64), ("arm64", ARM64)):
            with self.subTest(arch):
                self.registry["arch"] = arch
                ran = self.release("image", arch)
                self.assertEqual(ran.code, 0, ran.out)
                ref = f"{IMAGE}@{digest}"
                self.assertIn(["pull", "--quiet", ref], self.docker)
                [run] = [c for c in self.docker if c[0] == "run"]
                self.assertEqual(run[:run.index(ref) + 1], ["run", "--rm", "--pull", "never", "--network", "none", "--entrypoint", "python", ref])
                self.assertIn(f"{ref}, linux/{arch}, run with no network: its runner reports 1.0.0", ran.out)

    def test_a_runner_of_another_architecture(self):
        ran = self.release("image", "arm64")
        self.assertEqual(ran.code, 2)
        self.assertIn("this runner's docker is amd64, not arm64", ran.out)
        self.assertFalse([c for c in self.docker if c[0] == "pull"])

    def test_a_runner_that_reports_another_version(self):
        self.registry["images"][f"{IMAGE}@{AMD64}"]["version"] = "1.0.1"
        ran = self.release("image", "amd64")
        self.assertEqual(ran.code, 1)
        self.assertIn("runner reports 1.0.1, not 1.0.0", ran.out)

    def test_an_image_of_another_architecture_than_the_index_says(self):
        self.registry["images"][f"{IMAGE}@{AMD64}"]["architecture"] = "arm64"
        ran = self.release("image", "amd64")
        self.assertEqual(ran.code, 1)
        self.assertIn("is linux/arm64, not linux/amd64", ran.out)


class Signature(Release):
    def with_key(self, pem: str = PEM) -> None:
        (self.work / KEY).write_text(pem)

    def test_a_release_verifies_with_the_committed_key(self):
        self.with_key()
        ran = self.release("signature", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual(ran.outputs, {"signature": "verified"})
        self.assertEqual(self.cosign, [["verify", "--key", KEY, f"{IMAGE}@{DIGEST}"]])

    def test_a_release_without_the_key(self):
        ran = self.release("signature", tag="1.0.0")
        self.assertEqual(ran.code, 1)
        self.assertIn(f"{KEY} is missing", ran.out)
        self.assertEqual((self.cosign, ran.outputs), ([], {}))

    def test_a_release_that_does_not_verify(self):
        self.with_key(); self.signed = {f"{IMAGE}@{DIGEST}": [TESTS_PEM]}
        ran = self.release("signature", tag="1.0.0")
        self.assertEqual(ran.code, 1)
        self.assertIn("its signature does not verify with", ran.out)
        self.assertEqual(ran.outputs, {})

    def test_a_pre_release_that_verifies(self):
        self.with_key()
        ran = self.release("signature")
        self.assertEqual((ran.code, ran.outputs), (0, {"signature": "verified"}))
        self.assertNotIn("::notice::", ran.out)

    def test_a_pre_release_signed_for_ironbees_own_tests(self):
        self.signed = {f"{IMAGE}@{DIGEST}": [TESTS_PEM]}
        for key in (PEM, None):
            with self.subTest(key=key is not None):
                if key: self.with_key(key)
                else: (self.work / KEY).unlink(missing_ok=True)
                ran = self.release("signature")
                self.assertEqual((ran.code, ran.outputs), (0, {"signature": "tests"}), ran.out)
                self.assertIn(f"::notice::{IMAGE}@{DIGEST} does not verify with {KEY}: a pre-release signed for IronBee's own tests", ran.out)


class Token(Release):
    """The push's token, before anything is stamped: GitHub's API (a stub) answers `GET /` with the token's scopes in
    x-oauth-scopes for a classic token, and with no such header for a fine-grained one."""

    TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
    OTHER = {"X-GitHub-Request-Id": "AAAA:BBBB", "X-Ratelimit-Remaining": "4999"}       # headers that are never printed

    def token(self, *answers, **env):
        api = StubApi(list(answers)); self.addCleanup(api.stop)
        ran = self.release("token", **{"IRONBEE_PUSH_TOKEN": self.TOKEN, "GITHUB_API_URL": api.url, "NO_PROXY": "*", "no_proxy": "*", **env})
        self.assertNotIn(self.TOKEN, ran.out + ran.err)
        for name, value in self.OTHER.items(): self.assertNotIn(value, ran.out + ran.err)
        return ran, api.requests

    def test_a_classic_token_with_the_workflow_scope(self):
        ran, [req] = self.token((200, {}, {"X-OAuth-Scopes": "repo, workflow, read:org", **self.OTHER}))
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("the push's token may push a workflow file (its scopes: repo, workflow, read:org)", ran.out)
        self.assertEqual((req["method"], req["path"], req["headers"]["authorization"]), ("GET", "/", f"Bearer {self.TOKEN}"))

    def test_a_classic_token_without_it_is_refused(self):
        for scopes in ("repo, read:org", "repo,workflows", ""):
            with self.subTest(scopes=scopes):
                ran, _ = self.token((200, {}, {"X-OAuth-Scopes": scopes, **self.OTHER}))
                self.assertEqual(ran.code, 1, ran.out)
                self.assertIn(f"::error::the push's token lacks the workflow scope (its scopes: {scopes or 'none'})", ran.out)

    def test_a_fine_grained_token_cannot_be_checked_and_goes_on(self):
        ran, _ = self.token((200, {}, self.OTHER))
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("::notice::the push's token names no scopes, as a fine-grained token does: its Workflows permission could not be checked here", ran.out)

    def test_a_token_github_refuses(self):
        ran, _ = self.token((401, {"message": "Bad credentials"}))
        self.assertEqual(ran.code, 1)
        self.assertIn("GitHub refused the push's token (HTTP 401)", ran.out)

    def test_no_token(self):
        ran, reqs = self.token((200, {}), IRONBEE_PUSH_TOKEN="")
        self.assertEqual(ran.code, 2)
        self.assertIn("GH_ACCESS_TOKEN", ran.out)
        self.assertEqual(reqs, [])


class Publish(Release):
    def test_a_pre_release(self):
        base = self.ref("main")
        ran = self.release("publish")
        self.assertEqual(ran.code, 0, ran.out)
        head = self.ref("main")
        self.assertEqual(self.git("rev-parse", f"{head}~1", cwd=self.origin), base)
        self.assertEqual(self.git("log", "-1", "--format=%s|%an <%ae>|%cn <%ce>", head, cwd=self.origin), f"chore(release): v1.0.0-rc.2|{BOT}|{BOT}")
        self.assertEqual((self.ref("refs/tags/v1.0.0-rc.2"), self.ref("refs/tags/v0")), (head, head))
        self.assertIn("tagged v1.0.0-rc.2; v0 moved to it", ran.out)                                     # the step ran to its end
        for tag, message in (("v1.0.0-rc.2", "1.0.0-rc.2: a pre-release for IronBee's own tests"), ("v0", "v0: the newest release or pre-release (v1.0.0-rc.2)")):
            self.assertEqual(self.git("cat-file", "-t", f"refs/tags/{tag}", cwd=self.origin), "tag")     # annotated
            self.assertEqual(self.git("tag", "-l", "--format=%(taggername) %(taggeremail)|%(contents:subject)", tag, cwd=self.origin), f"{BOT}|{message}")
        for path in STAMPED:
            shown = self.git("show", f"v1.0.0-rc.2:{path}", cwd=self.origin)
            self.assertIn(f"IRONBEE_IMAGE: {IMAGE}@{DIGEST}", shown)
            self.assertIn("ref: ${{ job.workflow_sha || 'v1.0.0-rc.2' }}", shown)
        self.assertEqual(self.git("diff", "--name-only", base, head, cwd=self.origin).splitlines(), sorted(STAMPED))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_release_moves_its_major_versions_tag_and_v0(self):
        self.tag("v1.0.0-rc.1"); self.git("tag", "-a", "v0", "-m", "v0"); self.git("push", "--quiet", "origin", "v0")
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        head = self.ref("main")
        self.assertEqual((self.ref("refs/tags/v1.0.0"), self.ref("refs/tags/v1"), self.ref("refs/tags/v0")), (head, head, head))
        self.assertEqual(self.git("tag", "-l", "--format=%(contents:subject)", "v1", cwd=self.origin), "v1: the newest release of major version 1 (v1.0.0)")
        self.assertEqual(self.git("tag", "-l", "--format=%(contents:subject)", "v0", cwd=self.origin), "v0: the newest release or pre-release (v1.0.0)")
        self.assertIn("tagged v1.0.0; v1 and v0 moved to it", ran.out)

    def v0_at(self, name: str) -> None:
        self.git("tag", "-f", "-a", "v0", "-m", "v0", f"refs/tags/{name}^{{commit}}"); self.git("push", "--quiet", "--force", "origin", "refs/tags/v0")

    def test_v0_never_goes_back_to_an_older_line(self):
        self.tag("v2.0.0-rc.1", version="2.0.0"); self.v0_at("v2.0.0-rc.1")
        ahead = self.ref("refs/tags/v0")
        ran = self.release("plan", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("floating tag v1; v0 stays, v2.0.0-rc.1 being later", ran.out)
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        head = self.ref("main")
        self.assertEqual((self.ref("refs/tags/v1"), self.ref("refs/tags/v0")), (head, ahead))
        self.assertIn("tagged v1.0.0; v1 moved to it", ran.out); self.assertIn("v0 stays, v2.0.0-rc.1 being later", ran.out)

    def test_a_pre_release_of_an_older_line_moves_no_floating_tag(self):
        self.tag("v2.0.0-rc.1", version="2.0.0"); self.v0_at("v2.0.0-rc.1")
        ahead = self.ref("refs/tags/v0")
        ran = self.release("publish", tag="1.0.0-rc.3")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual(self.ref("refs/tags/v0"), ahead)
        self.assertIn("tagged v1.0.0-rc.3; v0 stays, v2.0.0-rc.1 being later", ran.out)

    def test_v0_moves_from_a_pre_release_to_its_release_and_on(self):
        self.tag("v1.0.0-rc.2"); self.v0_at("v1.0.0-rc.2")
        self.assertEqual(self.release("publish", tag="1.0.0").code, 0)                                   # a release follows its pre-release
        self.assertEqual(self.ref("refs/tags/v0"), self.ref("refs/tags/v1.0.0"))
        self.assertEqual(self.release("publish", tag="1.0.1-rc.1", digest=OTHER).code, 0)                # and a later pre-release follows it
        self.assertEqual(self.ref("refs/tags/v0"), self.ref("refs/tags/v1.0.1-rc.1"))

    def test_a_release_whose_v0_moved_during_the_run_pushes_nothing(self):
        self.tag("v1.0.0-rc.1"); self.git("tag", "-a", "v0", "-m", "v0"); self.git("push", "--quiet", "origin", "v0")
        main = self.ref("main")
        hook = self.work / ".git" / "hooks" / "pre-push"                                                     # moves origin's v0 after the tags were read
        hook.write_text(f"#!/bin/sh\ngit -C '{self.origin}' tag -f -a v0 -m elsewhere v1.0.0-rc.1 > /dev/null\n"); hook.chmod(0o755)
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 1, ran.out)
        self.assertIn("nothing was pushed", ran.out)
        self.assertEqual((self.ref("main"), self.git("tag", "-l", "v1.0.0", cwd=self.origin)), (main, ""))

    def test_each_floating_tag_says_where_it_moved_from(self):
        self.tag("v1.0.0-rc.1"); self.v0_at("v1.0.0-rc.1")
        v0 = self.git("rev-parse", "--short", "refs/tags/v0^{commit}", cwd=self.origin)
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn(f"tagged v1.0.0; v1 and v0 moved to it (v1 from new, v0 from {v0})", ran.out)

    def test_a_stale_local_floating_tag_is_read_again(self):
        self.assertEqual(self.release("publish").code, 0)                                                # origin's v0 at rc.2
        self.git("tag", "-f", "-a", "v0", "-m", "stale", "main~1")                                      # this clone's, behind
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual(self.ref("refs/tags/v0"), self.ref("refs/tags/v1.0.0"))

    def test_a_tag_a_refused_run_left_is_dropped_and_the_run_again_publishes(self):
        self.git("tag", "-a", "v1.0.0-rc.2", "-m", "left by a refused run")                              # never pushed
        self.git("tag", "mine")                                                                         # someone's own, kept
        ran = self.release("publish")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertNotIn("already pushed", ran.out)
        self.assertEqual(self.ref("refs/tags/v1.0.0-rc.2"), self.ref("main"))
        self.assertEqual(self.git("tag", "-l", "mine"), "mine")



    def test_a_plan_of_a_pushed_tag_claims_no_floating_tag(self):
        self.assertEqual(self.release("publish").code, 0)
        ran = self.release("plan")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("tag v1.0.0-rc.2, version 1.0.0 (rc.2)", ran.out); self.assertNotIn("floating tag", ran.out)

    def test_a_pre_release_promoted_as_it_is_stamps_its_tag_alone(self):
        self.tag("v1.0.0-rc.2")
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        head = self.ref("main")
        diff = self.git("diff", "--unified=0", f"{head}~1", head, cwd=self.origin).splitlines()
        lines = [line for line in diff if line[:1] in ("+", "-") and not line.startswith(("+++", "---"))]
        self.assertEqual(len(lines), 2 * len(STAMPED), lines)
        self.assertTrue(all("ref: ${{ job.workflow_sha || 'v1.0.0" in line for line in lines), lines)
        self.assertEqual(self.ref("refs/tags/v1.0.0"), head)

    def test_a_run_again_after_its_push_moves_nothing(self):
        self.assertEqual(self.release("publish").code, 0)
        self.assertEqual(self.release("publish", tag="1.0.0-rc.3", digest=OTHER).code, 0)   # v0 moves on to rc.3
        before = self.refs()
        ran = self.release("publish")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("::notice::v1.0.0-rc.2 is already pushed with this image and version: nothing is moved", ran.out)
        self.assertEqual(self.refs(), before)
        self.assertEqual(self.ref("refs/tags/v0"), self.ref("refs/tags/v1.0.0-rc.3"))

    def test_a_tag_that_names_another_release(self):
        self.tag("v1.0.0-rc.2", OTHER)
        before = self.refs()
        ran = self.release("publish")
        self.assertEqual(ran.code, 1)
        self.assertIn("a tag is never moved", ran.out)
        self.assertEqual(self.refs(), before)

    def test_main_moved_meanwhile_and_nothing_is_pushed(self):
        other = self.tmp / "other"
        self.git("clone", "--quiet", str(self.origin), str(other), cwd=self.tmp)
        (other / "README.md").write_text("x\n"); self.git("add", ".", cwd=other); self.git("commit", "--quiet", "-m", "x", cwd=other)
        self.git("push", "--quiet", "origin", "main", cwd=other)
        before = self.refs()
        ran = self.release("publish")
        self.assertEqual(ran.code, 1, ran.out)
        self.assertIn("nothing was pushed", ran.out)
        self.assertEqual(self.refs(), before)

    def test_the_newest_release_puts_a_hand_moved_v0_back(self):
        self.tag("v1.0.0-rc.1"); self.git("tag", "-a", "v0", "-m", "v0"); self.git("push", "--quiet", "origin", "v0")
        self.git("tag", "-f", "-a", "v0", "-m", "by hand", "main~1", cwd=self.origin)
        ran = self.release("publish")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual(self.ref("refs/tags/v0"), self.ref("refs/tags/v1.0.0-rc.2"))

    def test_an_older_lines_release_with_no_v0_anywhere(self):
        self.tag("v2.0.0-rc.1", version="2.0.0")                                                          # tagged before v0 existed
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual((self.ref("refs/tags/v0"), self.ref("refs/tags/v1")), ("", self.ref("refs/tags/v1.0.0")))
        self.assertIn("no v0 is made, v2.0.0-rc.1 being later", ran.out)

    def test_an_older_lines_release_leaves_a_hand_moved_v0_alone(self):
        self.tag("v2.0.0-rc.1", version="2.0.0"); self.git("tag", "-a", "v0", "-m", "by hand", "main~1"); self.git("push", "--quiet", "origin", "v0")
        by_hand = self.ref("refs/tags/v0")
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual((self.ref("refs/tags/v0"), self.ref("refs/tags/v1")), (by_hand, self.ref("refs/tags/v1.0.0")))
        self.assertIn("v0 stays, v2.0.0-rc.1 being later", ran.out)

    def test_a_floating_tag_origin_lacks_is_dropped_here(self):
        self.tag("v1.0.0-rc.1")
        self.git("tag", "-a", "v1", "-m", "left by a refused run")                                       # origin has no v1
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("v1 and v0 moved to it (v1 from new", ran.out)
        self.assertEqual(self.ref("refs/tags/v1"), self.ref("refs/tags/v1.0.0"))

    def test_a_version_tag_origin_lacks_counts_for_nothing(self):
        self.git("tag", "-a", "v2.0.0", "-m", "deleted from origin")                                     # here alone
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual(self.git("tag", "-l", "v2.0.0"), "")

    def test_a_kept_v0_moved_during_the_run_and_nothing_is_pushed(self):
        self.tag("v2.0.0-rc.1", version="2.0.0"); self.v0_at("v2.0.0-rc.1")
        main = self.ref("main")
        hook = self.work / ".git" / "hooks" / "post-commit"                                              # after the tags were read, before the push
        hook.write_text(f"#!/bin/sh\ngit -C '{self.origin}' tag -f -a v0 -m elsewhere main~1 > /dev/null\n"); hook.chmod(0o755)
        ran = self.release("publish", tag="1.0.0")
        self.assertEqual(ran.code, 1, ran.out)
        self.assertIn("nothing was pushed", ran.out)
        self.assertEqual((self.ref("main"), self.git("tag", "-l", "v1.0.0", cwd=self.origin)), (main, ""))

    def test_a_working_tree_with_changes(self):
        (self.work / WORKFLOW).write_text((self.work / WORKFLOW).read_text() + "# more\n")
        before = self.refs()
        ran = self.release("publish")
        self.assertEqual(ran.code, 2)
        self.assertIn("the working tree holds changes", ran.out)
        self.assertEqual(self.refs(), before)


class GithubRelease(Release):
    def made(self, ran, tag: str) -> dict:
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual([c["method"] for c in ran.writes()], ["POST"])
        self.assertIn(f"made the GitHub release {tag}", ran.out)
        return ran.state["releases"][tag]

    def test_a_pre_release(self):
        self.tag("v1.0.0-rc.2")
        made = self.made(self.release("github-release", IRONBEE_SIGNATURE="verified"), "v1.0.0-rc.2")
        self.assertEqual({k: made[k] for k in ("tag_name", "name", "prerelease", "make_latest")},
                         {"tag_name": "v1.0.0-rc.2", "name": "v1.0.0-rc.2", "prerelease": True, "make_latest": "false"})
        self.assertEqual(made["body"], f"A pre-release of 1.0.0 for IronBee's own tests, not for production.\n\nImage: `{IMAGE}@{DIGEST}`\n\n"
                                       f"Platforms: linux/amd64, linux/arm64\n\nIts signature verifies with cosign v3 and `{KEY}` from this repository:\n\n"
                                       f"    cosign verify --key {KEY} {IMAGE}@{DIGEST}\n\n")

    def test_a_pre_release_signed_for_ironbees_own_tests(self):
        self.tag("v1.0.0-rc.2")
        made = self.made(self.release("github-release", IRONBEE_SIGNATURE="tests"), "v1.0.0-rc.2")
        self.assertIn(f"It was signed for IronBee's own tests: it does not verify with `{KEY}` from this repository.", made["body"])
        self.assertNotIn("cosign verify", made["body"])

    def test_a_release(self):
        self.tag("v1.0.0")
        made = self.made(self.release("github-release", tag="1.0.0", IRONBEE_SIGNATURE="verified"), "v1.0.0")
        self.assertEqual((made["prerelease"], made["make_latest"]), (False, "true"))
        self.assertTrue(made["body"].startswith(f"Image: `{IMAGE}@{DIGEST}`"))
        self.assertIn(f"    cosign verify --key {KEY} {IMAGE}@{DIGEST}\n", made["body"])

    def test_a_release_whose_image_did_not_verify(self):
        self.tag("v1.0.0")
        for signature in ("tests", "", "yes"):
            with self.subTest(signature):
                ran = self.release("github-release", tag="1.0.0", IRONBEE_SIGNATURE=signature)
                self.assertEqual(ran.code, 2)
                self.assertEqual(ran.calls, [])

    def test_a_release_that_exists_is_left_as_it_is(self):
        self.tag("v1.0.0-rc.2")
        self.state["releases"] = {"v1.0.0-rc.2": {"tag_name": "v1.0.0-rc.2", "id": 1}}
        ran = self.release("github-release", IRONBEE_SIGNATURE="verified")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn("::notice::the GitHub release v1.0.0-rc.2 exists: nothing to do", ran.out)
        self.assertEqual(ran.writes(), [])

    def test_a_tag_not_pushed(self):
        ran = self.release("github-release", IRONBEE_SIGNATURE="verified")
        self.assertEqual(ran.code, 1)
        self.assertIn("v1.0.0-rc.2 is not pushed", ran.out)
        self.assertEqual(ran.calls, [])

    def test_a_create_that_fails(self):
        self.tag("v1.0.0-rc.2")
        self.state["fail"] = [{"method": "POST", "path": f"repos/{REPO}/releases", "status": 502, "times": 3}]
        ran = self.release("github-release", IRONBEE_SIGNATURE="verified")
        self.assertEqual(ran.code, 1)
        self.assertIn("GitHub did not make the release v1.0.0-rc.2 (HTTP 502)", ran.out)
        self.assertEqual([c["method"] for c in ran.calls], ["GET", "POST", "GET"])     # a POST is not sent again on a 5xx
        self.assertEqual(ran.sleeps, [])

    def test_a_create_made_without_an_answer_is_found(self):
        self.tag("v1.0.0-rc.2")
        self.state["fail"] = [{"method": "POST", "path": f"repos/{REPO}/releases", "status": 502, "times": 1, "made": True}]
        ran = self.release("github-release", IRONBEE_SIGNATURE="verified")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual(list(ran.state["releases"]), ["v1.0.0-rc.2"])
        self.assertEqual([c["method"] for c in ran.calls], ["GET", "POST", "GET"])


if __name__ == "__main__":
    unittest.main()
