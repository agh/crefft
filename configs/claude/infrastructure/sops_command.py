"""Check sealed metadata or supply two named keys to one trusted consumer."""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

SOPS_VERSION = b"sops 3.13.3"
SECRET_KEYS = frozenset(("POSTGRES_USER", "POSTGRES_PASSWORD"))
FAILURE = "Secret operation failed."


class SecretError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SecretError


def decrypt(sops: Path, identity: Path, source: Path) -> dict[str, str]:
    if not all(path.is_absolute() and path.is_file() for path in (sops, identity, source)):
        raise SecretError

    sops_env = {
        "HOME": str(identity.parent),
        "XDG_CONFIG_HOME": str(identity.parent),
        "SOPS_AGE_KEY_FILE": str(identity),
        "SOPS_DISABLE_VERSION_CHECK": "1",
    }
    version = subprocess.run(
        [str(sops), "--version"],
        env=sops_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if version.returncode or version.stdout.strip() != SOPS_VERSION:
        raise SecretError

    with tempfile.TemporaryDirectory(prefix="sops-pipe-") as directory:
        fifo = Path(directory) / "plaintext"
        os.mkfifo(fifo, 0o600)
        with os.fdopen(os.open(fifo, os.O_RDONLY | os.O_NONBLOCK), "rb") as reader:
            os.set_blocking(reader.fileno(), True)
            # SOPS opens its output read/write; macOS cannot reopen a write-only pipe that way.
            with os.fdopen(os.open(fifo, os.O_RDWR), "wb") as writer:
                fifo.unlink()
                process = subprocess.Popen(
                    [
                        str(sops), "decrypt",
                        "--input-type", "yaml",
                        "--output-type", "json",
                        "--extract", '["postgres_readonly"]',
                        "--output", f"/dev/fd/{writer.fileno()}",
                        str(source),
                    ],
                    env=sops_env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    pass_fds=(writer.fileno(),),
                )
            with process:
                plaintext = reader.read()
                if process.wait() != 0:
                    raise SecretError

    values = json.loads(plaintext)
    if not isinstance(values, dict) or values.keys() != SECRET_KEYS:
        raise SecretError
    if not all(isinstance(value, str) and value and "\0" not in value for value in values.values()):
        raise SecretError
    return values


def main() -> int:
    parser = Parser(description=__doc__)
    parser.add_argument("--sops", required=True, type=Path)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    try:
        args = parser.parse_args()
        command = args.command
        if command[:1] == ["--"]:
            command = command[1:]
        if args.check:
            if command:
                raise SecretError
        elif not command or not Path(command[0]).is_absolute():
            raise SecretError

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        values = decrypt(args.sops, args.identity, args.file)
        if args.check:
            for key in sorted(SECRET_KEYS):
                print(f"{key}: length={len(values[key].encode('utf-8'))} bytes")
        else:
            result = subprocess.run(
                command,
                env={"LC_ALL": "C", **values},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if result.returncode:
                raise SecretError
    except (SecretError, OSError, ValueError):
        print(FAILURE, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
