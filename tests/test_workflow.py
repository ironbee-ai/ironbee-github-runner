"""The workflow files themselves: the one job and its steps, the inputs and secrets by their published names and the
variable each becomes, where each secret may go, no expression inside a script, every action pinned by commit, the image
by digest, each step's condition and the queue, and the customer's file; the workflow without a queue, as its script
makes it; every reusable workflow's image as the build checks it; the build's and the release's own files. Needs PyYAML
(skipped without it)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from support import FIXTURES, ROOT, SCRIPTS, changed, event

try:
    import yaml
except ImportError:                                          # pragma: no cover
    yaml = None

WORKFLOWS = ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "code-review.yml"
NO_QUEUE = WORKFLOWS / "code-review-no-queue.yml"
BUILD = WORKFLOWS / "build.yml"
RELEASE = WORKFLOWS / "release.yml"
EXAMPLE = ROOT / "examples" / "ironbee-review.yml"
EXAMPLE_SERVER = ROOT / "examples" / "ironbee-review-enterprise-server.yml"

# Every input and secret, by the names customers write; a major version keeps them all.
INPUTS = {"model-provider", "model-url", "model-name", "model-ca-certificate", "model-prefix", "model-max-output", "aws-region",
          "runs-on", "knowledge-repository", "knowledge-ref", "ignore-paths", "target-branches", "skip-labels", "skip-title-keywords", "app-slug",
          "ironbee-api-url", "ironbee-run-reports", "runner-repository", "github-ca-certificate"}
SECRETS = {"ironbee-api-key", "registry-token", "model-key", "model-headers", "knowledge-token", "jev-key", "app-id", "app-private-key",
           "runner-token"}
CHECKOUT_ONLY = {"runner-repository", "runner-token"}       # the scripts' copy, off github.com: never the runner's
REQUIRED = {"model-provider"}                               # the two secrets every review needs are checked by the decide step, so a run without secrets still reaches it
NEEDED_SECRETS = {"ironbee-api-key", "registry-token"}

# The variable each becomes in the review step's container: the runner's own list of what it reads.
VARIABLES = {"model-provider": "IRONBEE_MODEL_PROVIDER", "model-url": "IRONBEE_MODEL_URL", "model-key": "IRONBEE_MODEL_KEY",
             "model-headers": "IRONBEE_MODEL_HEADERS", "model-ca-certificate": "IRONBEE_MODEL_CA_CERTIFICATE", "model-name": "IRONBEE_MODEL_NAME",
             "model-prefix": "IRONBEE_MODEL_PREFIX", "model-max-output": "IRONBEE_MODEL_MAX_OUTPUT", "aws-region": "AWS_REGION",
             "jev-key": "IRONBEE_JEV_KEY", "ironbee-api-key": "IRONBEE_API_KEY", "knowledge-repository": "IRONBEE_KNOWLEDGE_REPOSITORY",
             "knowledge-ref": "IRONBEE_KNOWLEDGE_REF", "knowledge-token": "IRONBEE_KNOWLEDGE_TOKEN", "ignore-paths": "IRONBEE_IGNORE_PATHS",
             "target-branches": "IRONBEE_TARGET_BRANCHES", "skip-labels": "IRONBEE_SKIP_LABELS", "skip-title-keywords": "IRONBEE_SKIP_TITLE_KEYWORDS",
             "app-id": "IRONBEE_APP_ID", "app-private-key": "IRONBEE_APP_PRIVATE_KEY", "app-slug": "IRONBEE_APP_SLUG", "ironbee-api-url": "IRONBEE_API_URL",
             "ironbee-run-reports": "IRONBEE_RUN_REPORTS", "github-ca-certificate": "IRONBEE_GITHUB_CA_CERTIFICATE"}
HANDED = {"GITHUB_TOKEN": "${{ github.token }}", "IRONBEE_ACTION": "${{ steps.decide.outputs.action }}",
          "IRONBEE_PULL_REQUEST": "${{ steps.decide.outputs.pull-request }}", "IRONBEE_COMMENT_ID": "${{ steps.decide.outputs.comment-id }}"}

# The one job's steps, in order, by id.
STEPS = ["repository", "scripts", "register", "decide", "app-token", "neutral", "review", "stop", "fallback-app-token", "fallback"]

# The pull request's queue: the events that may run the reviewer wait their turn; every other one has a group of its own.
QUEUE = ("${{ (github.event_name == 'pull_request' || "
         "(github.event_name == 'pull_request_review_comment' && github.event.comment.in_reply_to_id && "
         "github.event.comment.user.type != 'Bot' && github.event.sender.type != 'Bot') || "
         "(github.event_name == 'issue_comment' && contains(github.event.comment.body, '@') && "
         "github.event.comment.user.type != 'Bot' && github.event.sender.type != 'Bot')) "
         "&& format('ironbee-review-{0}', github.event.pull_request.number || github.event.issue.number) "
         "|| format('ironbee-{0}', github.run_id) }}")

# Where each secret's value may go, as (step, place): the model's, the rules repository's, Jev's and the registry
# token to the review step alone; the API key to it and the register step; the App's key to it and the token steps;
# the decide step only learns whether a secret is set.
SECRET_PLACES = {"ironbee-api-key": {("register", "env"), ("review", "env")}, "registry-token": {("review", "env")},
                 "model-key": {("review", "env")}, "model-headers": {("review", "env")}, "knowledge-token": {("review", "env")},
                 "jev-key": {("review", "env")}, "app-id": {("review", "env"), ("app-token", "with"), ("fallback-app-token", "with")},
                 "app-private-key": {("review", "env"), ("app-token", "with"), ("fallback-app-token", "with")},
                 "runner-token": {("scripts", "with")}}
REVIEW_ONLY_INPUTS = {"model-provider", "model-url", "model-name", "model-ca-certificate", "model-prefix", "model-max-output", "aws-region",
                      "knowledge-repository", "knowledge-ref", "ignore-paths", "target-branches", "skip-labels", "skip-title-keywords",
                      "ironbee-run-reports", "github-ca-certificate"}
RELEASE_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-rc\.[1-9]\d*)?$")

EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.S)
PINNED = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(/[^@]+)?@[0-9a-f]{40}$")
IMAGE = re.compile(r"^docker\.io/([a-z0-9]+(?:[._-][a-z0-9]+)*)/[a-z0-9]+(?:[._-][a-z0-9]+)*@sha256:[0-9a-f]{64}$")
USES_LINE = re.compile(r"^\s*(?:-\s+)?uses:\s+(\S+)(.*)$")
PLACEHOLDER = "0" * 64


def evaluate(expression: str, event_name: str, payload: dict, run_id: int = 42, inputs: dict | None = None, steps: dict | None = None):
    """A `${{ }}` expression of the operators and functions the groups and the restart step's condition use, over an
    event, the workflow's inputs and the steps' results: `&&` and `||` give an operand as GitHub's do, a missing
    property is null, `contains` and `startsWith` ignore case, `always()` is true."""
    def walk(node, path: str):
        for key in path.split("."): node = node.get(key) if isinstance(node, dict) else None
        return node
    body = expression.strip().removeprefix("${{").removesuffix("}}")
    body = re.sub(r"\bgithub\.([A-Za-z_.]+)", lambda m: f"github({m.group(1)!r})", body)
    body = re.sub(r"\binputs\.([A-Za-z0-9_-]+)", lambda m: f"inputs({m.group(1)!r})", body)
    body = re.sub(r"\bsteps\.([A-Za-z0-9_.-]+)", lambda m: f"steps({m.group(1)!r})", body)
    body = body.replace("always()", "True").replace("&&", " and ").replace("||", " or ")
    functions = {"github": lambda p: walk({"event_name": event_name, "run_id": run_id, "event": payload}, p),
                 "inputs": lambda k: (inputs or {}).get(k, ""), "steps": lambda p: walk(steps or {}, p),
                 "contains": lambda a, b: str(b or "").lower() in str(a or "").lower(),
                 "startsWith": lambda a, b: str(a or "").lower().startswith(str(b or "").lower()),
                 "format": lambda f, *args: re.sub(r"\{(\d+)\}", lambda m: str(args[int(m.group(1))]), f)}
    return eval(" ".join(body.split()), {"__builtins__": {}}, functions)


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
        self.job = self.jobs["review"]; self.steps = {s["id"]: s for s in self.job["steps"]}

    def test_the_inputs_and_secrets_by_their_names(self):
        self.assertEqual(set(self.call["inputs"]), INPUTS)
        self.assertEqual(set(self.call["secrets"]), SECRETS)
        required = {k for k, v in {**self.call["inputs"], **self.call["secrets"]}.items() if v.get("required")}
        self.assertEqual(required, REQUIRED)
        self.assertTrue(all(v["type"] == "string" for v in self.call["inputs"].values()))

    def test_one_job_named_job(self):
        self.assertEqual(set(self.jobs), {"review"})                 # a pull request's checks list it once, as <caller's workflow> / <caller's job> / Job
        self.assertEqual(self.job["name"], "Job")
        self.assertNotIn("container", self.job)                       # the image runs in a step
        self.assertNotIn("outputs", self.job)

    def test_its_steps_in_order(self):
        self.assertEqual([s["id"] for s in self.job["steps"]], STEPS)
        self.assertTrue(all("id" in s for s in self.job["steps"]))

    def test_the_review_step_hands_every_input_and_secret_to_the_runner(self):
        env = self.steps["review"]["env"]
        want = {var: "${{ %s.%s }}" % ("secrets" if name in SECRETS else "inputs", name) for name, var in VARIABLES.items()}
        self.assertEqual(env, {**want, **HANDED, "IRONBEE_REGISTRY_TOKEN": "${{ secrets.registry-token }}"})
        self.assertEqual(set(VARIABLES) | {"runs-on", "registry-token"} | CHECKOUT_ONLY, INPUTS | SECRETS)

    def test_the_review_and_its_stop_run_the_review_script(self):
        self.assertEqual(self.steps["review"]["run"], "exec bash .ironbee-github-runner/scripts/review.sh")   # a signal to the step reaches the script
        self.assertEqual(self.steps["stop"]["run"], "bash .ironbee-github-runner/scripts/review.sh stop")
        self.assertNotIn("env", self.steps["stop"])
        self.assertNotIn("python -m core.runner", WORKFLOW.read_text())

    def test_the_image_by_digest_in_the_jobs_environment(self):
        self.assertEqual(set(self.job["env"]), {"IRONBEE_IMAGE"})
        m = IMAGE.match(self.job["env"]["IRONBEE_IMAGE"])
        self.assertIsNotNone(m, self.job["env"]["IRONBEE_IMAGE"])
        self.assertEqual(m.group(1), "ironbeeai")                    # the namespace the registry token signs in with

    def test_the_queue_of_a_pull_request(self):
        c = self.job["concurrency"]
        self.assertEqual({**c, "group": " ".join(c["group"].split())},
                         {"group": QUEUE, "cancel-in-progress": False, "queue": "max"})            # its lines as one
        self.assertNotIn("concurrency", self.wf)

    def test_who_waits_in_the_queue(self):
        """Every event that may run the reviewer waits in its pull request's queue; a bot's comment (ours included), a
        thread's first comment, a comment that mentions nobody and the events of no pull request never wait."""
        group = self.job["concurrency"]["group"]
        comment, reply = event("issue_comment.created"), event("pull_request_review_comment.created")
        bot = {"user": {"login": "acme-reviewer[bot]", "type": "Bot"}}
        cases = {"a pull request's event": ("pull_request", event("pull_request.opened"), "ironbee-review-7"),
                 "a person's reply on a thread": ("pull_request_review_comment", reply, "ironbee-review-7"),
                 "a person's comment that mentions someone": ("issue_comment", comment, "ironbee-review-7"),
                 "a thread's first comment": ("pull_request_review_comment", changed(reply, comment__in_reply_to_id=None), "ironbee-42"),
                 "a bot's reply on a thread": ("pull_request_review_comment", changed(reply, comment__user=bot["user"]), "ironbee-42"),
                 "a reply a bot sent": ("pull_request_review_comment", changed(reply, sender__type="Bot"), "ironbee-42"),
                 "a bot's comment that mentions us": ("issue_comment", changed(comment, comment__user=bot["user"]), "ironbee-42"),
                 "a comment a bot sent": ("issue_comment", changed(comment, sender__type="Bot"), "ironbee-42"),
                 "a comment that mentions nobody": ("issue_comment", changed(comment, comment__body="Looks good to me."), "ironbee-42"),
                 "a merge queue's group": ("merge_group", event("merge_group.checks_requested"), "ironbee-42"),
                 "a push": ("push", {"ref": "refs/heads/main"}, "ironbee-42"),
                 "a manual start": ("workflow_dispatch", {}, "ironbee-42")}
        for name, (event_name, payload, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(evaluate(group, event_name, payload), want)

    def test_each_step_has_a_timeout_and_a_hung_review_holds_the_queue_two_hours_at_most(self):
        timeouts = {s["id"]: s.get("timeout-minutes") for s in self.job["steps"]}
        self.assertEqual(timeouts, {"repository": 1, "scripts": 5, "register": 10, "decide": 10, "app-token": 5, "neutral": 10, "review": 120,
                                    "stop": 2, "fallback-app-token": 5, "fallback": 10})
        self.assertNotIn("timeout-minutes", self.job)

    def test_run_reports_are_on_unless_the_caller_turns_them_off(self):
        self.assertEqual(self.call["inputs"]["ironbee-run-reports"], {"description": self.call["inputs"]["ironbee-run-reports"]["description"],
                                                                      "type": "string", "required": False, "default": "true"})
        self.assertEqual(self.steps["review"]["env"]["IRONBEE_RUN_REPORTS"], "${{ inputs.ironbee-run-reports }}")
        self.assertNotIn("ironbee-run-reports", str(self.steps["register"]))      # the registration is the same either way

    def test_no_expression_inside_a_script(self):
        for where, text in strings(self.wf):
            if where[-1] == "run": self.assertNotIn("${{", text, "/".join(where))

    def test_every_action_pinned_by_commit(self):
        uses = [text for where, text in strings(self.wf) if where[-1] == "uses"]
        self.assertTrue(uses)
        for u in uses: self.assertRegex(u, PINNED)

    def test_each_secret_where_it_may_go(self):
        places: dict = {}
        for step in self.job["steps"]:
            for where, text in strings(step):
                place = where[0] if where[0] in ("env", "with") else where[-1]
                for expr in EXPRESSION.findall(text):
                    for name, cmp in re.findall(r"secrets\.([a-z0-9-]+)(\s*!=\s*'')?", expr):
                        if cmp: self.assertEqual((step["id"], place), ("decide", "env"), f"{name}: only the decide step asks whether it is set"); continue
                        places.setdefault(name, set()).add((step["id"], place))
        self.assertEqual(places, SECRET_PLACES)
        for where, text in strings({k: v for k, v in self.job.items() if k != "steps"}):
            self.assertNotIn("secrets.", text, "/".join(where))

    def test_the_model_and_the_rules_repository_go_to_the_review_step_alone(self):
        for step in self.job["steps"]:
            for where, text in strings(step):
                for name in re.findall(r"inputs\.([a-z0-9-]+)", text):
                    if name in REVIEW_ONLY_INPUTS: self.assertEqual(step["id"], "review", f"{name} in {step['id']}/{'/'.join(where)}")

    def test_the_decide_step_learns_whether_secrets_are_set_never_their_values(self):
        env = self.steps["decide"]["env"]
        self.assertEqual(env["IRONBEE_HAS_API_KEY"], "${{ secrets.ironbee-api-key != '' }}")
        self.assertEqual(env["IRONBEE_HAS_REGISTRY_TOKEN"], "${{ secrets.registry-token != '' }}")
        self.assertEqual(env["IRONBEE_HAS_APP_ID"], "${{ secrets.app-id != '' }}")
        self.assertEqual(env["IRONBEE_HAS_APP_PRIVATE_KEY"], "${{ secrets.app-private-key != '' }}")

    def test_the_secrets_every_review_needs_say_that_the_decide_step_checks_them(self):
        for name in NEEDED_SECRETS:
            self.assertFalse(self.call["secrets"][name]["required"])
            self.assertIn("the decide step checks that it is set", self.call["secrets"][name]["description"])

    def test_the_api_address_reaches_the_runner_and_the_register_step_alone(self):
        self.assertEqual(self.call["inputs"]["ironbee-api-url"]["default"], "")
        for name in ("review", "register"):
            self.assertEqual(self.steps[name]["env"]["IRONBEE_API_URL"], "${{ inputs.ironbee-api-url }}")
        places = {step["id"] for step in self.job["steps"] for _, text in strings(step) if "inputs.ironbee-api-url" in text}
        self.assertEqual(places, {"review", "register"})

    def test_the_register_step_and_its_runner_version(self):
        step = self.steps["register"]
        self.assertEqual(step["run"], "bash .ironbee-github-runner/scripts/register.sh")
        self.assertRegex(str(step["env"]["IRONBEE_RUNNER_VERSION"]), r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
        self.assertEqual(set(step["env"]), {"IRONBEE_API_KEY", "IRONBEE_API_URL", "IRONBEE_RUNNER_VERSION"})

    def test_the_apps_token_is_minted_only_right_before_a_check_is_written(self):
        steps = self.job["steps"]
        minted = [i for i, s in enumerate(steps) if "create-github-app-token" in s.get("uses", "")]
        self.assertEqual([steps[i]["id"] for i in minted], ["app-token", "fallback-app-token"])
        for i in minted:
            self.assertEqual(steps[i]["with"]["permission-checks"], "write")
            self.assertTrue(all("permission-" not in k or k == "permission-checks" for k in steps[i]["with"]))
            self.assertEqual(steps[i + 1]["run"], "bash .ironbee-github-runner/scripts/neutral.sh")
            self.assertEqual(steps[i + 1]["env"]["IRONBEE_APP_TOKEN"], "${{ steps.%s.outputs.token }}" % steps[i]["id"])
            self.assertIn("inputs.app-slug != ''", steps[i]["if"])
            self.assertEqual(steps[i]["if"].replace(" && inputs.app-slug != ''", ""), steps[i + 1]["if"])   # minted only where the write follows

    def test_the_scripts_are_this_workflows_own(self):
        """The workflow's repository at the commit the job names (github.com, GHE.com), else the copy `runner-repository`
        names at this release's tag (GitHub Enterprise Server); read with `runner-token` where one is given."""
        [checkout] = [s for s in self.job["steps"] if "actions/checkout@" in s.get("uses", "")]
        self.assertIs(checkout, self.job["steps"][1])
        ref = checkout["with"]["ref"]
        m = re.fullmatch(r"\$\{\{ job\.workflow_sha \|\| '([^']+)' \}\}", ref)
        self.assertIsNotNone(m, ref)
        self.assertEqual(checkout["with"], {"repository": "${{ job.workflow_repository || inputs.runner-repository }}", "ref": ref,
                                            "token": "${{ secrets.runner-token || github.token }}",
                                            "path": ".ironbee-github-runner", "sparse-checkout": "scripts", "persist-credentials": False})
        self.assertNotIn("if", checkout)

    def test_the_tag_the_scripts_are_read_at_is_the_releases_own(self):
        tag = re.search(r"job\.workflow_sha \|\| '([^']+)'", self.steps["scripts"]["with"]["ref"]).group(1)
        self.assertRegex(tag, RELEASE_TAG)
        self.assertEqual(tag.removeprefix("v").split("-")[0], str(self.steps["register"]["env"]["IRONBEE_RUNNER_VERSION"]))

    def test_a_job_that_names_no_repository_needs_the_copy_named(self):
        """Where a job names no workflow repository the checkout would read the calling repository's own `scripts`:
        the step before it fails first, naming the input."""
        guard = self.job["steps"][0]
        self.assertEqual(guard["if"], "job.workflow_repository == '' && inputs.runner-repository == ''")
        self.assertIn("::error::runner-repository is not given", guard["run"])
        self.assertTrue(guard["run"].rstrip().endswith("exit 2"))
        self.assertNotIn("env", guard)

    def test_the_copys_input_and_token_go_to_the_checkout_alone(self):
        for step in self.job["steps"]:
            for where, text in strings(step):
                for name in re.findall(r"(?:inputs|secrets)\.([a-z0-9-]+)", text):
                    if name in CHECKOUT_ONLY: self.assertIn(step["id"], ("repository", "scripts"), f"{name} in {step['id']}/{'/'.join(where)}")
        self.assertNotIn("runner-token", str(self.steps["repository"]))

    def test_the_github_servers_authority_reaches_the_runner_by_name_as_the_models_does(self):
        env = self.steps["review"]["env"]
        self.assertEqual(env["IRONBEE_GITHUB_CA_CERTIFICATE"], "${{ inputs.github-ca-certificate }}")
        self.assertEqual(self.call["inputs"]["github-ca-certificate"]["default"], "")
        passed = re.search(r"PASSED=\((.*?)\)", (SCRIPTS / "review.sh").read_text(), re.S).group(1).split()
        self.assertIn("IRONBEE_GITHUB_CA_CERTIFICATE", passed)
        self.assertEqual(set(env) - {"IRONBEE_REGISTRY_TOKEN"}, set(passed) & set(env))     # every one the step sets, by name

    def test_the_job_and_its_events(self):
        self.assertIn("""contains(fromJSON('["pull_request", "issue_comment", "pull_request_review_comment", "merge_group", "workflow_dispatch"]'), github.event_name)""", self.job["if"])
        self.assertIn("(github.event_name == 'push' && github.ref == format('refs/heads/{0}', github.event.repository.default_branch))", self.job["if"])

    def test_each_steps_events(self):
        self.assertEqual(self.steps["register"]["if"], "github.event_name == 'push' || github.event_name == 'workflow_dispatch'")
        self.assertEqual(self.steps["decide"]["if"], """contains(fromJSON('["pull_request", "issue_comment", "pull_request_review_comment", "merge_group"]'), github.event_name)""")
        self.assertEqual(self.steps["app-token"]["if"], "steps.decide.outputs.write != '' && inputs.app-slug != ''")
        self.assertEqual(self.steps["neutral"]["if"], "steps.decide.outputs.write != ''")              # off wherever decide did not run
        self.assertEqual(self.steps["review"]["if"], "steps.decide.outputs.action != ''")
        self.assertEqual(self.steps["stop"]["if"], "always() && steps.decide.outputs.action != ''")

    def test_the_fallback_follows_a_pull_requests_review_that_did_not_succeed(self):
        f = self.steps["fallback"]
        self.assertEqual(f["if"], "always() && github.event_name == 'pull_request' && steps.decide.outcome == 'success' && "
                                  "steps.decide.outputs.action == 'review' && steps.review.outcome != 'success'")
        self.assertEqual((f["env"]["IRONBEE_REASON"], f["env"]["IRONBEE_HEAD"]), ("not_run", "${{ steps.decide.outputs.head }}"))
        self.assertEqual(f["env"]["IRONBEE_PULL_REQUEST"], "${{ steps.decide.outputs.pull-request }}")
        names = [s["id"] for s in self.job["steps"]]
        self.assertLess(names.index("stop"), names.index("fallback"))                                   # the container is gone first

    def test_the_fallback_writes_nothing_where_the_review_was_concluding(self):
        self.assertEqual(self.steps["fallback"]["env"]["IRONBEE_CONCLUDING"], "${{ steps.review.outputs.concluding }}")

    def test_the_job_takes_the_callers_permissions(self):
        self.assertNotIn("permissions", self.job)     # contents: write where the caller allows resolving threads
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

    def test_the_names_a_pull_request_shows(self):
        """`IronBee / Code Review / Job` beside `IronBee / Code Review Result`."""
        self.assertEqual(self.wf["name"], "IronBee")
        self.assertEqual(list(self.wf["jobs"]), ["code-review"])
        self.assertEqual(self.wf["jobs"]["code-review"]["name"], "Code Review")

    def test_the_call(self):
        [job] = self.wf["jobs"].values()
        self.assertRegex(job["uses"], r"^ironbee-ai/ironbee-github-runner/\.github/workflows/code-review\.yml@v\d+\.\d+\.\d+$")
        self.assertTrue(NEEDED_SECRETS <= set(job["secrets"]) <= SECRETS)
        self.assertTrue({"model-provider"} <= set(job["with"]) <= INPUTS)


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class ServersFile(unittest.TestCase):
    """The customer's file on a GitHub Enterprise Server: the workflow without a queue, from the server's copy, named in
    `uses:` and in `runner-repository`, read with `runner-token`; the server's own runners; `actions: write` for the
    restart step; and our job alone, since a re-run starts every job of a run again."""

    def setUp(self) -> None:
        self.wf = load(EXAMPLE_SERVER); self.main = load(EXAMPLE)

    def test_the_triggers_and_names_are_the_github_com_files(self):
        self.assertEqual(self.wf["on"], self.main["on"])
        self.assertEqual(self.wf["name"], self.main["name"])
        self.assertEqual({n: j["name"] for n, j in self.wf["jobs"].items()}, {"code-review": "Code Review"})

    def test_the_permissions_add_actions_write(self):
        self.assertEqual(self.wf["permissions"], {**self.main["permissions"], "actions": "write"})

    def test_the_call_names_the_copy_twice_and_its_token(self):
        [job] = self.wf["jobs"].values()
        m = re.fullmatch(r"([A-Za-z0-9-]+/[A-Za-z0-9._-]+)/\.github/workflows/code-review-no-queue\.yml@v\d+\.\d+\.\d+", job["uses"])
        self.assertIsNotNone(m, job["uses"])
        self.assertEqual(job["with"]["runner-repository"], m.group(1))
        self.assertIn("runs-on", job["with"])
        self.assertTrue(NEEDED_SECRETS | {"runner-token"} <= set(job["secrets"]) <= SECRETS)
        self.assertTrue({"model-provider", "runner-repository", "runs-on"} <= set(job["with"]) <= INPUTS)


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class WithoutAQueue(unittest.TestCase):
    """code-review-no-queue.yml, for a host whose Actions know no concurrency queue: code-review.yml as
    scripts/build-no-queue.sh makes it, with one waiting run, a narrower group and the restart step."""

    def setUp(self) -> None:
        self.main, self.wf = load(WORKFLOW), load(NO_QUEUE)
        self.job = self.wf["jobs"]["review"]; self.steps = {s["id"]: s for s in self.job["steps"]}
        self.group = self.job["concurrency"]["group"]

    def build(self, *args, cwd=ROOT) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(SCRIPTS / "build-no-queue.sh"), *args], cwd=cwd, capture_output=True, text=True)

    def test_it_is_what_its_script_makes(self):
        p = self.build("--check")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(NO_QUEUE.read_text().startswith("# Generated from code-review.yml by scripts/build-no-queue.sh: do not edit"))

    def test_the_rest_is_the_first_files(self):
        self.assertEqual({k: v for k, v in self.wf.items() if k != "jobs"}, {k: v for k, v in self.main.items() if k != "jobs"})
        self.assertEqual(set(self.wf["jobs"]), {"review"})
        main = self.main["jobs"]["review"]
        self.assertEqual({k: v for k, v in self.job.items() if k not in ("concurrency", "steps")}, {k: v for k, v in main.items() if k not in ("concurrency", "steps")})
        self.assertEqual(self.job["steps"][:-1], main["steps"])
        self.assertEqual(self.job["steps"][-1]["id"], "restart")

    def test_one_waiting_run_and_never_a_started_one_cancelled(self):
        self.assertEqual(set(self.job["concurrency"]), {"group", "cancel-in-progress"})
        self.assertIs(self.job["concurrency"]["cancel-in-progress"], False)
        self.assertFalse(re.search(r"^\s+queue:", NO_QUEUE.read_text(), re.M))

    def cases(self) -> dict:
        comment, reply = event("issue_comment.created"), event("pull_request_review_comment.created")
        bot = {"login": "acme-reviewer[bot]", "type": "Bot"}
        return {"a pull request's event": ("pull_request", event("pull_request.opened"), {}, True),
                "a person's reply on a thread": ("pull_request_review_comment", reply, {}, True),
                "a comment that names us": ("issue_comment", comment, {}, True),
                "a comment that names us in another case": ("issue_comment", changed(comment, comment__body="Thanks, @IronBee-AI!"), {}, True),
                "a comment that names someone else": ("issue_comment", changed(comment, comment__body="@bob please look"), {}, False),
                "a comment that mentions nobody": ("issue_comment", changed(comment, comment__body="Looks good to me."), {}, False),
                "under the App, a comment that names it": ("issue_comment", changed(comment, comment__body="@acme-reviewer review"), {"app-slug": "acme-reviewer"}, True),
                "under the App given with its @ and in capitals": ("issue_comment", changed(comment, comment__body="@acme-reviewer review"), {"app-slug": "@Acme-Reviewer"}, True),
                "under the App, a comment that names @ironbee-ai": ("issue_comment", comment, {"app-slug": "acme-reviewer"}, False),
                "a thread's first comment": ("pull_request_review_comment", changed(reply, comment__in_reply_to_id=None), {}, False),
                "a bot's reply on a thread": ("pull_request_review_comment", changed(reply, comment__user=bot), {}, False),
                "a bot's comment that names us": ("issue_comment", changed(comment, comment__user=bot), {}, False),
                "a comment a bot sent": ("issue_comment", changed(comment, sender__type="Bot"), {}, False),
                "a merge queue's group": ("merge_group", event("merge_group.checks_requested"), {}, False),
                "a push": ("push", {"ref": "refs/heads/main"}, {}, False),
                "a manual start": ("workflow_dispatch", {}, {}, False)}

    def test_who_waits_in_the_pull_requests_group(self):
        """The first file's group, but for a conversation comment, which waits only when it names the reviewer."""
        for name, (event_name, payload, inputs, waits) in self.cases().items():
            with self.subTest(name):
                self.assertEqual(evaluate(self.group, event_name, payload, inputs=inputs), "ironbee-review-7" if waits else "ironbee-42")

    def test_every_comment_the_decide_step_takes_is_in_the_group(self):
        """So that no command runs beside a review: the decide step's own mention rule over the runner's cases."""
        cases = json.loads((FIXTURES / "mention-cases.json").read_text())["cases"]
        comment = event("issue_comment.created")
        for case in cases:
            slug = "" if case["mention"] == "@ironbee-ai" else case["mention"].removeprefix("@")
            p = subprocess.run(["jq", "-n", "-L", str(SCRIPTS), "--arg", "b", case["body"], "--arg", "n", case["mention"], 'include "ironbee"; $b | addressed([$n])'],
                               capture_output=True, text=True, check=True)
            if p.stdout.strip() != "true": continue
            with self.subTest(case["body"]):
                self.assertEqual(evaluate(self.group, "issue_comment", changed(comment, comment__body=case["body"]), inputs={"app-slug": slug}), "ironbee-review-7")

    def test_the_restart_step_ends_every_run_of_the_group_that_handed_on_no_review(self):
        step = self.job["steps"][-1]
        self.assertEqual((step["name"], step["run"], step["timeout-minutes"], step["shell"]),
                         ("Start a replaced review again", "bash .ironbee-github-runner/scripts/restart.sh", 10, "bash"))
        self.assertEqual(step["env"], {"GH_TOKEN": "${{ github.token }}", "IRONBEE_APP_SLUG": "${{ inputs.app-slug }}"})
        done = {"scripts": {"outcome": "success"}}
        for name, (event_name, payload, inputs, waits) in self.cases().items():
            for action in ("", "answer", "respond", "retract", "review"):
                with self.subTest(name, action=action):
                    steps = {**done, "decide": {"outputs": {"action": action}}}
                    self.assertEqual(bool(evaluate(step["if"], event_name, payload, inputs=inputs, steps=steps)), waits and action != "review")
        comment = event("issue_comment.created")
        self.assertFalse(evaluate(step["if"], "issue_comment", comment, steps={"scripts": {"outcome": "failure"}, "decide": {"outputs": {"action": ""}}}))

    def test_the_script_refuses_a_first_file_it_cannot_turn_into_the_second(self):
        text = WORKFLOW.read_text()
        tmp = Path(tempfile.mkdtemp(prefix="ironbee-no-queue-")); self.addCleanup(shutil.rmtree, tmp, True)
        variants = {"another group": text.replace("contains(github.event.comment.body, '@')", "contains(github.event.comment.body, '@@')"),
                    "no queue": text.replace("      queue: max\n", ""),
                    "a second queue": text.replace("    runs-on: ${{", "    queue: max\n    runs-on: ${{"),
                    "no steps at the end": text + "\nconcurrency:\n  group: x\n"}
        for name, variant in variants.items():
            with self.subTest(name):
                (tmp / "in.yml").write_text(variant)
                p = self.build(str(tmp / "in.yml"), str(tmp / "out.yml"), cwd=tmp)
                self.assertEqual(p.returncode, 2, p.stdout)
                self.assertFalse((tmp / "out.yml").exists())

    def test_the_check_fails_on_a_copy_edited_by_hand(self):
        tmp = Path(tempfile.mkdtemp(prefix="ironbee-no-queue-")); self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copy(WORKFLOW, tmp / "in.yml")
        (tmp / "out.yml").write_text(NO_QUEUE.read_text().replace("timeout-minutes: 10\n        shell: bash\n        run: bash .ironbee-github-runner/scripts/restart.sh",
                                                                 "timeout-minutes: 20\n        shell: bash\n        run: bash .ironbee-github-runner/scripts/restart.sh"))
        p = self.build("--check", str(tmp / "in.yml"), str(tmp / "out.yml"), cwd=tmp)
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertIn("is not what scripts/build-no-queue.sh makes", p.stdout)
        p = self.build("--check", str(tmp / "in.yml"), str(tmp / "missing.yml"), cwd=tmp)
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertEqual(self.build(str(tmp / "in.yml"), str(tmp / "out.yml"), cwd=tmp).returncode, 0)
        self.assertEqual((tmp / "out.yml").read_text(), NO_QUEUE.read_text())


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
            refs = [j["env"]["IRONBEE_IMAGE"] for j in load(ROOT / path)["jobs"].values() if "IRONBEE_IMAGE" in j.get("env", {})]
            self.assertEqual(len(refs), 1, path)
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
        self.assertIn("shellcheck --shell=bash --external-sources --severity=warning scripts/*.sh", runs)
        self.assertIn("bash scripts/build-no-queue.sh --check", runs)
        self.assertIn("sha256sum --check --strict", runs)
        self.assertIn(".github/workflows/*.yml", runs)

    def test_the_release_takes_its_one_input_through_the_environment(self):
        self.assertEqual(triggers(self.release), {"workflow_dispatch"})
        inputs = self.release["on"]["workflow_dispatch"]["inputs"]
        self.assertEqual({k: (v["type"], v["required"]) for k, v in inputs.items()}, {"image-tag": ("string", True)})
        self.assertEqual(self.release["env"], {"IRONBEE_IMAGE_TAG": "${{ inputs.image-tag }}"})
        self.assertEqual(self.release["run-name"], "Release ${{ inputs.image-tag }}")
        for where, text in strings(self.release["jobs"]):
            self.assertNotIn("inputs.", text, "/".join(where))

    def test_the_release_runs_its_script_one_step_at_a_time(self):
        runs = [s["run"] for j in self.release["jobs"].values() for s in j["steps"] if "run" in s]
        self.assertEqual(runs, ["bash scripts/release.sh digest", "bash scripts/release.sh plan", "bash scripts/release.sh index",
                                "bash scripts/release.sh signature", 'bash scripts/release.sh image "$ARCH"', "bash scripts/release.sh token",
                                "bash scripts/release.sh publish", "bash scripts/release.sh github-release"])
        self.assertEqual(self.release["jobs"]["publish"]["needs"], ["plan", "image"])
        self.assertEqual(self.release["jobs"]["image"]["needs"], "plan")

    def test_the_tag_is_read_once_and_every_later_step_works_by_its_digest(self):
        plan = self.release["jobs"]["plan"]
        steps = plan["steps"]
        i = next(i for i, s in enumerate(steps) if s.get("run") == "bash scripts/release.sh digest")
        self.assertEqual(steps[i]["id"], "digest")
        self.assertTrue(any("docker/login-action@" in s.get("uses", "") for s in steps[:i]))         # the tag is read signed in
        self.assertEqual(plan["outputs"]["digest"], "${{ steps.digest.outputs.digest }}")
        for s in steps[i + 1:]:
            if "run" in s: self.assertEqual(s["env"]["IRONBEE_IMAGE_DIGEST"], "${{ steps.digest.outputs.digest }}", s["run"])
        for name in ("image", "publish"):
            self.assertEqual(self.release["jobs"][name]["env"], {"IRONBEE_IMAGE_DIGEST": "${{ needs.plan.outputs.digest }}"})
        self.assertNotIn("IRONBEE_IMAGE_DIGEST", steps[i].get("env", {}))

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
