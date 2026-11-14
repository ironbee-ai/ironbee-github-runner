"""The register job (scripts/register.sh) against a stub of IronBee's API: the body (runner 1.0.0's, frozen), each answer
and each refusal, the attempts, and a log that names no number of the contract."""
from __future__ import annotations

import datetime
import json
import socket
import unittest

from support import FIXTURES, REPO, ScriptTest, StubApi

PROJECT = "3f1c2a9e-8b7d-4e6f-9a0b-1c2d3e4f5a6b"
USED, LIMIT = 4242, 4141                                     # numbers no log may carry
STANDING = {"licence": {"developers": {"limit": 50, "used": 41}, "endsAt": "2099-11-13"}, "runner": {"supportedUntil": None, "moveTo": None}}


def day(offset: int) -> str:
    return (datetime.datetime.now(datetime.UTC).date() + datetime.timedelta(days=offset)).isoformat()


def registered(created: bool = True, **over) -> tuple:
    return 200, {"project": {"id": PROJECT, "created": created}, "noProject": None, **STANDING, **over}


def refused(status: int, code: str, message: str = "Refused.", details: dict | None = None) -> tuple:
    return status, {"error": {"code": code, "message": message, **({"details": details} if details is not None else {})}}


class Register(ScriptTest):
    def register(self, *answers, env: dict | None = None, args: tuple = ()):
        api = StubApi(list(answers)); self.addCleanup(api.stop)
        e = {"IRONBEE_API_KEY": "ib-key-0123", "IRONBEE_RUNNER_VERSION": "1.0.0", "IRONBEE_API_URL": api.url, "GITHUB_REPOSITORY": REPO,
             "NO_PROXY": "*", "no_proxy": "*"}
        e.update(env or {})
        return self.run_script("register.sh", e, args=args), api.requests


class TheCall(Register):
    def test_the_body_is_runner_1_0_0s_frozen_registration(self):
        ran, [req] = self.register(registered())
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual(json.loads(req["body"]), json.loads((FIXTURES / "register-1.0.0.json").read_text()))
        self.assertEqual((req["method"], req["path"]), ("PUT", "/v1/code-review-repositories"))
        self.assertEqual(req["headers"]["x-api-key"], "ib-key-0123")
        self.assertEqual(req["headers"]["content-type"], "application/json")
        self.assertEqual(req["headers"]["user-agent"], "ironbee-runner/1.0.0")
        self.assertNotIn("ib-key-0123", ran.out + ran.err)

    def test_a_repository_named_by_hand(self):
        ran, [req] = self.register(registered(), args=("acme/gadgets",))
        self.assertEqual(json.loads(req["body"])["repository"], {"provider": "github", "path": "acme/gadgets"})
        self.assertIn("registered acme/gadgets", ran.out)

    def test_the_api_url_may_end_with_a_slash(self):
        api = StubApi([registered()]); self.addCleanup(api.stop)
        ran = self.run_script("register.sh", {"IRONBEE_API_KEY": "k", "IRONBEE_RUNNER_VERSION": "1.0.0", "IRONBEE_API_URL": api.url + "/", "NO_PROXY": "*", "no_proxy": "*"})
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual(api.requests[0]["path"], "/v1/code-review-repositories")


class Answers(Register):
    def test_a_project_made_now(self):
        ran, _ = self.register(registered(created=True))
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn(f"registered {REPO}: project {PROJECT}, made now", ran.out)

    def test_a_project_found(self):
        ran, _ = self.register(registered(created=False))
        self.assertIn(f"registered {REPO}: project {PROJECT}, found", ran.out)

    def test_each_case_that_leaves_the_repository_without_a_project(self):
        for case in ("project_limit", "project_archived", "name_taken"):
            with self.subTest(case):
                ran, _ = self.register((200, {"project": None, "noProject": case, **STANDING}))
                self.assertEqual(ran.code, 0, ran.out)
                self.assertIn(f"registered {REPO} without a project ({case}): its pull requests are reviewed with the account's settings", ran.out)

    def test_a_case_this_release_does_not_know_is_dropped(self):
        ran, _ = self.register((200, {"project": None, "noProject": "a_newer_case", **STANDING}))
        self.assertEqual(ran.code, 0, ran.out)
        self.assertIn('dropped noProject "a_newer_case"', ran.out)
        self.assertIn("without a project (no case given)", ran.out)

    def test_members_this_release_does_not_know_are_ignored(self):
        ran, _ = self.register(registered(somethingNew={"x": 1}))
        self.assertEqual(ran.code, 0, ran.out)

    def test_an_answer_that_cannot_be_read_fails(self):
        for body in ("not json", [], "null"):
            with self.subTest(body):
                ran, _ = self.register((200, body))
                self.assertEqual(ran.code, 1)
                self.assertIn("could not be read", ran.out)


