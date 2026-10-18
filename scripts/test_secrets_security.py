"""Run the documented sealed-secret commands without exposing fixture values."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from security_test_helpers import ROOT, fenced_blocks  # noqa: E402

GUIDE = "configs/claude/infrastructure/secrets.md"
HELPER = "configs/claude/infrastructure/sops_command.py"
FAILURE = "Secret operation failed.\n"


class SecretsGuideTests(unittest.TestCase):
    def test_only_scoped_helper_commands_are_documented(self):
        commands = [block for block in fenced_blocks(GUIDE) if "sops" in block]
        self.assertEqual(len(commands), 2, "expected one check and one consumer command")
        for command in commands:
            self.assertIn(HELPER, command)
            self.assertNotIn("exec-env", command)
            self.assertNotIn("sops -d", command)
        self.assertTrue((ROOT / HELPER).is_file(), "documented helper is missing")

    def test_guide_keeps_publishing_credentials_outside_agents(self):
        text = " ".join((ROOT / GUIDE).read_text().split())
        self.assertIn("Agents **MUST NOT** receive credentials that can publish or push", text)
        self.assertIn("separate, human-approved step outside the agent", text)
        self.assertIn("SOPS 3.13.3", text)


class SealedCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "posix" or not Path("/dev/fd").is_dir():
            raise unittest.SkipTest("sealed-secret commands require POSIX /dev/fd/")
        cls.tools = {}
        for variable, name, version in (
            ("SOPS_BIN", "sops", "sops 3.13.3"),
            ("AGE_BIN", "age", "v1.3.2"),
            ("AGE_KEYGEN_BIN", "age-keygen", "v1.3.2"),
        ):
            binary = shutil.which(os.environ.get(variable, name))
            if not binary:
                raise unittest.SkipTest(
                    f"{name} is unavailable; set {variable} to a pinned local binary "
                    "(for example, in .tmp-check/); no global installation is required"
                )
            result = subprocess.run(
                [binary, "--version"],
                env={"SOPS_DISABLE_VERSION_CHECK": "1"},
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode or result.stdout.strip() != version:
                raise unittest.SkipTest(
                    f"sealed-secret tests require {version}; set {variable} to a pinned "
                    "local binary (for example, in .tmp-check/)"
                )
            cls.tools[name] = str(Path(binary).resolve())

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.work = Path(self.tmpdir.name)
        self.identity = self.work / "identity.txt"
        self.source = self.work / "secrets.yaml"
        self.marker = self.work / "consumer-ran"
        self.parent_env = os.environ.copy()
        self.user = "synthetic-user-" + secrets.token_hex(12)
        self.password = "synthetic-password-" + secrets.token_hex(12) + "'\"\\\n$(false);\u00e9"
        self.unused = "synthetic-unrelated-" + secrets.token_hex(12)
        self.canaries = (self.user, self.password, self.unused)
        self.values = {"POSTGRES_USER": self.user, "POSTGRES_PASSWORD": self.password}
        self.payload = {
            "postgres_readonly": self.values,
            "unrelated": {"TOKEN": self.unused},
        }
        self.recipient = self.generate_identity(self.identity)
        self.encrypt(self.payload)
        self.env = {
            "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.defpath}",
            "SOPS_BIN": self.tools["sops"],
            "AGE_IDENTITY": str(self.identity),
            "SECRETS_FILE": str(self.source),
            "TMPDIR": str(self.work),
            "UNRELATED_PARENT_VARIABLE": "must-not-reach-the-consumer",
            "SOPS_AGE_KEY": "must-not-reach-the-consumer",
        }
        self.consumer = self.work / "consumer.py"
        self.consumer.write_text(
            textwrap.dedent(
                """\
                import hashlib
                import json
                import os
                import resource
                import sys
                from pathlib import Path

                Path(sys.argv[1]).write_text("consumer started\\n")
                expected = json.loads(sys.argv[2])
                # macOS adds this non-secret variable during Python startup, not inheritance.
                if sys.platform == "darwin":
                    os.environ.pop("__CF_USER_TEXT_ENCODING", None)
                valid = set(os.environ) == set(expected) | {"LC_ALL"}
                valid = valid and os.environ.get("LC_ALL") == "C"
                valid = valid and resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
                for name, digest in expected.items():
                    actual = hashlib.sha256(os.environ.get(name, "").encode()).hexdigest()
                    valid = valid and actual == digest
                if not valid:
                    sys.exit(17)
                if "--noisy" in sys.argv:
                    output = json.dumps(dict(os.environ)).encode()
                    os.write(1, output)
                    os.write(2, output)
                if "--fail" in sys.argv:
                    sys.exit(23)
                """
            ),
            encoding="utf-8",
        )

    def generate_identity(self, path: Path) -> str:
        result = subprocess.run(
            [self.tools["age-keygen"], "-o", str(path)],
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertTrue(result.returncode == 0, "temporary identity generation failed")
        result = subprocess.run(
            [self.tools["age-keygen"], "-y", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertTrue(result.returncode == 0, "temporary recipient lookup failed")
        return result.stdout.strip()

    def encrypt(self, payload: dict):
        result = subprocess.run(
            [
                self.tools["sops"], "encrypt",
                "--input-type", "json",
                "--output-type", "yaml",
                "--filename-override", str(self.source),
                "--age", self.recipient,
                "--output", str(self.source),
            ],
            input=json.dumps(payload).encode(),
            cwd=self.work,
            env={"SOPS_DISABLE_VERSION_CHECK": "1"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        self.assertTrue(result.returncode == 0, "synthetic fixture encryption failed")

    def run_documented(self, *, check: bool = False, child_args: tuple[str, ...] = (), **env: str):
        self.marker.unlink(missing_ok=True)
        command = next(
            block for block in fenced_blocks(GUIDE)
            if HELPER in block and ("--check" in block) == check
        )
        if not check:
            digests = {
                name: hashlib.sha256(value.encode()).hexdigest()
                for name, value in self.values.items()
            }
            consumer = shlex.join(
                [
                    sys.executable, "-I", str(self.consumer), str(self.marker),
                    json.dumps(digests), *child_args,
                ]
            )
            command = command.replace("/usr/local/libexec/postgres-readonly-check", consumer)
        result = subprocess.run(
            ["/bin/bash", "-euo", "pipefail", "-c", command],
            cwd=ROOT,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertFalse(
            any(
                form in result.stdout + result.stderr
                for value in self.canaries
                for form in (value, json.dumps(value)[1:-1])
            ),
            "a decrypted canary reached captured stdout or stderr",
        )
        self.assertTrue(os.environ == self.parent_env, "the parent environment changed")
        self.assertFalse(
            any(value in ambient for value in self.canaries for ambient in os.environ.values()),
            "a decrypted canary reached the parent environment",
        )
        for path in self.work.rglob("*"):
            if path.is_file():
                content = path.read_bytes()
                self.assertFalse(
                    any(
                        form.encode() in content
                        for value in self.canaries
                        for form in (value, json.dumps(value)[1:-1])
                    ),
                    "a decrypted canary reached a temporary artifact",
                )
        return result

    def assert_failed_before_child(self, **env: str):
        for check in (False, True):
            with self.subTest(mode="check" if check else "consumer"):
                result = self.run_documented(check=check, **env)
                self.assertTrue(result.returncode != 0, "failure incorrectly reported success")
                self.assertTrue(result.stdout == "", "failure printed unexpected stdout")
                self.assertTrue(result.stderr == FAILURE, "failure did not use the fixed message")
                self.assertFalse(self.marker.exists(), "consumer ran before validation succeeded")

    def test_check_prints_only_correct_byte_lengths(self):
        result = self.run_documented(check=True)
        self.assertTrue(result.returncode == 0, "metadata check failed")
        expected = "".join(
            f"{key}: length={len(value.encode())} bytes\n"
            for key, value in sorted(self.values.items())
        )
        self.assertTrue(result.stdout == expected, "metadata did not match labeled byte lengths")
        self.assertTrue(result.stderr == "", "metadata check printed unexpected stderr")
        self.assertFalse(self.marker.exists(), "metadata check launched the consumer")

    def test_child_receives_exact_keys_without_output_or_artifacts(self):
        result = self.run_documented()
        self.assertTrue(result.returncode == 0, "scoped consumer failed")
        self.assertTrue(self.marker.exists(), "consumer did not verify the exact environment")
        self.assertTrue(result.stdout == result.stderr == "", "consumer output was not suppressed")

    def test_child_output_is_suppressed_even_on_failure(self):
        for child_args in (("--noisy",), ("--noisy", "--fail")):
            with self.subTest(failure="--fail" in child_args):
                result = self.run_documented(child_args=child_args)
                self.assertTrue(self.marker.exists(), "consumer did not run")
                failed = "--fail" in child_args
                self.assertTrue((result.returncode != 0) == failed, "wrong consumer exit status")
                self.assertTrue(result.stdout == "", "consumer stdout was forwarded")
                self.assertTrue(
                    result.stderr == (FAILURE if failed else ""),
                    "consumer stderr was forwarded or the failure was not reported",
                )

    def test_missing_file_stops_before_child(self):
        self.assert_failed_before_child(SECRETS_FILE=str(self.work / "ciphertext-fragment"))

    def test_missing_identity_stops_before_child(self):
        self.assert_failed_before_child(AGE_IDENTITY=str(self.work / "missing-identity"))

    def test_wrong_identity_stops_before_child(self):
        wrong_identity = self.work / "wrong-identity.txt"
        self.generate_identity(wrong_identity)
        self.assert_failed_before_child(AGE_IDENTITY=str(wrong_identity))

    def test_missing_branch_stops_before_child(self):
        self.encrypt({"unrelated": {"TOKEN": self.unused}})
        self.assert_failed_before_child()

    def test_missing_key_stops_before_child(self):
        self.encrypt({"postgres_readonly": {"POSTGRES_USER": self.user}})
        self.assert_failed_before_child()

    def test_extra_key_stops_before_child(self):
        self.encrypt({"postgres_readonly": {**self.values, "UNEXPECTED": self.unused}})
        self.assert_failed_before_child()

    def test_invalid_values_stop_before_child(self):
        for name, value in (
            ("empty", ""),
            ("null", None),
            ("number", 123),
            ("nested", {"TOKEN": self.unused}),
            ("nul-byte", self.password + "\0"),
        ):
            with self.subTest(shape=name):
                self.encrypt({"postgres_readonly": {**self.values, "POSTGRES_PASSWORD": value}})
                self.assert_failed_before_child()

    def test_tampered_ciphertext_or_mac_stops_before_child(self):
        ciphertext = self.source.read_text()
        for field in ("POSTGRES_USER:", "mac:"):
            with self.subTest(field=field):
                start = ciphertext.index("data:", ciphertext.index(field)) + len("data:")
                changed = "B" if ciphertext[start] == "A" else "A"
                self.source.write_text(ciphertext[:start] + changed + ciphertext[start + 1:])
                self.assert_failed_before_child()

    def test_malformed_file_stops_before_child(self):
        self.source.write_text("not: [valid YAML\nciphertext-fragment\n")
        self.assert_failed_before_child()

    def test_missing_sops_stops_before_child(self):
        self.assert_failed_before_child(SOPS_BIN=str(self.work / "missing-sops"))

    def test_wrong_sops_version_stops_before_child(self):
        stub = self.work / "sops"
        stub.write_text(f'#!{sys.executable}\nprint("sops 0.0.0")\n')
        stub.chmod(0o700)
        self.assert_failed_before_child(SOPS_BIN=str(stub))

    def test_nonzero_decryption_with_valid_output_stops_before_child(self):
        stub = self.work / "sops"
        stub.write_text(
            f"#!{sys.executable}\n"
            + f"real_sops = {self.tools['sops']!r}\n"
            + textwrap.dedent(
                """\
                import subprocess
                import sys

                if sys.argv[1:] == ["--version"]:
                    print("sops 3.13.3")
                else:
                    output = sys.argv[sys.argv.index("--output") + 1]
                    descriptor = int(output.rsplit("/", 1)[1])
                    subprocess.run(
                        [real_sops, *sys.argv[1:]],
                        pass_fds=(descriptor,),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=True,
                    )
                    sys.exit(1)
                """
            ),
            encoding="utf-8",
        )
        stub.chmod(0o700)
        self.assert_failed_before_child(SOPS_BIN=str(stub))

    def test_raw_sops_diagnostics_never_escape(self):
        stub = self.work / "sops"
        stub.write_text(
            f"#!{sys.executable}\n"
            + textwrap.dedent(
                """\
                import os
                import sys
                from pathlib import Path

                if sys.argv[1:] == ["--version"]:
                    print("sops 3.13.3")
                else:
                    content = Path(sys.argv[-1]).read_bytes()
                    content += Path(os.environ["SOPS_AGE_KEY_FILE"]).read_bytes()
                    os.write(1, content)
                    os.write(2, content)
                    sys.exit(1)
                """
            ),
            encoding="utf-8",
        )
        stub.chmod(0o700)
        self.assert_failed_before_child(SOPS_BIN=str(stub))


if __name__ == "__main__":
    unittest.main()
