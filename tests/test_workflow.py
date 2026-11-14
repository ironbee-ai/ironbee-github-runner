"""The workflow files themselves: the inputs and secrets by their published names and the variable each becomes, where
each secret may go, no expression inside a script, every action pinned by commit, the image by digest, the jobs'
conditions and the queue, and the customer's file; every reusable workflow's image as the build checks it; the build's
and the release's own files. Needs PyYAML (skipped without it)."""
from __future__ import annotations

import os
import re
import subprocess
import unittest

from support import ROOT, SCRIPTS

try:
    import yaml
except ImportError:                                          # pragma: no cover
    yaml = None

WORKFLOWS = ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "code-review.yml"
BUILD = WORKFLOWS / "build.yml"
RELEASE = WORKFLOWS / "release.yml"
EXAMPLE = ROOT / "examples" / "ironbee-review.yml"

# Every input and secret, by the names customers write; a major version keeps them all.
INPUTS = {"model-provider", "model-url", "model-name", "model-ca-certificate", "model-prefix", "model-max-output", "aws-region",
          "runs-on", "knowledge-repository", "knowledge-ref", "ignore-paths", "target-branches", "skip-labels", "skip-title-keywords", "app-slug",
          "ironbee-api-url", "ironbee-run-reports"}
SECRETS = {"ironbee-api-key", "registry-token", "model-key", "model-headers", "knowledge-token", "jev-key", "app-id", "app-private-key"}
REQUIRED = {"model-provider"}                               # the two secrets every review needs are checked by job 1, so a run without secrets still reaches it
NEEDED_SECRETS = {"ironbee-api-key", "registry-token"}

# The variable each becomes in the review job's container: the runner's own list of what it reads.
VARIABLES = {"model-provider": "IRONBEE_MODEL_PROVIDER", "model-url": "IRONBEE_MODEL_URL", "model-key": "IRONBEE_MODEL_KEY",
             "model-headers": "IRONBEE_MODEL_HEADERS", "model-ca-certificate": "IRONBEE_MODEL_CA_CERTIFICATE", "model-name": "IRONBEE_MODEL_NAME",
             "model-prefix": "IRONBEE_MODEL_PREFIX", "model-max-output": "IRONBEE_MODEL_MAX_OUTPUT", "aws-region": "AWS_REGION",
             "jev-key": "IRONBEE_JEV_KEY", "ironbee-api-key": "IRONBEE_API_KEY", "knowledge-repository": "IRONBEE_KNOWLEDGE_REPOSITORY",
             "knowledge-ref": "IRONBEE_KNOWLEDGE_REF", "knowledge-token": "IRONBEE_KNOWLEDGE_TOKEN", "ignore-paths": "IRONBEE_IGNORE_PATHS",
             "target-branches": "IRONBEE_TARGET_BRANCHES", "skip-labels": "IRONBEE_SKIP_LABELS", "skip-title-keywords": "IRONBEE_SKIP_TITLE_KEYWORDS",
             "app-id": "IRONBEE_APP_ID", "app-private-key": "IRONBEE_APP_PRIVATE_KEY", "app-slug": "IRONBEE_APP_SLUG", "ironbee-api-url": "IRONBEE_API_URL",
             "ironbee-run-reports": "IRONBEE_RUN_REPORTS"}
HANDED = {"GITHUB_TOKEN": "${{ github.token }}", "IRONBEE_ACTION": "${{ needs.decide.outputs.action }}",
          "IRONBEE_PULL_REQUEST": "${{ needs.decide.outputs.pull-request }}", "IRONBEE_COMMENT_ID": "${{ needs.decide.outputs.comment-id }}"}

# Where each secret's value may go, as (job, place): the model's, the rules repository's and Jev's to the review job
# alone; the App's key to the review job and the token steps; job 1 only learns whether a secret is set.
SECRET_PLACES = {"ironbee-api-key": {("register", "env"), ("review", "env")}, "registry-token": {("review", "container")},
                 "model-key": {("review", "env")}, "model-headers": {("review", "env")}, "knowledge-token": {("review", "env")},
                 "jev-key": {("review", "env")}, "app-id": {("review", "env"), ("decide", "with"), ("fallback", "with")},
                 "app-private-key": {("review", "env"), ("decide", "with"), ("fallback", "with")}}
