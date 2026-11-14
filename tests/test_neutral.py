"""The neutral check of the decide step and the fallback (scripts/neutral.sh): the check's rule (no check and no review of ours on the commit),
and the second look that turns the neutral into a copy of a review's conclusion found beside it."""
from __future__ import annotations

import unittest

from support import APP_LOGIN, APP_SLUG, APP_TOKEN, CHECK, CHECK_PRE, GROUP_HEAD, HEAD, JOB_LOGIN, JOB_TOKEN, ScriptTest, check, marked, seed_check

LISTED = [f"repos/acme/widgets/commits/{HEAD}/check-runs?check_name=Code%20Review%20Result&filter=all&per_page=100",
          f"repos/acme/widgets/commits/{HEAD}/check-runs?check_name=IronBee%20review&filter=all&per_page=100"]   # one listing a name


class Neutral(ScriptTest):
    def neutral(self, reason: str = "not_run", pr: str = "7", head: str = HEAD, **env):
        e = {"IRONBEE_REASON": reason, "IRONBEE_HEAD": head, "IRONBEE_PULL_REQUEST": pr, "IRONBEE_APP_SLUG": "", "IRONBEE_APP_TOKEN": ""}
        e.update(env)
        return self.run_script("neutral.sh", e)

    def ours(self, ran, head: str = HEAD, app: str = "github-actions") -> list:
        return [c for c in ran.state["checks"] if c["head_sha"] == head and c["app"]["slug"] == app]

    def review(self, login: str = JOB_LOGIN, head: str = HEAD, body: str | None = None) -> dict:
        return {"id": 4401, "user": {"login": login, "type": "Bot"}, "commit_id": head, "state": "COMMENTED", "body": marked("Two findings.", "review:widgets__7") if body is None else body}


