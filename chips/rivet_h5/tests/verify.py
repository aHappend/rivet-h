"""Portable independent RIVET-H5 L1 verification.

Each suite freshly builds its own tools/artifacts and retains an exclusive receipt.
Physical timing and hardware gates are owned by the shared runtime.
"""

import argparse
import json
from pathlib import Path
import secrets
import shutil
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core_vectors import generate as core_vectors
from defect_checks import suite as defects
from execution import Run, digest, source_files
from signature_vectors import generate as signature_vectors
from simulation import build, check_counts, cleanup_objects, simulate
from synthesis_checks import suite as synthesis, synthesize


def core(run, compact=False, simulator="verilator"):
    vectors = run.path / ("core-vectors-" + secrets.token_hex(4) + ".txt")
    inventory, events = core_vectors(vectors, compact=compact)
    argv, obj, _ = build(run, "core_tb", simulator,
                         clock_limit=500000 if compact else 30000000)
    try:
        rec, stdout = simulate(run, argv, vectors, "core-" + simulator, simulator)
        observed = check_counts(stdout, inventory, "core_tb")
        if not compact:
            for op in (0, 1, 2, 4):
                if events[f"op_{op}_rejected"] <= 0:
                    raise AssertionError(f"sampler op {op}: no oracle-confirmed rejection exercised")
            for op in (0, 1, 2, 3):
                if events[f"op_{op}_rate_blocks"] <= 1:
                    raise AssertionError(f"sampler op {op}: no squeeze continuation")
            if events["op_4_swaps"] <= 0:
                raise AssertionError("SampleInBall fixtures exercise no nonzero swap collisions")
        return dict(inventory=inventory, oracle_sampler_events=events,
                    observed=observed, stdout=rec["stdout"], stderr=rec["stderr"])
    finally:
        cleanup_objects(obj)


def signatures(run, compact=False):
    vectors = run.path / ("signature-vectors-" + secrets.token_hex(4) + ".txt")
    inventory = signature_vectors(vectors, run.root / "tests/acvp_sigver.json",
                                  compact=compact)
    argv, obj, observation = build(run, "signature_tb", "verilator", observe=True)
    try:
        rec, stdout = simulate(run, argv, vectors, "signature-comparisons", "verilator")
        return dict(inventory=inventory, observation=observation,
                    observed=check_counts(stdout, inventory["counts"], "signature_tb"),
                    stdout=rec["stdout"], stderr=rec["stderr"])
    finally:
        cleanup_objects(obj)


def behavior(run):
    from legacy_checks import suite as legacy
    from parameter_checks import suite as parameters
    return dict(icarus=core(run, compact=True, simulator="icarus"),
                compiled_core=core(run), signatures=signatures(run),
                legacy=legacy(run), parameters=parameters(run))


def portable(run):
    destination = run.path / ("clean-reproduction-" + secrets.token_hex(4))
    destination.mkdir()
    files = [p for p in source_files(run.root) if p.is_file()]
    inventory = {}
    for p in files:
        relative = p.relative_to(run.root)
        if any(part in (".git", ".vulcan", ".tooling", "VULCAN", "evidence")
               for part in relative.parts):
            raise AssertionError(f"runtime source in portable selection: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
        inventory[str(relative)] = digest(target)
    for doc in destination.glob("design/*.md"):
        text = doc.read_text()
        for private in ("/data/", "/home/", "account/session", "PCIe BDF", "JTAG cable="):
            if private in text:
                raise AssertionError(f"nonportable documentation literal in {doc.name}: {private}")
    rec, _, _ = run.command(
        ["python3", "tests/verify.py", "--portable-child"],
        "fresh-portable-reproduction", cwd=destination)
    receipts = sorted(destination.glob("evidence/portable-child-*/receipt.json"))
    if len(receipts) != 1:
        raise AssertionError("clean reproduction did not retain exactly one fresh receipt")
    child = json.loads(receipts[0].read_text())
    if child["exit_status"] != 0 or not child["child_settled"]:
        raise AssertionError("clean reproduction did not finish successfully")
    if child["source_sha256"] != inventory:
        raise AssertionError("clean reproduction sources differ from copied source inventory")
    return dict(copied_source_sha256=inventory, child_receipt=run.relative(receipts[0]),
                stdout=rec["stdout"], stderr=rec["stderr"], child_details=child["details"])


def portable_child(run):
    from legacy_checks import suite as legacy
    return dict(icarus=core(run, compact=True, simulator="icarus"),
                verilator=core(run, compact=True), signatures=signatures(run, compact=True),
                legacy=legacy(run, compact=True),
                synthesis=synthesize(run, "rivet_h5_montgomery", mapped=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("behavior", "defects", "synthesis", "portable"))
    parser.add_argument("--portable-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    suites = ("portable-child",) if args.portable_child else (
        (args.suite,) if args.suite else ("behavior", "defects", "synthesis", "portable"))
    actions = {"behavior": behavior, "defects": defects, "synthesis": synthesis,
               "portable": portable, "portable-child": portable_child}
    for name in suites:
        run = Run(root, name)
        details = {}
        try:
            tools = (("yosys", "-V"),) if name == "synthesis" else (
                ("python3", "--version"), ("iverilog", "-V"), ("vvp", "-V"),
                ("verilator", "--version"), ("make", "--version"), ("g++", "--version"))
            if name in ("portable", "portable-child"):
                tools += (("yosys", "-V"),)
            for tool, flag in tools:
                run.tool_version(tool, flag)
            details["results"] = actions[name](run)
            run.finish(0, details)
        except (OSError, RuntimeError, AssertionError, ValueError, KeyError) as exc:
            details["failure"] = str(exc)
            run.finish(1, details)
            print(str(exc), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
