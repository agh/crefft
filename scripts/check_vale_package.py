#!/usr/bin/env python3
"""Sync a built package in an isolated consumer and check bad and good prose."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = {"Crefft.US", "Crefft.Direct", "Crefft.Literals"}


def check_package(vale: Path, package: Path) -> None:
    vale, package = vale.resolve(strict=True), package.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="crefft-vale-") as directory:
        consumer = Path(directory)
        config = consumer / ".vale.ini"
        config.write_text(
            "StylesPath = styles\nMinAlertLevel = warning\n"
            f"Packages = {package}\n",
            encoding="utf-8",
        )
        command = [str(vale), "--no-global", f"--config={config}"]
        subprocess.run(
            [*command, "sync", "--plain-progress"], cwd=consumer, check=True
        )
        for name in ("probe", "clean"):
            path = consumer / f"{name}.md"
            path.write_bytes((ROOT / f"configs/vale/fixtures/{name}.txt").read_bytes())
            result = subprocess.run(
                [*command, "--output=JSON", str(path)],
                cwd=consumer, text=True, capture_output=True, check=False,
            )
            print(f"{name}.md (exit {result.returncode}):", flush=True)
            if result.stderr:
                print(result.stderr, end="", flush=True)
            expected = 1 if name == "probe" else 0
            if result.returncode != expected:
                print(result.stdout, end="", flush=True)
                raise RuntimeError(f"{name}.md: expected exit {expected}")
            alerts = [alert for group in json.loads(result.stdout).values() for alert in group]
            for alert in alerts:
                print(
                    f"  {alert['Line']}:{alert['Span'][0]}:{alert['Check']}: "
                    f"{alert['Message']}",
                    flush=True,
                )
            if not alerts:
                print("  no alerts", flush=True)
            checks = {alert["Check"] for alert in alerts}
            if (name == "probe" and checks != RULES) or (name == "clean" and alerts):
                raise RuntimeError(f"{name}.md: unexpected alerts: {sorted(checks)}")
            if any(alert["Severity"] != "error" for alert in alerts):
                raise RuntimeError(f"{name}.md: package rules must remain errors")
        print("Consumer package check passed: all three rules fired; clean prose had no alerts.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vale", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    check_package(args.vale, args.package)


if __name__ == "__main__":
    main()