class TheRule(Neutral):
    def test_a_head_with_nothing_of_ours_gets_the_neutral(self):
        ran = self.neutral()
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        [c] = self.ours(ran)
        self.assertEqual((c["name"], c["status"], c["conclusion"], c["output"]["title"]), (CHECK, "completed", "neutral", "Not reviewed"))
        self.assertNotIn("details_url", c)                                              # a neutral links nowhere
        self.assertIn("The review did not run", c["output"]["summary"])
        self.assertIn("`@ironbee-ai review`", c["output"]["summary"])
        self.assertEqual([(w["method"], w["path"], w["token"]) for w in ran.writes()], [("POST", "repos/acme/widgets/check-runs", JOB_TOKEN)])
        reads = [(c["method"], c["path"]) for c in ran.calls if c["method"] == "GET"]
        self.assertEqual(reads, [*(("GET", path) for path in LISTED), ("GET", "repos/acme/widgets/pulls/7/reviews?per_page=100"), *(("GET", path) for path in LISTED)])

    def test_a_check_of_ours_is_left_as_it_is(self):
        for conclusion in ("action_required", "failure", "success", "neutral"):          # failure: a released pre-release's blocking one
            with self.subTest(conclusion):
                self.state["checks"] = []
                seed_check(self.state, conclusion)
                ran = self.neutral()
                self.assertEqual(ran.code, 0, ran.err)
                self.assertEqual(ran.writes(), [])
                self.assertIn("left as it is", ran.out)

    def test_a_check_of_ours_under_the_pre_releases_name_is_left_as_it_is(self):
        for conclusion in ("action_required", "failure", "neutral"):
            with self.subTest(conclusion):
                self.state["checks"] = []
                seed_check(self.state, conclusion, name=CHECK_PRE)
                ran = self.neutral()
                self.assertEqual(ran.code, 0, ran.err)
                self.assertEqual(ran.writes(), [])
                self.assertIn("left as it is", ran.out)

    def test_a_check_of_ours_under_another_name_is_not_the_check(self):
        seed_check(self.state, "failure", name="lint")
        self.assertEqual([c["conclusion"] for c in self.ours(self.neutral()) if c["name"] == CHECK], ["neutral"])

    def test_another_apps_check_of_that_name_is_not_ours(self):
        seed_check(self.state, "failure", app="other-app")
        seed_check(self.state, "failure", app="other-app", name=CHECK_PRE)
        ran = self.neutral()
        self.assertEqual([c["conclusion"] for c in self.ours(ran)], ["neutral"])

    def test_our_check_on_another_commit_does_not_count(self):
        seed_check(self.state, "failure", head="3" * 40)
        self.assertEqual([c["conclusion"] for c in self.ours(self.neutral())], ["neutral"])

    def test_a_review_of_ours_on_the_head_is_left_as_it_is(self):
        self.state["reviews"]["7"] = [self.review()]
        ran = self.neutral()
        self.assertEqual(ran.code, 0, ran.err)
        self.assertEqual(ran.writes(), [])
        self.assertIn("holds a review of ours", ran.out)

    def test_a_heads_short_review_of_ours_is_left_as_it_is(self):
        """The short review the runner posts on a head whose round posted none, before it writes a blocking conclusion there: ours on
        that head, so a run killed before its check leaves no neutral, with or without its `concluding` output."""
        body = marked(f"## IronBee Code Review\n\nNo new change was read on `{HEAD[:7]}`: **2 findings** stay open.", "held:widgets__7")
        self.state["reviews"]["7"] = [self.review(body=body)]
        ran = self.neutral()
        self.assertEqual(ran.code, 0, ran.err)
        self.assertEqual(ran.writes(), [])
        self.assertIn("holds a review of ours", ran.out)

    def test_reviews_that_are_not_ours_on_the_head_do_not_count(self):
        others = {"on another head": self.review(head="3" * 40), "without our marker": self.review(body="Looks good."),
                  "someone else's": self.review(login="bob"), "our marker only quoted": self.review(body="> <!-- ironbee review:widgets__7 -->\nagreed")}
        for what, review in others.items():
            with self.subTest(what):
                self.state["checks"] = []; self.state["reviews"]["7"] = [review]
                self.assertEqual([c["conclusion"] for c in self.ours(self.neutral())], ["neutral"])

    def test_a_refused_write_fails_the_job(self):
        self.state["fail"] = [{"method": "POST", "path": "repos/acme/widgets/check-runs", "status": 403, "times": 1}]
        ran = self.neutral()
        self.assertEqual(ran.code, 1)
        self.assertIn("::error::GitHub refused the check", ran.out)

    def test_a_create_that_made_nothing_is_sent_again_after_a_look(self):
        for status in (502, 0):
            with self.subTest(status):
                self.state["checks"] = []
                self.state["fail"] = [{"method": "POST", "path": "repos/acme/widgets/check-runs", "status": status, "times": 1}]
                ran = self.neutral()
                self.assertEqual(ran.code, 0, ran.out + ran.err)
                self.assertEqual([c["conclusion"] for c in self.ours(ran)], ["neutral"])
                self.assertEqual([c["method"] for c in ran.calls], ["GET", "GET", "GET", "POST", "GET", "GET", "POST", "GET", "GET"])
                self.assertEqual(ran.sleeps, ["2"])

    def test_a_create_that_made_the_check_is_not_sent_again(self):
        self.state["fail"] = [{"method": "POST", "path": "repos/acme/widgets/check-runs", "status": 502, "times": 1, "made": True}]
        ran = self.neutral()
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual([c["conclusion"] for c in self.ours(ran)], ["neutral"])
        self.assertEqual([w["method"] for w in ran.writes()], ["POST"])
        self.assertIn("a check of ours is there now: taken as written", ran.out)
        self.assertEqual(ran.sleeps, [])

    def test_a_reviews_conclusion_found_after_a_failed_create_stays(self):
        self.state["fail"] = [{"method": "POST", "path": "repos/acme/widgets/check-runs", "status": 503, "times": 1, "made": True}]
        self.state["on_create"] = {"rewrite": {"conclusion": "action_required", "output": {"title": "1 blocking", "summary": "s"}}}
        ran = self.neutral()
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual([c["conclusion"] for c in self.ours(ran)], ["action_required"])
        self.assertEqual([w["method"] for w in ran.writes()], ["POST"])
        self.assertIn("already says action_required", ran.out)

    def test_a_create_never_answered_and_never_made_fails_after_three(self):
        self.state["fail"] = [{"method": "POST", "path": "repos/acme/widgets/check-runs", "status": 0, "times": 3}]
        ran = self.neutral()
        self.assertEqual(ran.code, 1)
        self.assertIn("::error::GitHub did not make the check on 2222222 (HTTP 000)", ran.out)
        self.assertEqual([w["method"] for w in ran.writes()], ["POST"] * 3)
        self.assertEqual(ran.sleeps, ["2", "5"])
        self.assertEqual(self.ours(ran), [])

    def test_a_429_create_is_sent_again(self):
        self.state["fail"] = [{"method": "POST", "path": "repos/acme/widgets/check-runs", "status": 429, "times": 1}]
        ran = self.neutral()
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual([c["conclusion"] for c in self.ours(ran)], ["neutral"])
        self.assertEqual([c["method"] for c in ran.calls], ["GET", "GET", "GET", "POST", "POST", "GET", "GET"])     # no look between: a 429 made nothing
        self.assertEqual(ran.sleeps, ["2"])

    def test_a_create_still_refused_with_429_is_tried_again_after_a_look(self):
        self.state["fail"] = [{"method": "POST", "path": "repos/acme/widgets/check-runs", "status": 429, "times": 3}]
        ran = self.neutral()
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual([c["conclusion"] for c in self.ours(ran)], ["neutral"])
        methods = [c["method"] for c in ran.calls]
        self.assertEqual(methods.count("POST"), 4)
        self.assertEqual(methods[methods.index("POST") + 3], "GET")                                 # ours listed again before the fourth create

    def test_a_listing_that_fails_writes_nothing(self):
        self.state["fail"] = [{"method": "GET", "path": "repos/acme/widgets/commits/", "status": 500, "times": 3}]
        ran = self.neutral()
        self.assertEqual(ran.code, 1)
        self.assertEqual(ran.writes(), [])


