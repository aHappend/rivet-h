"""Retained bounded reference-validation probe; no RTL acceptance is claimed."""

import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from execution import Run


def worker(output):
    from mldsa_reference import crosscheck_kats,keygen,sign,verify
    fixture = json.loads((Path(__file__).parent/"acvp_sigver.json").read_text())
    outcomes = crosscheck_kats(fixture)
    generated = []
    for level in range(3):
        pk,sk = keygen(bytes([level+1])*32,level)
        for message,context in ((b"",b""),(bytes(range(256))*2,bytes(range(255)))):
            signature = sign(sk,message,context)
            result = verify(pk,signature,message,context,level)
            assert result["auth"],result
            generated.append(dict(level=level,pk=pk.hex(),signature=signature.hex(),
                                  message=message.hex(),context=context.hex(),result=result))
    Path(output).write_text(json.dumps(dict(public_kats=outcomes,generated=generated),indent=2)+"\n")
    print(f"SUMMARY public_kats={len(outcomes)} generated_valid={len(generated)}")


def main():
    if len(sys.argv)>1 and sys.argv[1]=="--worker":
        worker(sys.argv[2])
        return 0
    root = Path(__file__).resolve().parent.parent
    run = Run(root,"oracle-validation",preparation=True)
    details = {}
    try:
        run.tool_version("python3","--version")
        output = run.path/"oracle-results.json"
        rec,stdout,_ = run.command(["python3","tests/oracle_probe.py","--worker",
                                    run.relative(output)],"oracle-validation")
        data = json.loads(output.read_text())
        details.update(public_kats=len(data["public_kats"]),generated_valid=len(data["generated"]),
                       output=run.relative(output))
        run.finish(0,details)
        return 0
    except (OSError,RuntimeError,ValueError,AssertionError) as exc:
        details["failure"]=str(exc)
        run.finish(1,details)
        return 1


if __name__=="__main__":
    sys.exit(main())
