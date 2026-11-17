"""The decide step (scripts/decide.sh): one test per event kind and per filter, over the recorded events."""
from __future__ import annotations

import unittest

from support import APP_SLUG, GROUP_HEAD, HEAD, JOB_LOGIN, JOB_TOKEN, SERVER, ScriptTest, changed, event, github, marked, on_host

NOTHING: dict = {}


class Decide(ScriptTest):
    def decide(self, name: str, payload: dict, **env):
        e = {"IRONBEE_HAS_API_KEY": "true", "IRONBEE_HAS_REGISTRY_TOKEN": "true", "IRONBEE_HAS_APP_ID": "false", "IRONBEE_HAS_APP_PRIVATE_KEY": "false",
             "IRONBEE_APP_SLUG": ""}
        e.update(env)
        return self.run_script("decide.sh", e, (name, payload))

    def under_app(self, **env) -> dict:
        return {"IRONBEE_APP_SLUG": APP_SLUG, "IRONBEE_HAS_APP_ID": "true", "IRONBEE_HAS_APP_PRIVATE_KEY": "true", **env}

    def assertEnds(self, ran, calls: int = 0) -> None:
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual(ran.outputs, NOTHING)
        self.assertIn("nothing to do", ran.out)
        self.assertEqual(len(ran.calls), calls, ran.calls)
        self.assertEqual(ran.writes(), [])


class PullRequest(Decide):
    def test_each_change_that_reviews_is_a_review_of_the_events_head(self):
        for change in ("opened", "synchronize", "reopened", "ready_for_review"):
            with self.subTest(change):
                ran = self.decide("pull_request", event(f"pull_request.{change}"))
                self.assertEqual(ran.code, 0, ran.err)
                self.assertEqual(ran.outputs, {"action": "review", "pull-request": "7", "head": HEAD})
                self.assertEqual(ran.calls, [])                 # decided from the event alone

    def test_any_other_change_ends(self):
        for change in ("closed", "edited", "labeled", "converted_to_draft"):
            with self.subTest(change):
                self.assertEnds(self.decide("pull_request", changed(event("pull_request.opened"), action=change)))

    def test_a_forks_pull_request_ends_and_writes_nothing(self):
        fork = changed(event("pull_request.opened"), pull_request__head__repo__full_name="someone/widgets")
        self.assertEnds(self.decide("pull_request", fork))
        gone = changed(event("pull_request.opened"), pull_request__head__repo=None)    # a fork deleted since
        self.assertEnds(self.decide("pull_request", gone))
        self.assertEnds(self.decide("pull_request", fork, IRONBEE_HAS_API_KEY="false"))   # no neutral there either

    def test_a_bots_own_pull_request_goes_on_to_the_bot_gate(self):
        bot = {"login": "dependabot[bot]", "id": 49699333, "type": "Bot"}
        ran = self.decide("pull_request", changed(event("pull_request.opened"), sender=bot, pull_request__user=bot))
        self.assertEqual(ran.outputs["action"], "review")

    def test_a_run_without_secrets_asks_a_neutral_under_the_job_token(self):
        ran = self.decide("pull_request", event("pull_request.synchronize"), IRONBEE_HAS_API_KEY="false")
        self.assertEqual(ran.code, 0, ran.err)
        self.assertEqual(ran.outputs, {"write": "no_secrets", "write-head": HEAD, "write-pull-request": "7"})
        self.assertEqual(ran.calls, [])

    def test_a_run_without_the_registry_token_has_no_secrets_either(self):
        ran = self.decide("pull_request", event("pull_request.opened"), IRONBEE_HAS_REGISTRY_TOKEN="false")
        self.assertEqual(ran.outputs, {"write": "no_secrets", "write-head": HEAD, "write-pull-request": "7"})
        ran = self.decide("pull_request", event("pull_request.opened"), IRONBEE_HAS_API_KEY="false", IRONBEE_HAS_REGISTRY_TOKEN="false")
        self.assertEqual(ran.outputs["write"], "no_secrets")

    def test_a_run_without_secrets_writes_nothing_under_the_app_without_its_key(self):
        ran = self.decide("pull_request", event("pull_request.opened"), **self.under_app(IRONBEE_HAS_API_KEY="false", IRONBEE_HAS_REGISTRY_TOKEN="false",
                                                                                         IRONBEE_HAS_APP_ID="false", IRONBEE_HAS_APP_PRIVATE_KEY="false"))
        self.assertEnds(ran)

    def test_a_run_without_secrets_given_the_apps_key_asks_a_neutral_under_the_app(self):
        # A Dependabot pull request whose secrets hold the App's id and key, and no API key.
        ran = self.decide("pull_request", event("pull_request.opened"), **self.under_app(IRONBEE_HAS_API_KEY="false", IRONBEE_HAS_REGISTRY_TOKEN="false"))
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual(ran.outputs, {"write": "no_secrets", "write-head": HEAD, "write-pull-request": "7"})
        self.assertEqual(ran.calls, [])