class TheReviewConcluding(Neutral):
    """The fallback after a review step that said it began to conclude on a head (its `concluding` output) and then stopped."""

    def test_the_head_it_was_concluding_on_gets_nothing(self):
        ran = self.neutral(IRONBEE_CONCLUDING=HEAD)                                   # no check, no review of ours: still nothing
        self.assertEqual(ran.code, 0, ran.err)
        self.assertEqual(ran.calls, [])
        self.assertEqual(ran.state["checks"], [])
        self.assertIn("began to conclude", ran.out)

    def test_no_output_from_a_killed_job_writes_as_before(self):
        for concluding in ("", None):
            with self.subTest(concluding):
                self.state["checks"] = []
                ran = self.neutral(IRONBEE_CONCLUDING=concluding)
                self.assertEqual([c["conclusion"] for c in self.ours(ran)], ["neutral"])

    def test_another_head_concluded_does_not_count(self):
        ran = self.neutral(IRONBEE_CONCLUDING="3" * 40)
        self.assertEqual([c["conclusion"] for c in self.ours(ran)], ["neutral"])


class TheSecondLook(Neutral):
    def test_a_reviews_conclusion_written_just_before_ours_is_copied_onto_ours(self):
        self.state["on_create"] = {"before": [check("action_required", title="1 blocking · 3 open", summary="Concluded at `2222222` from this pull request's findings.")]}
        ran = self.neutral()
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        review, own = self.ours(ran)
        self.assertEqual(own["conclusion"], "action_required")
        self.assertEqual(own["output"], {"title": "1 blocking · 3 open", "summary": "Concluded at `2222222` from this pull request's findings."})
        self.assertEqual(review["conclusion"], "action_required")
        self.assertEqual([(w["method"], w["path"]) for w in ran.writes()], [("POST", "repos/acme/widgets/check-runs"), ("PATCH", f"repos/acme/widgets/check-runs/{own['id']}")])
        self.assertIn("copied", ran.out)

    def test_a_reviews_conclusion_written_just_after_ours_is_copied_too(self):
        self.state["on_create"] = {"after": [check("success", title="Nothing open", summary="s")]}
        ran = self.neutral()
        self.assertEqual([c["conclusion"] for c in self.ours(ran)], ["success", "success"])

    def test_the_newest_of_several_conclusions_is_copied(self):
        self.state["on_create"] = {"before": [check("success", title="old"), check("action_required", title="new")]}
        ran = self.neutral()
        self.assertEqual([(c["conclusion"], c["output"]["title"]) for c in self.ours(ran)][-1], ("action_required", "new"))

    def test_a_neutral_already_rewritten_by_the_review_is_left(self):
        self.state["on_create"] = {"rewrite": {"conclusion": "action_required", "output": {"title": "1 blocking", "summary": "s"}}}
        ran = self.neutral()
        self.assertEqual(ran.code, 0, ran.err)
        self.assertEqual([w["method"] for w in ran.writes()], ["POST"])
        self.assertIn("a review rewrote it", ran.out)

    def test_a_released_pre_releases_failure_is_a_reviews_conclusion_too(self):
        """Released pre-releases wrote failure where a review now writes action_required: it is copied as action_required,
        since nothing of this release writes failure, and it ends the look."""
        self.state["on_create"] = {"before": [check("failure", title="1 blocking")]}
        ran = self.neutral()
        self.assertEqual([(c["conclusion"], c["output"]["title"]) for c in self.ours(ran)], [("failure", "1 blocking"), ("action_required", "1 blocking")])
        self.assertIn("a review's conclusion of ours (action_required) was beside it", ran.out)
        self.state["on_create"] = {"rewrite": {"conclusion": "failure", "output": {"title": "1 blocking", "summary": "s"}}}
        ran = self.neutral()
        self.assertEqual([w["method"] for w in ran.writes()], ["POST"])
        self.assertIn("already says failure: a review rewrote it", ran.out)

    def test_a_conclusion_under_the_pre_releases_name_is_ours_too(self):
        """A pre-release's check is ours: its conclusion is copied onto ours, which keeps the check's own name; an empty
        title or summary is copied as the check's name."""
        self.state["on_create"] = {"before": [check("action_required", name=CHECK_PRE, title="", summary="")]}
        ran = self.neutral()
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual([(c["name"], c["conclusion"], c["output"]["title"]) for c in self.ours(ran)], [(CHECK_PRE, "action_required", ""), (CHECK, "action_required", CHECK)])
        self.assertIn("copied", ran.out)

    def test_a_neutral_beside_it_is_no_conclusion(self):
        self.state["on_create"] = {"before": [check("neutral", title="Retracted")]}
        ran = self.neutral()
        self.assertEqual([w["method"] for w in ran.writes()], ["POST"])

    def test_another_apps_conclusion_beside_it_is_not_copied(self):
        self.state["on_create"] = {"before": [check("success", app="other-app")]}
        ran = self.neutral()
        self.assertEqual([c["conclusion"] for c in self.ours(ran)], ["neutral"])


