"""The review step (scripts/review.sh) against a stub registry and daemon (tests/stubs/docker): the registry token in a
configuration of the step's own that names no credential helper, gone before the image runs; the pull by digest; the
run as the job's user (the container's root under rootless Docker; userns-remap refused) with the event file read-only
and the step's outputs file mounted; every variable of the workflow's review step handed on by name and no secret on
any command line; the docker client as the step's own process, and a signal before it stopping the pull with nothing
run; the runner's `concluding` and exit code; the stop of a container left behind."""
from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
import time
import unittest
from pathlib import Path

from support import REPO, ROOT, SCRIPTS, STUBS, ScriptTest, event

try:
    import yaml
except ImportError:                                          # pragma: no cover
    yaml = None

IMAGE = "docker.io/ironbeeai/ironbee-code-review-runner@sha256:" + "a" * 64
TOKEN = "dckr_oat_registry-token-value"
HEAD = "2" * 40
SECRETS = {"IRONBEE_MODEL_KEY": "sk-model-key-value", "IRONBEE_MODEL_HEADERS": "X-Gateway=gateway-header-value",
           "IRONBEE_JEV_KEY": "jev-key-value", "IRONBEE_API_KEY": "ib-api-key-value", "IRONBEE_KNOWLEDGE_TOKEN": "knowledge-token-value",
           "IRONBEE_APP_ID": "123456", "IRONBEE_APP_PRIVATE_KEY": "-----BEGIN RSA PRIVATE KEY-----\nkey\n-----END RSA PRIVATE KEY-----",
           "GITHUB_TOKEN": "ghs_job-token-value"}
ACTIONS = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REPOSITORY": REPO, "GITHUB_API_URL": "https://api.github.com"}