class ReviewComment(Decide):
    def setUp(self) -> None:
        super().setUp()
        self.reply = event("pull_request_review_comment.created")                     # comment 5202, a reply to 5201
        self.state["comments"]["5201"] = {"id": 5201, "user": {"login": JOB_LOGIN, "type": "Bot"}, "body": marked("**Negative radius** is not rejected.")}

    def test_a_reply_on_our_thread_from_someone_who_counts_is_answered(self):
        ran = self.decide("pull_request_review_comment", self.reply)
        self.assertEqual(ran.code, 0, ran.err)
        self.assertEqual(ran.outputs, {"action": "answer", "pull-request": "7", "comment-id": "5202"})
        self.assertEqual([(c["method"], c["path"], c["token"]) for c in ran.calls], [("GET", "repos/acme/widgets/pulls/comments/5201", JOB_TOKEN)])

    def test_a_bots_comment_ends(self):
        bot = {"login": "renovate[bot]", "id": 1, "type": "Bot"}
        self.assertEnds(self.decide("pull_request_review_comment", changed(self.reply, comment__user=bot, sender=bot)))

    def test_our_own_comment_ends(self):
        us = {"login": JOB_LOGIN, "id": 41898282, "type": "Bot"}
        self.assertEnds(self.decide("pull_request_review_comment", changed(self.reply, comment__user=us, sender=us)))

    def test_a_threads_first_comment_ends(self):
        self.assertEnds(self.decide("pull_request_review_comment", changed(self.reply, comment__in_reply_to_id=None)))

    def test_a_thread_that_is_not_ours_ends(self):
        roots = {"someone else's, with our marker": {"user": {"login": "bob", "type": "User"}, "body": marked("mine")},
                 "ours without a marker": {"user": {"login": JOB_LOGIN, "type": "Bot"}, "body": "a workflow's comment"},
                 "ours, the marker only quoted": {"user": {"login": JOB_LOGIN, "type": "Bot"}, "body": "> earlier\n> <!-- ironbee f1 -->\nhello"}}
        for what, root in roots.items():
            with self.subTest(what):
                self.state["comments"]["5201"] = {"id": 5201, **root}
                self.assertEnds(self.decide("pull_request_review_comment", self.reply), calls=1)

    def test_a_first_comment_gone_ends(self):
        del self.state["comments"]["5201"]
        self.assertEnds(self.decide("pull_request_review_comment", self.reply), calls=1)

    def test_a_reply_from_someone_who_does_not_count_ends_before_any_read(self):
        for association in ("CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "NONE"):
            with self.subTest(association):
                passer = changed(self.reply, comment__author_association=association, comment__user__login="passer", sender__login="passer")
                self.assertEnds(self.decide("pull_request_review_comment", passer))

    def test_the_pull_requests_author_counts_whatever_the_association(self):
        author = changed(self.reply, comment__author_association="NONE")              # bob opened #7
        self.assertEqual(self.decide("pull_request_review_comment", author).outputs["action"], "answer")
        for association in ("OWNER", "COLLABORATOR"):
            with self.subTest(association):
                other = changed(self.reply, comment__author_association=association, comment__user__login="carol")
                self.assertEqual(self.decide("pull_request_review_comment", other).outputs["action"], "answer")

    def test_a_reply_on_a_forks_pull_request_ends(self):
        self.assertEnds(self.decide("pull_request_review_comment", changed(self.reply, pull_request__head__repo__full_name="someone/widgets")))

    def test_a_run_without_secrets_ends(self):
        self.assertEnds(self.decide("pull_request_review_comment", self.reply, IRONBEE_HAS_API_KEY="false"))

    def test_an_edit_ends(self):
        self.assertEnds(self.decide("pull_request_review_comment", changed(self.reply, action="edited")))

    def test_a_slug_in_another_case_still_finds_our_thread(self):
        self.state["comments"]["5201"]["user"] = {"login": f"{APP_SLUG}[bot]", "type": "Bot"}
        ran = self.decide("pull_request_review_comment", self.reply, **self.under_app(IRONBEE_APP_SLUG="Acme-Reviewer"))
        self.assertEqual(ran.outputs.get("action"), "answer", ran.out + ran.err)

    def test_under_the_app_our_thread_is_the_apps(self):
        self.state["comments"]["5201"]["user"] = {"login": f"{APP_SLUG}[bot]", "type": "Bot"}
        self.assertEqual(self.decide("pull_request_review_comment", self.reply, **self.under_app()).outputs["action"], "answer")
        self.state["comments"]["5201"]["user"] = {"login": JOB_LOGIN, "type": "Bot"}           # another workflow's, under the App
        self.assertEnds(self.decide("pull_request_review_comment", self.reply, **self.under_app()), calls=1)


class IssueComment(Decide):
    def setUp(self) -> None:
        super().setUp()
        self.comment = event("issue_comment.created")                                   # alice: "@ironbee-ai full review"

    def says(self, body: str, **paths) -> dict:
        return changed(self.comment, comment__body=body, **paths)

    def test_a_command_from_a_writer_is_a_respond(self):
        ran = self.decide("issue_comment", self.comment)
        self.assertEqual(ran.code, 0, ran.err)
        self.assertEqual(ran.outputs, {"action": "respond", "pull-request": "7", "comment-id": "3101"})
        self.assertEqual([(c["method"], c["path"]) for c in ran.calls],
                         [("GET", "repos/acme/widgets/pulls/7"), ("GET", "repos/acme/widgets/collaborators/alice/permission")])
        self.assertTrue(all(c["token"] == JOB_TOKEN for c in ran.calls))

    def test_a_question_is_a_respond(self):
        self.assertEqual(self.decide("issue_comment", self.says("@ironbee-ai why is the radius checked twice?")).outputs["action"], "respond")

    def test_the_retract_word_after_the_mention_is_a_retract(self):
        self.assertEqual(self.decide("issue_comment", self.says("Fixed both. @IronBee-AI, please retract!")).outputs["action"], "retract")
        self.assertEqual(self.decide("issue_comment", self.says("retract @ironbee-ai")).outputs["action"], "respond")

    def test_each_permission_that_pushes_may_command(self):
        for login in ("alice", "bob", "carol"):
            with self.subTest(login):
                ran = self.decide("issue_comment", self.says("@ironbee-ai review", comment__user__login=login, sender__login=login))
                self.assertEqual(ran.outputs["action"], "respond")

    def test_a_comment_not_addressed_to_us_ends_before_any_read(self):
        for body in ("LGTM", "@ironbee-ai-staging review", "@github-actions review", "me@ironbee-ai review", ""):
            with self.subTest(body):
                self.assertEnds(self.decide("issue_comment", self.says(body)))

    def test_an_enterprise_managed_users_command_is_obeyed(self):
        self.state["permissions"]["octocat_acme"] = "write"
        ran = self.decide("issue_comment", self.says("@ironbee-ai review", comment__user__login="octocat_acme", sender__login="octocat_acme"))
        self.assertEqual(ran.outputs["action"], "respond", ran.out + ran.err)
        self.assertEqual(ran.calls[-1]["path"], "repos/acme/widgets/collaborators/octocat_acme/permission")

    def test_a_login_no_account_can_have_ends_before_its_permission_is_asked(self):
        for login in ("a/b", "a.b", "a b", "..", "a%2Fb", "a?b", "ä"):
            with self.subTest(login):
                self.assertEnds(self.decide("issue_comment", self.says("@ironbee-ai review", comment__user__login=login)), calls=1)

    def test_a_command_from_someone_who_may_not_write_ends(self):
        self.assertEnds(self.decide("issue_comment", self.says("@ironbee-ai review", comment__user__login="reader")), calls=2)
        self.assertEnds(self.decide("issue_comment", self.says("@ironbee-ai review", comment__user__login="stranger")), calls=2)   # GitHub: 404

    def test_a_comment_on_a_forks_pull_request_ends(self):
        self.state["pulls"]["7"]["head"]["repo"]["full_name"] = "someone/widgets"
        self.assertEnds(self.decide("issue_comment", self.comment), calls=1)

    def test_a_comment_on_an_issue_ends(self):
        self.assertEnds(self.decide("issue_comment", changed(self.comment, issue__pull_request=None)))

    def test_an_edit_ends(self):
        self.assertEnds(self.decide("issue_comment", changed(self.comment, action="edited")))

    def test_a_bots_comment_ends(self):
        bot = {"login": "dependabot[bot]", "id": 49699333, "type": "Bot"}
        self.assertEnds(self.decide("issue_comment", changed(self.comment, comment__user=bot, sender=bot)))

    def test_a_run_without_secrets_ends(self):
        self.assertEnds(self.decide("issue_comment", self.comment, IRONBEE_HAS_API_KEY="false"))
        self.assertEnds(self.decide("issue_comment", self.comment, IRONBEE_HAS_REGISTRY_TOKEN="false"))

    def test_under_the_app_the_slug_is_the_only_name(self):
        ran = self.decide("issue_comment", self.says(f"@{APP_SLUG} review"), **self.under_app())
        self.assertEqual(ran.outputs["action"], "respond")
        self.assertEqual(self.decide("issue_comment", self.says(f"@{APP_SLUG} retract"), **self.under_app()).outputs["action"], "retract")
        self.assertEnds(self.decide("issue_comment", self.says("@ironbee-ai review"), **self.under_app()))

    def test_a_read_that_fails_for_a_moment_is_asked_again(self):
        self.state["fail"] = [{"method": "GET", "path": "repos/acme/widgets/collaborators/", "status": 502, "times": 2}]
        ran = self.decide("issue_comment", self.comment)
        self.assertEqual(ran.outputs["action"], "respond", ran.out + ran.err)
        self.assertEqual(ran.sleeps, ["2", "5"])

    def test_a_read_that_keeps_failing_fails_the_job(self):
        for status in (503, 0):
            with self.subTest(status):
                self.state["fail"] = [{"method": "GET", "path": "repos/acme/widgets/collaborators/", "status": status, "times": 3}]
                ran = self.decide("issue_comment", self.comment)
                self.assertEqual(ran.code, 1)
                self.assertEqual(ran.outputs, NOTHING)
                self.assertIn("::error::", ran.out)

    def test_on_a_server_the_reads_name_its_host(self):
        self.state = github(SERVER)
        ran = self.decide("issue_comment", self.comment, **on_host(SERVER))
        self.assertEqual(ran.outputs, {"action": "respond", "pull-request": "7", "comment-id": "3101"}, ran.out + ran.err)
        self.assertEqual({(c["host"], c["token"]) for c in ran.calls}, {(SERVER, JOB_TOKEN)})

    def test_a_refused_read_is_not_asked_again(self):
        self.state["fail"] = [{"method": "GET", "path": "repos/acme/widgets/pulls/7", "status": 403, "times": 1}]
        ran = self.decide("issue_comment", self.comment)
        self.assertEqual(ran.code, 1)
        self.assertEqual(len(ran.calls), 1)


class MergeGroupAndOthers(Decide):
    def test_a_merge_group_asks_a_neutral_on_its_commit(self):
        ran = self.decide("merge_group", event("merge_group.checks_requested"))
        self.assertEqual(ran.code, 0, ran.err)
        self.assertEqual(ran.outputs, {"write": "merge_group", "write-head": GROUP_HEAD})
        self.assertEqual(ran.calls, [])

    def test_a_merge_group_under_the_app(self):
        self.assertEqual(self.decide("merge_group", event("merge_group.checks_requested"), **self.under_app()).outputs["write"], "merge_group")
        no_key = self.under_app(IRONBEE_HAS_API_KEY="false", IRONBEE_HAS_REGISTRY_TOKEN="false", IRONBEE_HAS_APP_ID="false", IRONBEE_HAS_APP_PRIVATE_KEY="false")
        self.assertEnds(self.decide("merge_group", event("merge_group.checks_requested"), **no_key))

    def test_the_registering_events_end(self):
        self.assertEnds(self.decide("push", event("push")))
        self.assertEnds(self.decide("workflow_dispatch", event("workflow_dispatch")))


class Configuration(Decide):
    def test_the_apps_key_without_its_slug(self):
        ran = self.decide("pull_request", event("pull_request.opened"), IRONBEE_HAS_APP_ID="true", IRONBEE_HAS_APP_PRIVATE_KEY="true")
        self.assertEqual(ran.code, 2)
        self.assertIn("::error::", ran.out)
        self.assertEqual(ran.outputs, NOTHING)

    def test_the_slug_without_the_apps_key_where_the_secrets_are(self):
        ran = self.decide("pull_request", event("pull_request.opened"), IRONBEE_APP_SLUG=APP_SLUG)
        self.assertEqual(ran.code, 2)

    def test_no_event_file(self):
        ran = self.run_script("decide.sh", {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": "/nonexistent/event.json"})
        self.assertEqual(ran.code, 2)


if __name__ == "__main__":
    unittest.main()