REVIEW_ONLY_INPUTS = {"model-provider", "model-url", "model-name", "model-ca-certificate", "model-prefix", "model-max-output", "aws-region",
                      "knowledge-repository", "knowledge-ref", "ignore-paths", "target-branches", "skip-labels", "skip-title-keywords",
                      "ironbee-run-reports"}

EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.S)
PINNED = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(/[^@]+)?@[0-9a-f]{40}$")
IMAGE = re.compile(r"^docker\.io/([a-z0-9]+(?:[._-][a-z0-9]+)*)/[a-z0-9]+(?:[._-][a-z0-9]+)*@sha256:[0-9a-f]{64}$")
USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s+(\S+)(.*)$")
PLACEHOLDER = "0" * 64


def load(path) -> dict:
    d = yaml.safe_load(path.read_text())
    if True in d: d["on"] = d.pop(True)                      # YAML 1.1 reads the key `on` as true
    return d


def strings(node, where=()):
    """(path, text) of every string in the tree."""
    if isinstance(node, dict):
        for k, v in node.items(): yield from strings(v, where + (str(k),))
    elif isinstance(node, list):
        for i, v in enumerate(node): yield from strings(v, where + (str(i),))
    elif isinstance(node, str):
        yield where, node


def triggers(wf: dict) -> set:
    on = wf.get("on")
    return {on} if isinstance(on, str) else set(on or ())


