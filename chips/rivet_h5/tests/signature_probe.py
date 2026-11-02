"""Bounded compiled end-to-end public-KAT signature diagnostic."""

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from execution import Run
from signature_vectors import generate
from simulation import build,simulate,cleanup_objects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-of")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    run = Run(root,"signature-public-kat",preparation=True,repair_of=args.repair_of)
    details = {}
    obj = None
    try:
        run.tool_version("verilator","--version")
        vectors = run.path/"signature-vectors.txt"
        ledger = generate(vectors,root/"tests/acvp_sigver.json",compact=True)
        ledger_path = run.path/"comparison-ledger.json"
        with ledger_path.open("x") as f:
            json.dump(ledger,f,indent=2)
            f.write("\n")
        details["comparison_ledger"] = run.relative(ledger_path)
        argv,obj,observation = build(run,"signature_tb","verilator",observe=True)
        details["test_only_observation"] = observation
        _,stdout = simulate(run,argv,vectors,"public-kat-signatures","verilator")
        matches = re.findall(r"SUMMARY commands=(\d+) beats=(\d+) results=(\d+) challenge_bytes=(\d+) stalls=(\d+) cancels=(\d+) resets=(\d+) clocks=(\d+)",stdout)
        if len(matches)!=1:
            raise AssertionError("signature observation summary missing")
        names = ("commands","beats","results","challenge_bytes","stalls","cancels","resets","clocks")
        observed = dict(zip(names,map(int,matches[0])))
        for name in names[:-1]:
            if observed[name]!=ledger["counts"].get(name,0):
                raise AssertionError(f"observed {name} count disagrees with independent fixture inventory")
        details["observed"] = observed
        cleanup_objects(obj)
        run.finish(0,details)
        return 0
    except (OSError,RuntimeError,ValueError,AssertionError) as exc:
        details["failure"]=str(exc)
        cleanup_objects(obj)
        run.finish(1,details)
        print(str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.exit(main())