class Warnings(Register):
    def standing(self, developers: dict, ends: str, until=None, move=None) -> tuple:
        return registered(licence={"developers": developers, "endsAt": ends}, runner={"supportedUntil": until, "moveTo": move})

    def assertNoContractNumber(self, log: str, *numbers) -> None:
        for n in numbers: self.assertNotIn(str(n), log)

    def test_over_the_developer_limit(self):
        ran, _ = self.register(self.standing({"limit": LIMIT, "used": USED}, day(200)))
        self.assertIn("warning: this account has more developers this month than its licence covers", ran.out)
        self.assertNoContractNumber(ran.out, LIMIT, USED, day(200))

    def test_within_the_limit_no_warning(self):
        ran, _ = self.register(self.standing({"limit": USED, "used": USED}, day(200)))
        self.assertNotIn("warning", ran.out)

    def test_the_licences_last_fourteen_days(self):
        for offset in (0, 5, 13):
            with self.subTest(offset):
                ran, _ = self.register(self.standing({"limit": LIMIT, "used": 1}, day(offset)))
                self.assertIn("warning: the licence for IronBee's self-hosted review ends soon", ran.out)
                self.assertNoContractNumber(ran.out, LIMIT, day(offset))
        for offset in (14, 60):
            with self.subTest(offset):
                ran, _ = self.register(self.standing({"limit": LIMIT, "used": 1}, day(offset)))
                self.assertNotIn("warning", ran.out)

    def test_a_versions_last_day_names_the_day_and_the_version_to_move_to(self):
        ran, _ = self.register(self.standing({"limit": LIMIT, "used": 1}, day(200), until="2027-06-30", move="2.0.0"))
        self.assertIn("warning: runner 1.0.0 is served until 2027-06-30; move the workflow to 2.0.0 before then", ran.out)
        ran, _ = self.register(self.standing({"limit": LIMIT, "used": 1}, day(200), until="2027-06-30", move="two"))
        self.assertIn("move the workflow to a supported version before then", ran.out)

    def test_values_that_are_not_days_or_counts_warn_of_nothing(self):
        ran, _ = self.register(self.standing({"limit": "50", "used": 51.5}, "2027-02-30", until="soon"))
        self.assertEqual(ran.code, 0, ran.out)
        self.assertNotIn("warning", ran.out)

    def test_every_warning_at_once_still_registers(self):
        ran, _ = self.register(self.standing({"limit": LIMIT, "used": USED}, day(3), until=day(40), move="2.0.0"))
        self.assertEqual(ran.code, 0, ran.out)
        self.assertEqual(sum(line.startswith("warning:") for line in ran.out.splitlines()), 3)
        self.assertNoContractNumber(ran.out, LIMIT, USED, day(3))


