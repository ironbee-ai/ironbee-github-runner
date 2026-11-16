"""The restart step of the workflow without a queue (scripts/restart.sh): a run of the pull request's group that handed
on no review starts again the newest review of the head that was cancelled, when the head holds nothing of ours and
that run holds our job alone; with the job's token, on the job's host."""
from __future__ import annotations

import unittest

from support import APP_LOGIN, APP_SLUG, HEAD, JOB_LOGIN, JOB_TOKEN, SERVER, ScriptTest, changed, event, github, marked, on_host, seed_check

RUN, WORKFLOW = 500, 77                                       # this run, and its workflow (the calling repository's file)
OURS = {"name": "Code Review / Job", "status": "completed", "conclusion": "cancelled"}
RUNS = f"repos/acme/widgets/actions/workflows/{WORKFLOW}/runs?event=pull_request&head_sha={HEAD}&status=cancelled&per_page=100"


def run(id_: int, event_name: str = "pull_request", head: str = HEAD, conclusion: str | None = "cancelled", workflow: int = WORKFLOW,
        status: str = "completed") -> dict:
    return {"id": id_, "workflow_id": workflow, "event": event_name, "head_sha": head, "status": status, "conclusion": conclusion}


class Restart(ScriptTest):
    def setUp(self) -> None:
        super().setUp()
        self.seed()

    def seed(self) -> None:
        self.state["runs"] = [run(RUN, "issue_comment", status="in_progress", conclusion=None), run(480)]
        self.state["jobs"] = {"480": [{**OURS, "id": 9480}]}

    def restart(self, payload: dict | None = None, name: str = "issue_comment", **env):
        e = {"GITHUB_RUN_ID": str(RUN), "IRONBEE_APP_SLUG": ""}
        e.update(env)
        return self.run_script("restart.sh", e, (name, payload or event("issue_comment.created")))

    def assertNothing(self, ran, says: str) -> None:
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual(ran.writes(), [])
        self.assertEqual(ran.state.get("reruns", []), [])
        self.assertIn(says, ran.out)
        self.assertIn("nothing started again", ran.out)


class StartedAgain(Restart):
    def test_a_cancelled_review_with_our_job_alone_is_started_again(self):
        ran = self.restart()
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual(ran.state["reruns"], [480])
        self.assertEqual([(c["method"], c["path"]) for c in ran.calls],
                         [("GET", "repos/acme/widgets/pulls/7"),
                          ("GET", f"repos/acme/widgets/commits/{HEAD}/check-runs?check_name=Code%20Review%20Result&filter=all&per_page=100"),
                          ("GET", f"repos/acme/widgets/commits/{HEAD}/check-runs?check_name=IronBee%20review&filter=all&per_page=100"),
                          ("GET", "repos/acme/widgets/pulls/7/reviews?per_page=100"),
                          ("GET", f"repos/acme/widgets/actions/runs/{RUN}"), ("GET", RUNS),
                          ("GET", "repos/acme/widgets/actions/runs/480/jobs?per_page=100"), ("POST", "repos/acme/widgets/actions/runs/480/rerun")])
        self.assertEqual({c["token"] for c in ran.calls}, {JOB_TOKEN})
        self.assertIn("restart: run 480, the review of 2222222 a newer run replaced while it waited, started again", ran.out)

    def test_the_newest_cancelled_review_of_this_workflow_on_the_head(self):
        self.state["runs"] += [run(470), run(490, workflow=88), run(495, head="3" * 40), run(496, "issue_comment"), run(497, conclusion="success"),
                               run(498, conclusion="failure")]
        self.state["jobs"].update({str(n): [{**OURS, "id": n}] for n in (470, 490, 495, 496, 497, 498)})
        ran = self.restart()
        self.assertEqual(ran.state["reruns"], [480])

    def test_a_reply_on_a_thread_and_a_pull_requests_own_event_name_the_pull_request(self):
        for name, payload in (("pull_request_review_comment", event("pull_request_review_comment.created")), ("pull_request", event("pull_request.opened"))):
            with self.subTest(name):
                self.seed()
                ran = self.restart(payload, name)
                self.assertEqual(ran.state["reruns"], [480], ran.out + ran.err)

    def test_on_a_server_with_its_host_and_its_token(self):
        self.state = github(SERVER); self.seed()
        ran = self.restart(**on_host(SERVER))
        self.assertEqual(ran.state["reruns"], [480], ran.out + ran.err)
        self.assertEqual({(c["host"], c["token"]) for c in ran.calls}, {(SERVER, JOB_TOKEN)})

    def test_a_job_list_with_no_job_is_no_other_job(self):
        self.state["jobs"] = {"480": []}
        self.assertEqual(self.restart().state["reruns"], [480])


