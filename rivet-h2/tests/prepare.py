#!/usr/bin/env python3
"""Retain a bounded preparation command even when the main entry cannot import."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    if (not argv or args.output.is_absolute() or ".." in args.output.parts
            or args.output.parts[:2] != ("evidence", "preparation") or len(args.output.parts) < 3):
        parser.error("require a command and fresh project-local evidence/preparation/<name>")
    output = root / args.output
    output.mkdir(parents=True, exist_ok=False)
    inventory = {}
    for pattern in ("rtl/*.sv", "design/*.md", "rivet_h1_reference/rtl/*.sv", "tests/*"):
        for source in sorted(root.glob(pattern)):
            if source.is_file():
                rel = source.relative_to(root)
                inventory[rel.as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
                target = output / "sources" / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    before = time.monotonic()
    code, timed_out, error = None, False, None
    with (output / "stdout.txt").open("w") as out, (output / "stderr.txt").open("w") as err:
        try:
            code = subprocess.run(argv, cwd=root, stdout=out, stderr=err, timeout=3600).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
        except OSError as exc:
            error = str(exc)
    version = subprocess.run(["python3", "--version"], cwd=root, capture_output=True, text=True, timeout=3600)
    receipt = {
        "kind": "advisory_preparation", "argv": argv, "cwd": ".",
        "source_sha256": inventory, "started_at": start,
        "ended_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "elapsed_s": time.monotonic() - before, "timeout_s": 3600,
        "exit_code": code, "timed_out": timed_out, "error": error,
        "tool_version": version.stdout.strip(), "tool_version_argv": ["python3", "--version"],
        "stdout": (args.output / "stdout.txt").as_posix(),
        "stderr": (args.output / "stderr.txt").as_posix(),
    }
    with (output / "receipt.json").open("x") as f:
        json.dump(receipt, f, indent=2)
        f.write("\n")
    print((args.output / "receipt.json").as_posix())
    return code if code is not None else 1


if __name__ == "__main__":
    sys.exit(main())
