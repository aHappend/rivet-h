"""Bounded arithmetic-leaf synthesis diagnostic with full artifact retention."""

from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
from execution import Run
from synthesis_checks import synthesize


def main():
    run = Run(Path(__file__).resolve().parent.parent,"arithmetic-synthesis",preparation=True)
    details = dict(results=[])
    try:
        run.tool_version("yosys","-V")
        for top in ("rivet_h5_montgomery","rivet_h5_butterfly"):
            details["results"].append(synthesize(run,top,mapped=True))
        run.finish(0,details)
        return 0
    except (OSError,RuntimeError,ValueError,AssertionError) as exc:
        details["failure"]=str(exc)
        run.finish(1,details)
        return 1


if __name__=="__main__":
    sys.exit(main())
