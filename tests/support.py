"""What the scripts' tests share. A script runs with bash as a job runs it, its environment given whole (so on github.com
unless a test names a GITHUB_SERVER_URL), with the stubs
first on PATH: `gh` (tests/stubs/gh, a small GitHub of acme/widgets), `sleep` (records the pause, waits none), and for
the release `docker` (a registry and a daemon) and `cosign`. IronBee's API is a stub on the loopback interface. The
events are recorded ones (tests/fixtures/events). No network."""
from __future__ import annotations

import copy
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
STUBS = ROOT / "tests" / "stubs"

REPO = "acme/widgets"
JOB_TOKEN = "job-token"                                     # the job's token: github-actions
APP_TOKEN = "app-token"                                     # the customer's own App's installation token
APP_SLUG = "acme-reviewer"
JOB_LOGIN = "github-actions[bot]"
APP_LOGIN = f"{APP_SLUG}[bot]"
HEAD = "2" * 40                                             # the recorded pull request's head
GROUP_HEAD = "9" * 40                                       # the recorded merge group's commit
SERVER = "ghes.acme.com"                                    # a GitHub Enterprise Server's host
TENANT = "acme.ghe.com"                                     # a GHE.com tenant's host


def event(name: str) -> dict:
    return json.loads((FIXTURES / "events" / f"{name}.json").read_text())


def marked(text: str, mark: str = "f1") -> str:
    """A text of ours as the reviewer writes it: our hidden marker on a line of its own."""
    return f"{text}\n\n<!-- ironbee {mark} -->"


def github(host: str = "github.com") -> dict:
    """The stub GitHub's state: acme/widgets on `host` with pull request 7, the recorded one."""
    pull = event("pull_request_review_comment.created")["pull_request"]
    return {"host": host, "repo": REPO, "tokens": {JOB_TOKEN: "github-actions", APP_TOKEN: APP_SLUG, "other-token": "other-app"},
            "checks": [], "reviews": {}, "comments": {}, "pulls": {"7": pull},
            "permissions": {"alice": "write", "bob": "admin", "carol": "maintain", "reader": "read"}, "runs": [], "jobs": {}, "fail": [],
            "next_id": 1000}


def on_host(host: str) -> dict:
    """What Actions gives a job on `host`: its server's address, as a GHE.com tenant's and a server's jobs read it."""
    return {"GITHUB_SERVER_URL": f"https://{host}"}


CHECK = "Code Review Result"                                # the check's name, the only one written
CHECK_PRE = "IronBee review"                                # the name the pre-releases wrote, still read as ours


def check(conclusion: str, app: str = "github-actions", head: str = HEAD, name: str = CHECK, title: str = "t", summary: str = "s") -> dict:
    """A check run another writer makes around ours (the stub's on_create), `app` the slug of the App it writes as."""
    return {"name": name, "head_sha": head, "status": "completed", "conclusion": conclusion, "output": {"title": title, "summary": summary}, "app": app}


def seed_check(state: dict, conclusion: str, **kw) -> dict:
    """A check run already on the commit before the script runs."""
    row = check(conclusion, **kw); state["next_id"] += 1
    row = {**row, "id": state["next_id"], "app": {"slug": row["app"]}}; state["checks"].append(row)
    return row


@dataclass
class Ran:
    code: int
    out: str
    err: str
    outputs: dict          # what the script wrote to GITHUB_OUTPUT
    calls: list            # the stub gh's calls, in order
    state: dict            # the stub GitHub after the run
    sleeps: list           # the pauses asked for

    def writes(self) -> list:
        return [c for c in self.calls if c["method"] != "GET"]


class ScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="ironbee-scripts-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = github()

    def run_script(self, script: str, env: dict | None = None, ev: tuple | None = None, args: tuple = (), cwd: Path | None = None) -> Ran:
        """`ev`: (GitHub's event name, its payload), handed over as a job is: GITHUB_EVENT_NAME and the event file.
        `cwd`: where the script runs, the test's own directory when not given."""
        files = {k: self.tmp / k for k in ("state.json", "calls.jsonl", "sleeps", "output")}
        files["state.json"].write_text(json.dumps(self.state))
        for k in ("calls.jsonl", "sleeps", "output"): files[k].write_text("")
        e = {"PATH": f"{STUBS}{os.pathsep}{os.environ['PATH']}", "HOME": str(self.tmp), "TMPDIR": str(self.tmp),
             "STUB_GH_STATE": str(files["state.json"]), "STUB_GH_CALLS": str(files["calls.jsonl"]), "STUB_SLEEP_LOG": str(files["sleeps"]),
             "GITHUB_OUTPUT": str(files["output"]), "GITHUB_REPOSITORY": REPO, "GH_TOKEN": JOB_TOKEN}
        if ev is not None:
            path = self.tmp / "event.json"; path.write_text(json.dumps(ev[1]))
            e.update(GITHUB_EVENT_NAME=ev[0], GITHUB_EVENT_PATH=str(path))
        e.update(env or {})
        p = subprocess.run(["bash", str(SCRIPTS / script), *args], env={k: v for k, v in e.items() if v is not None}, capture_output=True, text=True, timeout=120,
                           cwd=cwd or self.tmp)
        outputs = dict(line.split("=", 1) for line in files["output"].read_text().splitlines() if line)
        calls = [json.loads(line) for line in files["calls.jsonl"].read_text().splitlines() if line]
        return Ran(p.returncode, p.stdout, p.stderr, outputs, calls, json.loads(files["state.json"].read_text()), files["sleeps"].read_text().split())


def changed(payload: dict, **paths) -> dict:
    """A copy of an event with values set by paths, their keys joined by `__` (`comment__user__type="Bot"`); None
    removes the key."""
    out = copy.deepcopy(payload)
    for dotted, value in paths.items():
        keys = dotted.split("__"); node = out
        for k in keys[:-1]: node = node[k]
        if value is None: node.pop(keys[-1], None)
        else: node[keys[-1]] = value
    return out


class StubApi:
    """An API on 127.0.0.1 (IronBee's, or GitHub's for the release): each request recorded (method, path, headers, body),
    each answered by the next of `answers` ((status, body) or (status, body, headers): a body dict or list as JSON, a
    str as it is), the last one again when they run out."""

    def __init__(self, answers: list):
        self.answers = list(answers); self.requests = []
        api = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None: self.answer()
            def do_PUT(self) -> None: self.answer()
            def do_POST(self) -> None: self.answer()

            def answer(self) -> None:
                size = int(self.headers.get("Content-Length") or 0); raw = self.rfile.read(size)
                api.requests.append({"method": self.command, "path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": raw.decode()})
                status, body, *headers = api.answers.pop(0) if len(api.answers) > 1 else api.answers[0]
                data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data)))
                for name, value in (headers[0] if headers else {}).items(): self.send_header(name, value)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None: pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def stop(self) -> None:
        self.server.shutdown(); self.server.server_close()
