"""Exclusive project-local diagnostic retention; no runtime state is edited."""

import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def source_files(root):
    return sorted([*root.glob("rtl/*.sv"), *root.glob("design/*.md"),
                   *root.glob("tests/*"), *root.glob("rivet_h4_reference/rtl/*.sv")])


class Run:
    def __init__(self, root, stem, preparation=False, repair_of=None):
        self.root = Path(root).resolve()
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        parent = self.root / "evidence"
        if preparation:
            parent /= "preparation"
        parent.mkdir(parents=True, exist_ok=True)
        self.path = parent / f"{stem}-{timestamp}-{secrets.token_hex(4)}"
        self.path.mkdir()
        self.start = utc()
        self.children = []
        self.sources = {str(p.relative_to(self.root)): digest(p)
                        for p in source_files(self.root) if p.is_file()}
        self.versions = {}
        self.repair_of = repair_of
        snapshot = self.path / f"sources-{secrets.token_hex(4)}"
        snapshot.mkdir()
        for relative in self.sources:
            dest = snapshot / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.root / relative, dest)
        self.snapshot = str(snapshot.relative_to(self.root))

    def relative(self, path):
        return str(Path(path).relative_to(self.root))

    def command(self, argv, label, timeout=2700, cwd=None, expect_failure=False):
        workdir = self.root if cwd is None else Path(cwd).resolve()
        ident = label + "-" + secrets.token_hex(4)
        stdout = self.path / (ident + ".stdout.txt")
        stderr = self.path / (ident + ".stderr.txt")
        record = dict(argv=[str(a) for a in argv], cwd=str(workdir), start=utc(),
                      timeout_seconds=timeout, timed_out=False,
                      stdout=self.relative(stdout), stderr=self.relative(stderr))
        begin = time.monotonic()
        with stdout.open("xb") as out, stderr.open("xb") as err:
            child = subprocess.Popen(record["argv"], cwd=workdir, stdout=out,
                                     stderr=err, start_new_session=True)
            record["pid"] = child.pid
            try:
                while True:
                    try:
                        code = child.wait(timeout=min(30, max(0.01, timeout-(time.monotonic()-begin))))
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic()-begin >= timeout:
                            record["timed_out"] = True
                            os.killpg(child.pid, signal.SIGTERM)
                            try:
                                code = child.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                os.killpg(child.pid, signal.SIGKILL)
                                code = child.wait()
                            break
                        print(f"progress {label}: {int(time.monotonic()-begin)} seconds",flush=True)
            finally:
                record["end"] = utc()
        record.update(exit_status=code, child_settled=child.poll() is not None,
                      duration_seconds=time.monotonic()-begin)
        self.children.append(record)
        if record["timed_out"] or (code != 0 and not expect_failure):
            raise RuntimeError(f"{label}: exit {code}, timeout={record['timed_out']}; "
                               f"see {record['stdout']} and {record['stderr']}")
        return record, stdout.read_text(errors="replace"), stderr.read_text(errors="replace")

    def tool_version(self, tool, flag):
        rec, out, err = self.command([tool, flag], f"version-{tool}")
        self.versions[tool] = dict(stdout=rec["stdout"], stderr=rec["stderr"],
                                   text=(out+err).strip())

    def finish(self, exit_status, details):
        receipt = dict(argv=list(sys.orig_argv), cwd=str(Path.cwd()),
                       start=self.start, end=utc(), exit_status=exit_status,
                       source_sha256=self.sources, source_snapshot=self.snapshot,
                       tool_versions=self.versions, children=self.children,
                       child_settled=all(c["child_settled"] for c in self.children),
                       repair_of=self.repair_of, details=details)
        path = self.path / "receipt.json"
        with path.open("x",encoding="utf-8") as f:
            json.dump(receipt,f,indent=2)
            f.write("\n")
        print(self.relative(path),flush=True)
        return path