def listed() -> dict:
    """The workflows a release stamps, each with the image it runs: scripts/release.sh's own list."""
    out = subprocess.run(["bash", str(SCRIPTS / "release.sh"), "workflows"], capture_output=True, text=True, check=True).stdout
    return dict(line.split(" ", 1) for line in out.splitlines() if line)


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class Workflow(unittest.TestCase):
    def setUp(self) -> None:
        self.wf = load(WORKFLOW); self.jobs = self.wf["jobs"]; self.call = self.wf["on"]["workflow_call"]

    def test_the_inputs_and_secrets_by_their_names(self):
        self.assertEqual(set(self.call["inputs"]), INPUTS)
        self.assertEqual(set(self.call["secrets"]), SECRETS)
        required = {k for k, v in {**self.call["inputs"], **self.call["secrets"]}.items() if v.get("required")}
        self.assertEqual(required, REQUIRED)
        self.assertTrue(all(v["type"] == "string" for v in self.call["inputs"].values()))

    def test_the_four_jobs(self):
        self.assertEqual(set(self.jobs), {"register", "decide", "review", "fallback"})
        self.assertNotIn("IronBee review", [j.get("name") for j in self.jobs.values()])   # no job's check run takes the gate's name

    def test_the_review_job_hands_every_input_and_secret_to_the_runner(self):
        env = self.jobs["review"]["steps"][-1]["env"]
        want = {var: "${{ %s.%s }}" % ("secrets" if name in SECRETS else "inputs", name) for name, var in VARIABLES.items()}
        self.assertEqual(env, {**want, **HANDED})
        self.assertEqual(set(VARIABLES) | {"runs-on", "registry-token"}, INPUTS | SECRETS)

    def test_the_review_job_runs_the_images_entry_point(self):
        [step] = self.jobs["review"]["steps"]
        self.assertEqual(step["run"], "ironbee-runner --print-report")
        self.assertNotIn("python -m core.runner", WORKFLOW.read_text())

    def test_the_image_by_digest_and_its_login(self):
        c = self.jobs["review"]["container"]
        m = IMAGE.match(c["image"])
        self.assertIsNotNone(m, c["image"])
        self.assertEqual(c["credentials"], {"username": m.group(1), "password": "${{ secrets.registry-token }}"})
        for name in ("register", "decide", "fallback"):
            self.assertNotIn("container", self.jobs[name])

    def test_the_queue_of_a_pull_request(self):
        self.assertEqual(self.jobs["review"]["concurrency"], {"group": "ironbee-review-${{ needs.decide.outputs.pull-request }}", "cancel-in-progress": False, "queue": "max"})
        for name in ("register", "decide", "fallback"):
            self.assertNotIn("concurrency", self.jobs[name])
        self.assertNotIn("concurrency", self.wf)

    def test_each_job_has_a_timeout_and_a_hung_review_holds_the_queue_two_hours_at_most(self):
        self.assertEqual({n: j.get("timeout-minutes") for n, j in self.jobs.items()}, {"register": 10, "decide": 10, "review": 120, "fallback": 10})

    def test_run_reports_are_on_unless_the_caller_turns_them_off(self):
        self.assertEqual(self.call["inputs"]["ironbee-run-reports"], {"description": self.call["inputs"]["ironbee-run-reports"]["description"],
                                                                      "type": "string", "required": False, "default": "true"})
        self.assertEqual(self.jobs["review"]["steps"][-1]["env"]["IRONBEE_RUN_REPORTS"], "${{ inputs.ironbee-run-reports }}")
        self.assertNotIn("ironbee-run-reports", str(self.jobs["register"]))       # the registration is the same either way

    def test_no_expression_inside_a_script(self):
        for where, text in strings(self.wf):
            if where[-1] == "run": self.assertNotIn("${{", text, "/".join(where))

    def test_every_action_pinned_by_commit(self):
        uses = [text for where, text in strings(self.wf) if where[-1] == "uses"]
        self.assertTrue(uses)
        for u in uses: self.assertRegex(u, PINNED)

    def test_each_secret_where_it_may_go(self):
        places: dict = {}
        for where, text in strings(self.wf):
            if where[0] != "jobs": continue
            job = where[1]; place = "container" if "container" in where else where[-2] if where[-2] in ("env", "with") else where[-1]
            for expr in EXPRESSION.findall(text):
                for name, cmp in re.findall(r"secrets\.([a-z0-9-]+)(\s*!=\s*'')?", expr):
                    if cmp: self.assertEqual((job, place), ("decide", "env"), f"{name}: only job 1 asks whether it is set"); continue
                    places.setdefault(name, set()).add((job, place))
        self.assertEqual(places, SECRET_PLACES)

    def test_the_model_and_the_rules_repository_go_to_the_review_job_alone(self):
        for where, text in strings(self.wf):
            if where[0] != "jobs": continue
            for name in re.findall(r"inputs\.([a-z0-9-]+)", text):
                if name in REVIEW_ONLY_INPUTS: self.assertEqual(where[1], "review", f"{name} in {'/'.join(where)}")

    def test_job_1_learns_whether_secrets_are_set_never_their_values(self):
        decide = next(s for s in self.jobs["decide"]["steps"] if s.get("id") == "decide")
        self.assertEqual(decide["env"]["IRONBEE_HAS_API_KEY"], "${{ secrets.ironbee-api-key != '' }}")
        self.assertEqual(decide["env"]["IRONBEE_HAS_REGISTRY_TOKEN"], "${{ secrets.registry-token != '' }}")
        self.assertEqual(decide["env"]["IRONBEE_HAS_APP_ID"], "${{ secrets.app-id != '' }}")
        self.assertEqual(decide["env"]["IRONBEE_HAS_APP_PRIVATE_KEY"], "${{ secrets.app-private-key != '' }}")

    def test_the_secrets_every_review_needs_say_that_job_1_checks_them(self):
        for name in NEEDED_SECRETS:
            self.assertFalse(self.call["secrets"][name]["required"])
            self.assertIn("the decide job checks that it is set", self.call["secrets"][name]["description"])

    def test_the_api_address_reaches_the_runner_and_the_register_job_alone(self):
        self.assertEqual(self.call["inputs"]["ironbee-api-url"]["default"], "")
        self.assertEqual(self.jobs["review"]["steps"][-1]["env"]["IRONBEE_API_URL"], "${{ inputs.ironbee-api-url }}")
        self.assertEqual(self.jobs["register"]["steps"][-1]["env"]["IRONBEE_API_URL"], "${{ inputs.ironbee-api-url }}")
        places = {(where[1], where[-2]) for where, text in strings(self.wf) if where[0] == "jobs" and "inputs.ironbee-api-url" in text}
        self.assertEqual(places, {("review", "env"), ("register", "env")})

    def test_the_apps_token_is_minted_only_where_a_check_is_written(self):
        for name in ("decide", "fallback"):
            steps = self.jobs[name]["steps"]
            i = next(i for i, s in enumerate(steps) if "create-github-app-token" in s.get("uses", ""))
            self.assertEqual(steps[i]["with"]["permission-checks"], "write")
            self.assertTrue(all("permission-" not in k or k == "permission-checks" for k in steps[i]["with"]))
            self.assertEqual(steps[i + 1]["run"], "bash .ironbee-github-runner/scripts/neutral.sh")
            self.assertEqual(steps[i + 1]["env"]["IRONBEE_APP_TOKEN"], "${{ steps.app-token.outputs.token }}")
            self.assertEqual(i + 2, len(steps))                # the token's step comes right before the write, the last step

    def test_the_scripts_are_this_workflows_own(self):
        for name in ("register", "decide", "fallback"):
            [checkout] = [s for s in self.jobs[name]["steps"] if "actions/checkout@" in s.get("uses", "")]
            self.assertEqual(checkout["with"]["repository"], "${{ job.workflow_repository }}")
            self.assertEqual(checkout["with"]["ref"], "${{ job.workflow_sha }}")
            self.assertFalse(checkout["with"]["persist-credentials"])

    def test_the_register_job_and_its_two_events(self):
        j = self.jobs["register"]
        self.assertIn("github.event_name == 'workflow_dispatch'", j["if"])
        self.assertIn("github.event_name == 'push' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch)", j["if"])
        [_, step] = j["steps"]
        self.assertEqual(step["run"], "bash .ironbee-github-runner/scripts/register.sh")
        self.assertRegex(str(step["env"]["IRONBEE_RUNNER_VERSION"]), r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
        self.assertEqual(j["permissions"], {"contents": "read"})

    def test_jobs_1_to_3_and_their_events(self):
        self.assertEqual(self.jobs["decide"]["if"], """contains(fromJSON('["pull_request", "issue_comment", "pull_request_review_comment", "merge_group"]'), github.event_name)""")
        self.assertEqual(self.jobs["review"]["if"], "needs.decide.outputs.action != ''")
        f = self.jobs["fallback"]
        self.assertEqual(f["needs"], ["decide", "review"])
        for part in ("always()", "github.event_name == 'pull_request'", "needs.decide.outputs.action == 'review'", "needs.review.result != 'success'"):
            self.assertIn(part, f["if"])

    def test_the_fallback_writes_nothing_where_the_review_was_concluding(self):
        self.assertEqual(self.jobs["review"]["outputs"], {"concluding": "${{ steps.run.outputs.concluding }}"})
        self.assertEqual(self.jobs["review"]["steps"][-1]["id"], "run")
        write = self.jobs["fallback"]["steps"][-1]["env"]
        self.assertEqual(write["IRONBEE_CONCLUDING"], "${{ needs.review.outputs.concluding }}")
        self.assertEqual(write["IRONBEE_HEAD"], "${{ needs.decide.outputs.head }}")

    def test_the_jobs_without_the_image_take_no_more_than_they_need(self):
        self.assertEqual(self.jobs["decide"]["permissions"], {"contents": "read", "pull-requests": "read", "checks": "write"})
        self.assertEqual(self.jobs["fallback"]["permissions"], {"contents": "read", "pull-requests": "read", "checks": "write"})
        self.assertNotIn("permissions", self.jobs["review"])     # the caller's, with contents: write where it allows resolving threads
        self.assertNotIn("permissions", self.wf)


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class CustomersFile(unittest.TestCase):
    def setUp(self) -> None:
        self.wf = load(EXAMPLE)

    def test_the_triggers(self):
        on = self.wf["on"]
        self.assertEqual(on["pull_request"], {"types": ["opened", "synchronize", "reopened", "ready_for_review"]})
        self.assertEqual(on["issue_comment"], {"types": ["created"]})
        self.assertEqual(on["pull_request_review_comment"], {"types": ["created"]})
        self.assertIn("merge_group", on)
        self.assertEqual(on["push"]["paths"], [".github/workflows/ironbee-review.yml"])
        self.assertEqual(len(on["push"]["branches"]), 1)
        self.assertIn("workflow_dispatch", on)
        self.assertEqual(set(on), {"pull_request", "issue_comment", "pull_request_review_comment", "merge_group", "push", "workflow_dispatch"})

    def test_the_permissions(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read", "pull-requests": "write", "checks": "write", "issues": "read"})

    def test_the_call(self):
        [job] = self.wf["jobs"].values()
        self.assertRegex(job["uses"], r"^ironbee-ai/ironbee-github-runner/\.github/workflows/code-review\.yml@v\d+\.\d+\.\d+$")
        self.assertTrue(NEEDED_SECRETS <= set(job["secrets"]) <= SECRETS)
        self.assertTrue({"model-provider"} <= set(job["with"]) <= INPUTS)


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class ReusableWorkflows(unittest.TestCase):
    """What the build checks of every reusable workflow (on: workflow_call): it parses, the release stamps it, and it names
    its image by a full digest. The placeholder of all zeros passes only where IRONBEE_PLACEHOLDER_ALLOWED is true, the
    build of a pull request: on main, a release stamps the workflow with a published image."""

    def test_each_parses_and_the_release_stamps_it(self):
        reusable = {str(p.relative_to(ROOT)) for p in sorted(WORKFLOWS.glob("*.y*ml")) if "workflow_call" in triggers(load(p))}
        self.assertTrue(reusable)
        self.assertEqual(reusable, set(listed()))

    def test_each_names_its_image_by_a_full_digest(self):
        allowed = os.environ.get("IRONBEE_PLACEHOLDER_ALLOWED") == "true"
        for path, image in listed().items():
            containers = [j["container"] for j in load(ROOT / path)["jobs"].values() if "container" in j]
            refs = [c["image"] if isinstance(c, dict) else c for c in containers]
            self.assertTrue(refs, path)
            for ref in refs:
                m = re.fullmatch(re.escape(image) + r"@sha256:([0-9a-f]{64})", ref)
                self.assertIsNotNone(m, f"{path}: {ref}")
                if not allowed: self.assertNotEqual(m.group(1), PLACEHOLDER, f"{path}: the placeholder, which no release has stamped")


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class RepositoryWorkflows(unittest.TestCase):
    """The build and the release: every action pinned by commit with its version beside it, no expression inside a
    script, and write access for the release's publishing job alone."""

    def setUp(self) -> None:
        self.build = load(BUILD); self.release = load(RELEASE)

    def test_every_action_pinned_by_commit_with_its_version(self):
        for path in sorted(WORKFLOWS.glob("*.y*ml")):
            for n, line in enumerate(path.read_text().splitlines(), 1):
                m = USES_LINE.match(line)
                if m:
                    self.assertRegex(m.group(1), PINNED, f"{path.name}:{n}")
                    self.assertRegex(m.group(2), r"^\s+#\s+v\d+(\.\d+)*$", f"{path.name}:{n}")

    def test_no_expression_inside_a_script(self):
        for path, wf in ((BUILD, self.build), (RELEASE, self.release)):
            for where, text in strings(wf):
                if where[-1] == "run": self.assertNotIn("${{", text, f"{path.name}: {'/'.join(where)}")

    def test_the_build(self):
        self.assertEqual(self.build["on"], {"pull_request": {"branches": ["main"]}, "push": {"branches": ["main"]}, "workflow_dispatch": None})
        self.assertEqual(self.build["permissions"], {"contents": "read"})
        self.assertFalse([n for n, j in self.build["jobs"].items() if "permissions" in j])
        [tests] = [s for j in self.build["jobs"].values() for s in j["steps"] if s.get("run") == "python -m pytest tests -q"]
        self.assertEqual(tests["env"], {"IRONBEE_PLACEHOLDER_ALLOWED": "${{ github.event_name == 'pull_request' }}"})
        runs = "\n".join(s.get("run", "") for j in self.build["jobs"].values() for s in j["steps"])
        self.assertIn("shellcheck --shell=bash --external-sources scripts/*.sh", runs)
        self.assertIn("sha256sum --check --strict", runs)
        self.assertIn(".github/workflows/*.yml", runs)

    def test_the_release_takes_its_inputs_through_the_environment(self):
        self.assertEqual(triggers(self.release), {"workflow_dispatch"})
        inputs = self.release["on"]["workflow_dispatch"]["inputs"]
        self.assertEqual({k: (v["type"], v["required"]) for k, v in inputs.items()},
                         {"version": ("string", True), "prerelease": ("string", False), "image-digest": ("string", True)})
        self.assertEqual(self.release["env"], {"IRONBEE_VERSION": "${{ inputs.version }}", "IRONBEE_PRERELEASE": "${{ inputs.prerelease }}",
                                               "IRONBEE_IMAGE_DIGEST": "${{ inputs.image-digest }}"})
        for where, text in strings(self.release["jobs"]):
            self.assertNotIn("inputs.", text, "/".join(where))

    def test_the_release_runs_its_script_one_step_at_a_time(self):
        runs = [s["run"] for j in self.release["jobs"].values() for s in j["steps"] if "run" in s]
        self.assertEqual(runs, ["bash scripts/release.sh plan", "bash scripts/release.sh index", "bash scripts/release.sh signature",
                                'bash scripts/release.sh image "$ARCH"', "bash scripts/release.sh token", "bash scripts/release.sh publish",
                                "bash scripts/release.sh github-release"])
        self.assertEqual(self.release["jobs"]["publish"]["needs"], ["plan", "image"])
        self.assertEqual(self.release["jobs"]["image"]["needs"], "plan")

    def test_the_release_writes_from_its_publishing_job_alone(self):
        # The job's token reads, and writes the GitHub release in the publishing job; GH_ACCESS_TOKEN, which may push a
        # change to a workflow file, is checked and then pushes, there alone.
        self.assertEqual(self.release["permissions"], {"contents": "read"})
        self.assertEqual({n: j.get("permissions") for n, j in self.release["jobs"].items()}, {"plan": None, "image": None, "publish": {"contents": "write"}})
        self.assertEqual(self.release["concurrency"], {"group": "release", "cancel-in-progress": False})
        for name, job in self.release["jobs"].items():
            [checkout] = [s for s in job["steps"] if "actions/checkout@" in s.get("uses", "")]
            self.assertEqual(checkout["with"]["ref"], "main")
            self.assertEqual(checkout["with"]["persist-credentials"], name == "publish")
            self.assertEqual(checkout["with"].get("token"), "${{ secrets.GH_ACCESS_TOKEN }}" if name == "publish" else None)
        steps = self.release["jobs"]["publish"]["steps"]
        self.assertEqual([s.get("run") for s in steps[1:]], ["bash scripts/release.sh token", "bash scripts/release.sh publish", "bash scripts/release.sh github-release"])
        self.assertEqual(steps[1]["env"], {"IRONBEE_PUSH_TOKEN": "${{ secrets.GH_ACCESS_TOKEN }}"})       # checked before anything is stamped
        self.assertEqual(steps[-1]["env"]["GH_TOKEN"], "${{ github.token }}")
        places = {(where[0], where[-2]) for where, text in strings(self.release["jobs"]) if "GH_ACCESS_TOKEN" in text}
        self.assertEqual(places, {("publish", "with"), ("publish", "env")})
        for path in sorted(WORKFLOWS.glob("*.y*ml")):
            if path != RELEASE: self.assertNotIn("GH_ACCESS_TOKEN", path.read_text(), path.name)

    def test_the_release_pulls_with_the_organizations_pull_token(self):
        logins = [s["with"] for j in self.release["jobs"].values() for s in j["steps"] if "docker/login-action@" in s.get("uses", "")]
        self.assertEqual(logins, [{"username": "ironbeeai", "password": "${{ secrets.DOCKERHUB_PULL_TOKEN }}"}] * 2)
        self.assertEqual(set(re.findall(r"secrets\.([A-Za-z0-9_-]+)", RELEASE.read_text())), {"DOCKERHUB_PULL_TOKEN", "GH_ACCESS_TOKEN"})

    def test_each_platform_on_its_own_architecture_and_cosign_3(self):
        image = self.release["jobs"]["image"]
        self.assertEqual(image["strategy"]["matrix"], {"include": [{"arch": "amd64", "runner": "ubuntu-24.04"}, {"arch": "arm64", "runner": "ubuntu-24.04-arm"}]})
        self.assertEqual(image["runs-on"], "${{ matrix.runner }}")
        [cosign] = [s for s in self.release["jobs"]["plan"]["steps"] if "sigstore/cosign-installer@" in s.get("uses", "")]
        self.assertRegex(cosign["with"]["cosign-release"], r"^v3\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
