"""What scripts/lib.sh gives every script and no single script's test reaches: the error annotation of `fail`, escaped
as GitHub reads a workflow command, so that no text can start a command line of its own."""
from __future__ import annotations

import subprocess
import unittest

from support import SCRIPTS


def fail(text: str, code: str = "2") -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", '. "$1"; fail "$2" "$3"', "_", str(SCRIPTS / "lib.sh"), code, text], capture_output=True, text=True)


class Fail(unittest.TestCase):
    def test_percent_cr_and_lf_are_escaped(self):
        p = fail("100% sure\r\n::warning::injected\nand\rmore")
        self.assertEqual(p.returncode, 2)
        self.assertEqual(p.stdout, "::error::100%25 sure%0D%0A::warning::injected%0Aand%0Dmore\n")

    def test_a_text_with_nothing_to_escape_is_as_it_was(self):
        p = fail("GitHub refused the check on 2222222 (HTTP 403)", "1")
        self.assertEqual((p.returncode, p.stdout), (1, "::error::GitHub refused the check on 2222222 (HTTP 403)\n"))


class CommandText(unittest.TestCase):
    def test_percent_cr_and_lf_are_escaped(self):
        ran = subprocess.run(["bash", "-c", f'. "{SCRIPTS}/lib.sh"; command_text "$1"', "_", "50% done\r\n::add-mask::x\nend"],
                             capture_output=True, text=True)
        self.assertEqual(ran.stdout, "50%25 done%0D%0A::add-mask::x%0Aend")


if __name__ == "__main__":
    unittest.main()
