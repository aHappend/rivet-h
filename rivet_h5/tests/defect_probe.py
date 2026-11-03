"""One bounded disposable arithmetic mutation, using unchanged comparisons."""

from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
from execution import Run
from defect_checks import suite


def main():
    run = Run(Path(__file__).resolve().parent.parent,"montgomery-defect-sensitivity",preparation=True)
    details = {}
    try:
        run.tool_version("verilator","--version")
        details = suite(run,selection=("montgomery-correction",))
        run.finish(0,details)
        return 0
    except (OSError,RuntimeError,ValueError,AssertionError) as exc:
        details["failure"]=str(exc)
        run.finish(1,details)
        print(str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.exit(main())
