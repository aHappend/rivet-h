"""Bounded project-local diagnostics; never edits admitted execution records."""

import argparse
from pathlib import Path
import secrets
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from execution import Run
from simulation import cleanup_objects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probe", choices=("legacy", "full-top-synthesis", "mutation", "signature-boundaries"))
    parser.add_argument("--mutation")
    parser.add_argument("--repair-of")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    run = Run(root, args.probe, preparation=True, repair_of=args.repair_of)
    details = {}
    obj = None
    try:
        if args.probe == "legacy":
            from legacy_checks import build, check_counts
            from legacy_vectors import generate
            vectors = run.path / ("legacy-vectors-" + secrets.token_hex(4) + ".txt")
            inventory = generate(vectors, 1, 3, compact=True)
            run.tool_version("iverilog", "-V")
            run.tool_version("vvp", "-V")
            argv, obj, ledger = build(run, 1, 3, "icarus")
            rec, stdout, _ = run.command([*argv, "+vectors=" + str(vectors)], "legacy-smoke", timeout=600)
            details.update(inventory=inventory, parent_copy=ledger,
                           observed=check_counts(stdout, inventory),
                           stdout=rec["stdout"], stderr=rec["stderr"])
        elif args.probe == "full-top-synthesis":
            from synthesis_checks import synthesize
            run.tool_version("yosys", "-V")
            details["result"] = synthesize(run, "rivet_h5_top", page=1)
        elif args.probe == "mutation":
            from defect_checks import suite
            if not args.mutation:
                raise ValueError("--mutation is required for a bounded mutation probe")
            run.tool_version("verilator", "--version")
            details["result"] = suite(run, selection=(args.mutation,))
        else:
            from signature_vectors import boundary_probe
            from simulation import build, check_counts, simulate
            vectors = run.path / ("signature-boundaries-" + secrets.token_hex(4) + ".txt")
            inventory = boundary_probe(vectors, root / "tests/acvp_sigver.json")
            details["inventory"] = inventory
            run.tool_version("verilator", "--version")
            argv, obj, observation = build(run, "signature_tb", "verilator", observe=True)
            details["observation"] = observation
            rec, out = simulate(run, argv, vectors, "signature-boundaries", "verilator")
            details.update(observed=check_counts(out, inventory["counts"], "signature_tb"),
                           stdout=rec["stdout"], stderr=rec["stderr"])
        cleanup_objects(obj)
        run.finish(0, details)
        return 0
    except (OSError, RuntimeError, ValueError, AssertionError, KeyError) as exc:
        cleanup_objects(obj)
        details["failure"] = str(exc)
        run.finish(1, details)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