class LeftAsItIs(Restart):
    def test_a_head_with_a_check_of_ours(self):
        for conclusion in ("neutral", "success", "action_required"):
            with self.subTest(conclusion):
                self.state["checks"] = []
                seed_check(self.state, conclusion)
                ran = self.restart()
                self.assertNothing(ran, "2222222 holds a check of ours")
                self.assertFalse([c for c in ran.calls if "/actions/" in c["path"]])

    def test_a_head_with_a_review_of_ours(self):
        self.state["reviews"]["7"] = [{"id": 1, "user": {"login": JOB_LOGIN, "type": "Bot"}, "commit_id": HEAD, "body": marked("Two findings.")}]
        self.assertNothing(self.restart(), "#7 holds a review of ours on 2222222")

    def test_another_apps_check_or_a_check_on_another_head_is_not_ours(self):
        seed_check(self.state, "success", app="other-app"); seed_check(self.state, "success", head="3" * 40)
        seed_check(self.state, "success", name="lint")
        self.assertEqual(self.restart().state["reruns"], [480])

    def test_under_the_app_ours_are_the_apps(self):
        seed_check(self.state, "success")                                               # another workflow's, under the job's token
        ran = self.restart(IRONBEE_APP_SLUG=APP_SLUG)
        self.assertEqual(ran.state["reruns"], [480])
        self.seed(); self.state["checks"] = []
        self.state["reviews"]["7"] = [{"id": 1, "user": {"login": APP_LOGIN, "type": "Bot"}, "commit_id": HEAD, "body": marked("Two findings.")}]
        self.assertNothing(self.restart(IRONBEE_APP_SLUG=APP_SLUG), "holds a review of ours")

    def test_a_closed_pull_request(self):
        self.state["pulls"]["7"]["state"] = "closed"
        self.assertNothing(self.restart(), "#7 is closed")

    def test_a_forks_pull_request(self):
        self.state["pulls"]["7"]["head"]["repo"]["full_name"] = "someone/widgets"
        self.assertNothing(self.restart(), "#7 comes from a fork")

    def test_a_comment_on_an_issue_or_an_event_with_no_pull_request(self):
        self.assertNothing(self.restart(changed(event("issue_comment.created"), issue__number=8)), "#8 is no pull request")
        self.assertNothing(self.restart({"action": "created"}), "the event names no pull request")

    def test_no_review_cancelled(self):
        self.state["runs"] = [run(RUN, "issue_comment", status="in_progress", conclusion=None), run(480, conclusion="success")]
        self.assertNothing(self.restart(), "no review of 2222222 was cancelled")

    def test_a_run_that_holds_other_jobs(self):
        self.state["jobs"] = {"480": [{**OURS, "id": 1}, {"name": "build", "status": "completed", "conclusion": "success", "id": 2}]}
        ran = self.restart()
        self.assertNothing(ran, "run 480, the review of 2222222 a newer run replaced while it waited, holds 2 jobs")
        self.assertIn("`@ironbee-ai review`", ran.out)


class Refused(Restart):
    def test_without_actions_write_the_step_fails_naming_it(self):
        for path in (f"repos/acme/widgets/actions/runs/{RUN}", "repos/acme/widgets/actions/runs/480/rerun"):
            with self.subTest(path):
                self.seed()
                self.state["fail"] = [{"method": "POST" if path.endswith("rerun") else "GET", "path": path, "status": 403, "times": 1}]
                ran = self.restart()
                self.assertEqual(ran.code, 1, ran.out)
                self.assertIn("(HTTP 403: Server Error): the calling workflow file must grant the job actions: write to start a review again", ran.out)
                self.assertEqual(ran.state.get("reruns", []), [])

    def test_a_run_github_will_not_start_again_says_why_in_githubs_words(self):
        self.state["runs"][1]["status"] = "in_progress"; self.state["runs"][1]["conclusion"] = "cancelled"     # the stub refuses a run that runs
        ran = self.restart()
        self.assertEqual(ran.code, 1, ran.out)
        self.assertIn("GitHub refused to start run 480 again (HTTP 403: This workflow is already running)", ran.out)

    def test_a_read_that_keeps_failing_fails_the_step_and_starts_nothing(self):
        self.state["fail"] = [{"method": "GET", "path": "repos/acme/widgets/actions/workflows/", "status": 502, "times": 3}]
        ran = self.restart()
        self.assertEqual(ran.code, 1)
        self.assertEqual(ran.state.get("reruns", []), [])
        self.assertEqual(ran.sleeps, ["2", "5"])

    def test_the_configuration(self):
        self.assertEqual(self.restart(GITHUB_RUN_ID="").code, 2)
        self.assertEqual(self.restart(GITHUB_RUN_ID="x1").code, 2)
        self.assertEqual(self.run_script("restart.sh", {"GITHUB_RUN_ID": str(RUN), "GITHUB_EVENT_PATH": "/nonexistent"}).code, 2)


if __name__ == "__main__":
    unittest.main()