def review_step_env() -> dict:
    """The workflow's review step's variables, each given a value of its own."""
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "code-review.yml").read_text())
    [step] = [s for s in wf["jobs"]["review"]["steps"] if s.get("id") == "review"]
    return {name: SECRETS.get(name, f"value-of-{name}") for name in step["env"]}


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class Review(ScriptTest):
    def setUp(self) -> None:
        super().setUp()
        self.temp = self.tmp / "runner-temp"; self.temp.mkdir()
        self.registry = {"arch": "amd64", "manifests": {}, "tags": {}, "token": TOKEN,
                         "images": {IMAGE: {"os": "linux", "architecture": "amd64", "version": "1.0.0"}}}

    def review(self, *args, payload: dict | None = None, **env):
        files = {"docker.json": self.tmp / "docker.json", "docker.calls": self.tmp / "docker.calls"}
        files["docker.json"].write_text(json.dumps(self.registry)); files["docker.calls"].write_text("")
        e = {**review_step_env(), "IRONBEE_REGISTRY_TOKEN": TOKEN, "IRONBEE_IMAGE": IMAGE, **ACTIONS, "RUNNER_TEMP": str(self.temp),
             "STUB_DOCKER_STATE": str(files["docker.json"]), "STUB_DOCKER_CALLS": str(files["docker.calls"])}
        e.update(env)
        ran = self.run_script("review.sh", e, ("pull_request", payload or event("pull_request.opened")), args=args)
        self.docker = json.loads(files["docker.json"].read_text())
        self.calls = [json.loads(line) for line in files["docker.calls"].read_text().splitlines() if line]
        return ran

    def run_of(self) -> dict:
        [run] = self.docker["runs"]
        return run

    def started(self) -> subprocess.Popen:
        """The script started as the step starts it, its process kept: what a signal is sent to."""
        state, calls, output = self.tmp / "docker.json", self.tmp / "docker.calls", self.tmp / "output"
        state.write_text(json.dumps(self.registry)); calls.write_text(""); output.write_text("")
        events = self.tmp / "event.json"; events.write_text(json.dumps(event("pull_request.opened")))
        env = {"PATH": f"{STUBS}{os.pathsep}{os.environ['PATH']}", "HOME": str(self.tmp), "TMPDIR": str(self.tmp), **review_step_env(),
               "IRONBEE_REGISTRY_TOKEN": TOKEN, "IRONBEE_IMAGE": IMAGE, **ACTIONS, "RUNNER_TEMP": str(self.temp), "GITHUB_EVENT_PATH": str(events),
               "GITHUB_OUTPUT": str(output), "STUB_DOCKER_STATE": str(state), "STUB_DOCKER_CALLS": str(calls)}
        return subprocess.Popen(["bash", str(SCRIPTS / "review.sh")], env=env, cwd=self.tmp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def daemon(self) -> dict:
        return json.loads((self.tmp / "docker.json").read_text())


class TheRun(Review):
    def test_the_token_in_a_configuration_of_the_steps_own_for_the_pull_alone(self):
        ran = self.review()
        self.assertEqual(ran.code, 0, ran.out)
        [pull] = self.docker["pulls"]
        self.assertEqual((pull["ref"], pull["auth"], pull["helpers"]), (IMAGE, f"ironbeeai:{TOKEN}", None))   # by digest; Docker Hub's entry, no helper
        self.assertFalse(Path(pull["config"]).exists())                                          # the token's configuration is gone
        self.assertEqual([c[0] for c in self.calls], ["info", "pull", "run"])                    # no login: no credential helper is asked
        self.assertNotIn("DOCKER_CONFIG", self.run_of()["env"])

    def test_under_rootless_docker_as_the_containers_root_which_is_the_jobs_user(self):
        self.registry["security"] = ["name=seccomp,profile=builtin", "name=rootless", "name=cgroupns"]
        self.assertEqual(self.review().code, 0)
        args = self.run_of()["args"]
        self.assertEqual(args[args.index("--user") + 1], "0:0")

    def test_userns_remap_is_refused_before_the_pull(self):
        self.registry["security"] = ["name=seccomp,profile=builtin", "name=userns"]
        ran = self.review()
        self.assertEqual(ran.code, 2)
        self.assertIn("::error::Docker runs with userns-remap, which the review step does not support", ran.out)
        self.assertEqual([c[0] for c in self.calls], ["info"])

    def test_a_daemon_out_of_reach(self):
        self.registry["no_daemon"] = True
        ran = self.review()
        self.assertEqual(ran.code, 1)
        self.assertIn("::error::docker could not reach its daemon: Cannot connect to the Docker daemon", ran.out)
        self.assertEqual([c[0] for c in self.calls], ["info"])

    def test_the_image_by_digest_as_the_jobs_user_with_the_runners_command(self):
        self.review()
        args = self.run_of()["args"]
        self.assertEqual(args[-3:], [IMAGE, "ironbee-runner", "--print-report"])
        self.assertIn("--rm", args)
        self.assertEqual(args[args.index("--user") + 1], f"{os.getuid()}:{os.getgid()}")
        self.assertEqual(args[args.index("--cidfile") + 1], str(self.temp / "ironbee-review.cid"))
        self.assertNotIn("-d", args); self.assertNotIn("--detach", args)                         # attached, so it proxies a signal

    def test_the_event_file_read_only_and_the_steps_outputs_file(self):
        self.review()
        run = self.run_of(); args = run["args"]
        mounts = sorted(args[i + 1] for i, a in enumerate(args) if a == "--mount")
        self.assertEqual(mounts, [f"type=bind,source={self.tmp / 'event.json'},target=/github/event.json,readonly",
                                  f"type=bind,source={self.tmp / 'output'},target=/github/output"])
        self.assertEqual((run["env"]["GITHUB_EVENT_PATH"], run["env"]["GITHUB_OUTPUT"]), ("/github/event.json", "/github/output"))

    def test_every_variable_of_the_review_step_reaches_the_runner_but_the_registry_token(self):
        self.review()
        step = review_step_env(); step.pop("IRONBEE_REGISTRY_TOKEN")
        want = {**step, **ACTIONS, "GITHUB_EVENT_PATH": "/github/event.json", "GITHUB_OUTPUT": "/github/output"}
        self.assertEqual(self.run_of()["env"], want)

    def test_no_secret_on_any_command_line(self):
        ran = self.review()
        argv = json.dumps(self.calls)
        for value in [TOKEN, base64.b64encode(f"ironbeeai:{TOKEN}".encode()).decode(), *SECRETS.values()]:
            self.assertNotIn(value, argv)
            self.assertNotIn(value, ran.out)
        for name in SECRETS:
            args = self.run_of()["args"]
            self.assertEqual(args[args.index(name) - 1], "-e")                                    # by name alone

    def test_a_proxy_of_the_runners_machine_is_handed_on_and_none_is_made_up(self):
        self.review()
        self.assertFalse({"HTTPS_PROXY", "https_proxy", "NO_PROXY"} & set(self.run_of()["env"]))
        self.review(HTTPS_PROXY="http://proxy.internal:3128", NO_PROXY="localhost")
        env = self.run_of()["env"]
        self.assertEqual((env["HTTPS_PROXY"], env["NO_PROXY"]), ("http://proxy.internal:3128", "localhost"))

    def test_the_runners_concluding_lands_in_the_steps_outputs(self):
        self.registry["concluding"] = HEAD
        ran = self.review()
        self.assertEqual(ran.outputs, {"concluding": HEAD})

    def test_the_runners_exit_is_the_steps(self):
        for code in (1, 2):
            with self.subTest(code):
                self.registry["exit"] = code
                self.assertEqual(self.review().code, code)


class Signals(Review):
    def test_the_docker_client_is_the_steps_own_process(self):
        """The script execs docker, as the workflow's step execs the script: a signal to the step is a signal to docker."""
        proc = self.started()
        out, _ = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, 0, out)
        self.assertEqual(self.daemon()["runs"][0]["pid"], proc.pid)

    def test_a_signal_during_the_pull_stops_it_and_runs_nothing(self):
        for sig, code in ((signal.SIGTERM, 143), (signal.SIGINT, 130)):
            with self.subTest(sig.name):
                self.registry["pull_sleeps"] = 30
                proc = self.started()
                deadline = time.monotonic() + 20
                while not self.daemon().get("pulls") and time.monotonic() < deadline: time.sleep(0.05)
                [pull] = self.daemon()["pulls"]
                began = time.monotonic(); proc.send_signal(sig)
                out, _ = proc.communicate(timeout=10)
                self.assertLess(time.monotonic() - began, 5)                                     # at once, not when the pull ends
                self.assertEqual(proc.returncode, code, out)
                self.assertIn("stopped before the image ran; nothing was run", out)
                self.assertNotIn("runs", self.daemon())
                self.assertFalse(Path(pull["config"]).exists())                                  # the token's configuration with it
                while time.monotonic() < deadline:
                    try: os.kill(pull["pid"], 0)
                    except ProcessLookupError: break
                    time.sleep(0.05)
                else: self.fail("the pull goes on")


