"""Portable independent RIVET-H5 L1 verification.

Each suite freshly builds its own tools/artifacts and retains an exclusive receipt.
Physical timing and hardware gates are owned by the shared runtime.
"""

import argparse
import json
import re
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
            for seed in (17,29,43):
                for label,minimum in ((f"montgomery_seed_{seed}",4160),
                    (f"butterfly_0_seed_{seed}",1024),(f"butterfly_1_seed_{seed}",1024),
                    (f"forward_seed_{seed}",24),(f"inverse_seed_{seed}",24),
                    (f"convolution_seed_{seed}",8)):
                    if inventory.get(label,0)<minimum:
                        raise AssertionError(f"missing required numerical matrix: {label}")
                for level in range(3):
                    for op in range(5):
                        if inventory.get(f"sampler_{op}_level_{level}_seed_{seed}",0)<4:
                            raise AssertionError("missing required sampler seed/level/mode comparisons")
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
        observed = check_counts(stdout, inventory["counts"], "signature_tb")
        valid = [case for case in inventory["cases"] if case["expected_auth"]]
        if not compact:
            for seed in (17,29,43):
                for level in range(3):
                    cases = [case for case in valid if case["label"].startswith(
                             f"valid_seed_{seed}_level_{level}_case_")]
                    if len(cases)<4 or any(case["oracle"]["hint_count"]<=0 for case in cases):
                        raise AssertionError("missing valid contextual signature/nonzero hint comparisons")
            for name in ("forged_message","forged_context","forged_challenge","forged_z","forged_hints"):
                cases = [case for case in inventory["cases"] if case["label"]==name]
                if len(cases)<36 or any(case["expected_auth"] for case in cases):
                    raise AssertionError("missing independently confirmed forgery comparisons")
        return dict(inventory=inventory, observation=observation,
                    observed=observed,
                    stdout=rec["stdout"], stderr=rec["stderr"])
    finally:
        cleanup_objects(obj)


def signature_startup(run):
    argv,obj,_ = build(run,"signature_startup_tb","icarus")
    try:
        rec,out,_ = run.command(argv,"icarus-signature-startup",timeout=600)
        matches = re.findall(r"SUMMARY results=(\d+) cancels=(\d+) resets=(\d+) clocks=(\d+)",out)
        if len(matches)!=1 or tuple(map(int,matches[0][:3]))!=(5,2,1):
            raise AssertionError("signature startup protocol comparisons missing")
        return dict(results=5,cancels=2,resets=1,clocks=int(matches[0][3]),
                    stdout=rec["stdout"],stderr=rec["stderr"])
    finally:
        cleanup_objects(obj)


def behavior(run):
    from legacy_checks import suite as legacy
    from parameter_checks import suite as parameters
    from parser_checks import suite as parser
    return dict(icarus=core(run, compact=True, simulator="icarus"),signature_startup=signature_startup(run),
                compiled_core=core(run), signatures=signatures(run),
                directed_parser=parser(run), legacy=legacy(run), parameters=parameters(run))


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
        for private in ("/data/", "/home/", "account/session", "JTAG cable="):
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
    return dict(icarus=core(run, compact=True, simulator="icarus"),signature_startup=signature_startup(run),
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