class Reasons(Neutral):
    def test_a_merge_queues_group_reads_no_reviews(self):
        ran = self.neutral("merge_group", pr="", head=GROUP_HEAD)
        self.assertEqual(ran.code, 0, ran.err)
        [c] = self.ours(ran, head=GROUP_HEAD)
        self.assertEqual((c["conclusion"], c["output"]["title"]), ("neutral", "Reviewed on its pull requests"))
        self.assertFalse(any("/reviews" in c["path"] for c in ran.calls))

    def test_a_run_without_secrets(self):
        [c] = self.ours(self.neutral("no_secrets"))
        self.assertEqual(c["output"]["title"], "Not reviewed")
        self.assertIn("Dependabot", c["output"]["summary"])

    def test_an_unknown_reason_or_head_is_a_configuration_error(self):
        self.assertEqual(self.neutral("whatever").code, 2)
        self.assertEqual(self.neutral(head="not-a-commit").code, 2)
        self.assertEqual(self.neutral(pr="7; rm -rf /").code, 2)


class UnderTheApp(Neutral):
    def app(self, **env) -> dict:
        return {"IRONBEE_APP_SLUG": APP_SLUG, "IRONBEE_APP_TOKEN": APP_TOKEN, **env}

    def test_the_app_writes_and_the_job_token_reads(self):
        ran = self.neutral(**self.app())
        self.assertEqual(ran.code, 0, ran.err)
        [c] = self.ours(ran, app=APP_SLUG)
        self.assertIn(f"`@{APP_SLUG} review`", c["output"]["summary"])
        self.assertEqual({w["token"] for w in ran.writes()}, {APP_TOKEN})
        self.assertEqual({r["token"] for r in ran.calls if r["method"] == "GET"}, {JOB_TOKEN})

    def test_a_slug_in_another_case_still_finds_our_review(self):
        self.state["reviews"]["7"] = [self.review(login=APP_LOGIN)]
        ran = self.neutral(**self.app(IRONBEE_APP_SLUG="Acme-Reviewer"))
        self.assertEqual(ran.code, 0, ran.out + ran.err)
        self.assertEqual(ran.writes(), [])
        self.assertIn("holds a review of ours", ran.out)

    def test_ours_is_the_apps(self):
        seed_check(self.state, "failure", app="github-actions")                       # another workflow's, under the App
        self.state["reviews"]["7"] = [self.review(login=JOB_LOGIN)]
        ran = self.neutral(**self.app())
        self.assertEqual([c["conclusion"] for c in self.ours(ran, app=APP_SLUG)], ["neutral"])
        self.state["checks"] = []; self.state["reviews"]["7"] = [self.review(login=APP_LOGIN)]
        self.assertEqual(self.neutral(**self.app()).writes(), [])

    def test_the_second_look_copies_the_apps_conclusion(self):
        self.state["on_create"] = {"before": [check("action_required", app=APP_SLUG, title="2 blocking")]}
        ran = self.neutral(**self.app())
        self.assertEqual([c["conclusion"] for c in self.ours(ran, app=APP_SLUG)], ["action_required", "action_required"])
        self.assertEqual({w["token"] for w in ran.writes()}, {APP_TOKEN})

    def test_no_token_from_the_app_is_a_configuration_error(self):
        ran = self.neutral(**self.app(IRONBEE_APP_TOKEN=""))
        self.assertEqual(ran.code, 2)
        self.assertEqual(ran.calls, [])


if __name__ == "__main__":
    unittest.main()
