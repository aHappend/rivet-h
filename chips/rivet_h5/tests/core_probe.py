"""Bounded advisory core probe; not an admitted L1 suite substitute."""

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
from core_vectors import generate
from execution import Run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator", choices=("icarus", "verilator"), default="icarus")
    parser.add_argument("--repair-of")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    run = Run(root, "core-smoke", preparation=True, repair_of=args.repair_of)
    result = {}
    obj = None
    try:
        vectors = run.path / "vectors.txt"
        planned, events = generate(vectors, compact=True)
        result.update(expected_comparisons=planned["comparisons"],
                      fixture_inventory=planned, oracle_sampler_events=events)
        sources = [str(p.relative_to(root)) for p in sorted(root.glob("rtl/*.sv"))]
        if args.simulator == "icarus":
            run.tool_version("iverilog", "-V")
            run.tool_version("vvp", "-V")
            binary = run.path / "core.vvp"
            run.command(["iverilog","-g2012","-Wall","-s","core_tb",
                         "-Pcore_tb.CLOCK_LIMIT=500000","-o",run.relative(binary),
                         "tests/core_tb.sv",*sources],"compile")
            rec, out, err = run.command(["vvp",run.relative(binary),
                                        "+vectors="+run.relative(vectors)],"simulate",timeout=600)
        else:
            run.tool_version("verilator", "--version")
            obj = run.path / ("compile-obj-"+run.path.name.rsplit("-",1)[1])
            run.command(["verilator","--binary","--timing","-Wno-fatal",
                         "--top-module","core_tb","-GCLOCK_LIMIT=500000",
                         "--Mdir",run.relative(obj),"-j","2",
                         "tests/core_tb.sv",*sources],"compile")
            rec, out, err = run.command([run.relative(obj/"Vcore_tb"),
                                        "+vectors="+run.relative(vectors)],"simulate")
        summary = re.findall(r"SUMMARY operations=(\d+) comparisons=(\d+) stalls=(\d+) clocks=(\d+)",out)
        if len(summary) != 1:
            raise AssertionError("missing/unexpected numerical summary")
        operations, comparisons, stalls, clocks = map(int,summary[0])
        if comparisons != planned["comparisons"] or operations != planned["operations"]:
            raise AssertionError(f"observed counts {operations}/{comparisons} disagree with fixture inventory")
        if stalls <= 0 or clocks > 500000:
            raise AssertionError("no observed stalls or compact clock bound exceeded")
        result.update(observed=dict(operations=operations,comparisons=comparisons,
                                    stalls=stalls,clocks=clocks))
        if obj is not None:
            from simulation import cleanup_objects
            cleanup_objects(obj)
        run.finish(0,result)
        return 0
    except (OSError, RuntimeError, AssertionError, ValueError) as exc:
        result["failure"] = str(exc)
        if obj is not None:
            from simulation import cleanup_objects
            cleanup_objects(obj)
        run.finish(1,result)
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
