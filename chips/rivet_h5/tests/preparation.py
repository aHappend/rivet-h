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
    parser.add_argument("probe", choices=("legacy", "legacy-extended", "full-top-synthesis", "mutation",
                                        "signature-boundaries", "parser", "protocol", "parameters-smoke",
                                        "portable"))
    parser.add_argument("--mutation")
    parser.add_argument("--repair-of")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    run = Run(root, args.probe, preparation=True, repair_of=args.repair_of)
    details = {}
    obj = None
    try:
        if args.probe in ("legacy", "legacy-extended"):
            from legacy_checks import build, check_counts, concurrency_fixture
            from legacy_vectors import generate
            vectors = run.path / ("legacy-vectors-" + secrets.token_hex(4) + ".txt")
            extended = args.probe == "legacy-extended"
            inventory = generate(vectors, 1, 3, compact=not extended, seeds=(17,))
            run.tool_version("verilator" if extended else "iverilog", "--version" if extended else "-V")
            argv, obj, ledger = build(run, 1, 3, "verilator" if extended else "icarus")
            concurrent = concurrency_fixture(run) if extended else None
            extra = ["+concurrent="+str(concurrent)] if extended else []
            rec, stdout, _ = run.command([*argv, "+vectors=" + str(vectors), *extra], "legacy-smoke",
                                         timeout=2700 if extended else 600)
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
        elif args.probe == "parser":
            from parser_checks import suite
            run.tool_version("verilator", "--version")
            details["result"] = suite(run)
        elif args.probe == "portable":
            from verify import portable
            for tool,flag in (("iverilog","-V"),("verilator","--version"),("yosys","-V")):
                run.tool_version(tool,flag)
            details["result"] = portable(run)
        elif args.probe == "parameters-smoke":
            from parameter_checks import diagnostic
            run.tool_version("iverilog","-V")
            run.tool_version("vvp","-V")
            details["result"] = diagnostic(run)
        elif args.probe == "protocol":
            from simulation import build, check_counts, simulate
            vectors = run.path/("protocol-vectors-"+secrets.token_hex(4)+".txt")
            with vectors.open("x") as f:
                for service in range(3):
                    for phase in range(3):
                        for reset in (0,1):
                            f.write(f"9 {service} {phase} {reset}\n")
                f.write("0 0 0 0\n")
            run.tool_version("verilator","--version")
            argv,obj,_ = build(run,"core_tb","verilator",clock_limit=500000)
            rec,out = simulate(run,argv,vectors,"lifecycle-protocol","verilator")
            details.update(observed=check_counts(out,dict(operations=19,comparisons=19),"core_tb"),
                           stdout=rec["stdout"],stderr=rec["stderr"])
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