class Refusals(Register):
    def test_each_refusal_fails_the_job_with_its_sentence(self):
        statuses = {"SELF_HOSTED_RUNNER_NOT_ENABLED": (403, "is not enabled for this account"),
                    "SELF_HOSTED_RUNNER_SUSPENDED": (403, "are suspended for this account"),
                    "SELF_HOSTED_RUNNER_LICENCE_ENDED": (403, "has ended; contact IronBee to renew it"),
                    "REPOSITORY_REVIEWED_BY_CLOUD": (409, "IronBee's cloud reviews this repository")}
        for code, (status, says) in statuses.items():
            with self.subTest(code):
                details = {"endsAt": "2026-11-01"} if code.endswith("LICENCE_ENDED") else None
                ran, reqs = self.register(refused(status, code, details=details))
                self.assertEqual(ran.code, 1)
                self.assertEqual(len(reqs), 1)
                self.assertIn(f"::error::IronBee refused the registration ({code}): ", ran.out)
                self.assertIn(says, ran.out)
                self.assertNotIn("2026-11-01", ran.out)

    def test_a_version_no_longer_served(self):
        ran, _ = self.register(refused(400, "RUNNER_VERSION_UNSUPPORTED", details={"moveTo": "2.0.0", "supportedUntil": "2026-10-01", "reason": None}))
        self.assertEqual(ran.code, 1)
        self.assertIn("This version of the IronBee runner is no longer served; move the workflow to 2.0.0.", ran.out)
        self.assertNotIn("Reason", ran.out)

    def test_a_version_stopped_at_once_says_why(self):
        ran, _ = self.register(refused(400, "RUNNER_VERSION_UNSUPPORTED", details={"moveTo": "1.0.1", "supportedUntil": "2026-10-01", "reason": "It can post\n a review twice."}))
        self.assertIn("move the workflow to 1.0.1. Reason: It can post a review twice.", ran.out)

    def test_a_code_this_release_does_not_know_shows_the_apis_text(self):
        ran, _ = self.register(refused(403, "SOMETHING_NEW", "Registrations are paused for maintenance."))
        self.assertEqual(ran.code, 1)
        self.assertIn("(SOMETHING_NEW): Registrations are paused for maintenance.", ran.out)

    def test_a_refusal_with_no_body(self):
        ran, _ = self.register((401, ""))
        self.assertEqual(ran.code, 1)
        self.assertIn("(HTTP_401): HTTP 401", ran.out)

    def test_a_percent_sign_is_kept_in_the_annotation(self):
        ran, _ = self.register(refused(403, "SOMETHING_NEW", "100% sure"))
        self.assertIn("100%25 sure", ran.out)


class Attempts(Register):
    def test_a_moments_refusal_is_tried_again(self):
        for status in (503, 429, 500):
            with self.subTest(status):
                ran, reqs = self.register((status, {"error": {"code": "X", "message": "busy"}}), registered())
                self.assertEqual(ran.code, 0, ran.out)
                self.assertEqual(len(reqs), 2)
                self.assertEqual(ran.sleeps, ["2"])

    def test_three_attempts_and_no_more(self):
        ran, reqs = self.register((502, "bad gateway"))
        self.assertEqual(ran.code, 1)
        self.assertEqual(len(reqs), 3)
        self.assertEqual(ran.sleeps, ["2", "5"])
        self.assertIn("::error::IronBee: no answer after 3 attempts (HTTP 502)", ran.out)

    def test_an_api_that_cannot_be_reached(self):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        ran = self.run_script("register.sh", {"IRONBEE_API_KEY": "k", "IRONBEE_RUNNER_VERSION": "1.0.0", "IRONBEE_API_URL": f"http://127.0.0.1:{port}", "NO_PROXY": "*", "no_proxy": "*"})
        self.assertEqual(ran.code, 1)
        self.assertIn("no answer after 3 attempts (no connection", ran.out)
        self.assertEqual(ran.sleeps, ["2", "5"])


class Configuration(Register):
    def test_no_api_key(self):
        ran, reqs = self.register(registered(), env={"IRONBEE_API_KEY": ""})
        self.assertEqual(ran.code, 2)
        self.assertEqual(reqs, [])
        self.assertIn("ironbee-api-key", ran.out)

    def test_a_version_that_is_not_major_minor_patch(self):
        for version in ("", "1.0", "v1.0.0", "01.0.0"):
            with self.subTest(version):
                ran, reqs = self.register(registered(), env={"IRONBEE_RUNNER_VERSION": version})
                self.assertEqual(ran.code, 2)
                self.assertEqual(reqs, [])

    def test_a_repository_that_is_not_owner_and_name(self):
        for repo in ("acme", "acme/widgets/x", "/widgets", "acme/"):
            with self.subTest(repo):
                ran, reqs = self.register(registered(), args=(repo,))
                self.assertEqual(ran.code, 2)
                self.assertEqual(reqs, [])


if __name__ == "__main__":
    unittest.main()
