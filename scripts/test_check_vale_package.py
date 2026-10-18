"""Keep the consumer smoke test strict about exit codes, rules, and severity."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_vale_package import RULES, check_package  # noqa: E402


class ValeConsumerCheckTests(unittest.TestCase):
    def run_check(self, *, probe_code=1, clean_code=0, checks=RULES, severity="error"):
        alerts = [
            {"Check": rule, "Severity": severity, "Line": 3, "Span": [1, 6], "Message": rule}
            for rule in sorted(checks)
        ]
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            vale, package = work / "vale", work / "Crefft.zip"
            vale.touch()
            package.touch()
            with patch("check_vale_package.subprocess.run") as run:
                run.side_effect = [
                    subprocess.CompletedProcess([], 0),
                    subprocess.CompletedProcess([], probe_code, json.dumps({"probe.md": alerts}), ""),
                    subprocess.CompletedProcess([], clean_code, "{}", ""),
                ]
                with contextlib.redirect_stdout(io.StringIO()):
                    check_package(vale, package)
                for call in run.call_args_list:
                    self.assertIn("--no-global", call.args[0])

    def test_expected_errors_and_clean_result_pass(self):
        self.run_check()

    def test_missing_or_extra_rules_fail(self):
        for rules in (RULES - {"Crefft.US"}, RULES | {"Vale.Repetition"}):
            with self.subTest(rules=rules), self.assertRaisesRegex(RuntimeError, "unexpected alerts"):
                self.run_check(checks=rules)

    def test_wrong_exit_codes_fail(self):
        for overrides in ({"probe_code": 0}, {"probe_code": 2}, {"clean_code": 1}):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(RuntimeError, "expected exit"):
                self.run_check(**overrides)

    def test_rules_must_remain_errors(self):
        with self.assertRaisesRegex(RuntimeError, "must remain errors"):
            self.run_check(severity="warning")


if __name__ == "__main__":
    unittest.main()