class Refused(Review):
    def test_a_refused_token_runs_nothing(self):
        self.registry["token"] = "another"
        ran = self.review()
        self.assertEqual(ran.code, 1)
        self.assertIn(f"::error::the runner's image could not be pulled ({IMAGE}): Error response from daemon: unauthorized", ran.out)
        self.assertEqual([c[0] for c in self.calls], ["info", "pull"])

    def test_an_image_that_cannot_be_pulled_runs_nothing(self):
        self.registry["images"] = {}
        ran = self.review()
        self.assertEqual(ran.code, 1)
        self.assertIn(f"::error::the runner's image could not be pulled ({IMAGE})", ran.out)
        self.assertEqual([c[0] for c in self.calls], ["info", "pull"])

    def test_the_steps_configuration(self):
        cases = {"an image by tag": {"IRONBEE_IMAGE": "docker.io/ironbeeai/ironbee-code-review-runner:1.0.0"},
                 "an image of another registry": {"IRONBEE_IMAGE": "ghcr.io/ironbeeai/ironbee-code-review-runner@sha256:" + "a" * 64},
                 "no registry token": {"IRONBEE_REGISTRY_TOKEN": ""},
                 "no runner temp": {"RUNNER_TEMP": str(self.tmp / "none")},
                 "an event path that is not absolute": {"GITHUB_EVENT_PATH": "event.json"},
                 "an output file that is not there": {"GITHUB_OUTPUT": str(self.tmp / "none" / "output")}}
        for name, env in cases.items():
            with self.subTest(name):
                ran = self.review(**env)
                self.assertEqual(ran.code, 2, ran.out)
                self.assertEqual(self.calls, [])
        self.assertEqual(self.review("again").code, 2)


class Stop(Review):
    def test_nothing_after_a_run_that_ended(self):
        self.review()
        ran = self.review("stop")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual([c[:2] for c in self.calls], [["container", "inspect"]])
        self.assertFalse((self.temp / "ironbee-review.cid").exists())

    def test_a_container_left_behind_is_stopped_and_removed(self):
        self.registry["left"] = True
        self.review(); left = self.docker["containers"]
        self.registry = self.docker
        ran = self.review("stop")
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual((self.docker["stopped"], self.docker["containers"]), (left, []))
        self.assertEqual(self.calls[1][:3], ["stop", "--time", "15"])
        self.assertIn("stopped and removed", ran.out)

    def test_no_run_no_container_and_never_a_failure(self):
        for env in ({}, {"RUNNER_TEMP": ""}, {"IRONBEE_IMAGE": ""}):
            with self.subTest(env):
                ran = self.review("stop", **env)
                self.assertEqual((ran.code, self.calls), (0, []), ran.out)
        (self.temp / "ironbee-review.cid").write_text("not an id")
        self.assertEqual(self.review("stop").code, 0)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
