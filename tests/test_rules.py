"""The rules of scripts/ironbee.jq that mirror the runner's: the mention and the retract word over the runner's own cases
(tests/fixtures/mention-cases.json), and our marker."""
from __future__ import annotations

import json
import subprocess
import unittest

from support import FIXTURES, SCRIPTS


def jq(filter_: str, data) -> object:
    p = subprocess.run(["jq", "-c", "-L", str(SCRIPTS), f'include "ironbee"; {filter_}'], input=json.dumps(data), capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


class Mention(unittest.TestCase):
    def test_the_runners_cases(self):
        cases = json.loads((FIXTURES / "mention-cases.json").read_text())["cases"]
        got = jq("map(. as $c | ([$c.mention] + (if $c.mentionAlias then [$c.mentionAlias] else [] end)) as $names"
                 " | {mentions: ($c.body | addressed($names)), retract: ($c.body | asks_retract($names))})", cases)
        self.assertEqual(len(got), len(cases))
        for case, out in zip(cases, got):
            with self.subTest(case["body"]):
                self.assertEqual(out, {"mentions": case["mentions"], "retract": case["retract"]})

    def test_a_name_with_characters_a_pattern_would_read(self):
        self.assertEqual(jq('map(addressed(["@a.b"]))', ["@a.b review", "@axb review"]), [True, False])


class Marker(unittest.TestCase):
    def test_a_hidden_marker_of_ours(self):
        bodies = {"Finding.\n\n<!-- ironbee f1 -->": True, "<!-- ironbee review:widgets__7 -->": True, "  <!-- ironbee f1 -->  ": True,
                  "> <!-- ironbee f1 -->": False, "   > quoted <!-- ironbee f1 -->": False, "<!-- ironbee -->": False,
                  "<!-- ironbee-summary start -->": False, "no marker": False, "": False, "a\r\n> b\r\n<!-- ironbee f2 -->": True}
        got = jq("map(has_marker)", list(bodies))
        self.assertEqual(dict(zip(bodies, got)), bodies)


if __name__ == "__main__":
    unittest.main()
