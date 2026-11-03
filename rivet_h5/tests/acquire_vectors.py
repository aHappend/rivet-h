"""One-time public fixture acquisition; verification never uses the network."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
from execution import Run, digest


def main():
    root = Path(__file__).resolve().parent.parent
    run = Run(root,"public-kat-acquisition",preparation=True)
    details = {}
    try:
        run.tool_version("curl","--version")
        api = "https://api.github.com/repos/usnistgov/ACVP-Server/commits?path=gen-val/json-files/ML-DSA-sigVer-FIPS204/internalProjection.json&per_page=1"
        _, text, _ = run.command(["curl","-fsSL",api],"source-revision")
        commit = json.loads(text)[0]["sha"]
        url = f"https://raw.githubusercontent.com/usnistgov/ACVP-Server/{commit}/gen-val/json-files/ML-DSA-sigVer-FIPS204/internalProjection.json"
        rec, text, _ = run.command(["curl","-fsSL",url],"public-vectors")
        original = json.loads(text)
        groups = []
        for group in original["testGroups"]:
            if group["signatureInterface"] != "external" or group.get("preHash") != "pure":
                continue
            selected = {k: group[k] for k in ("tgId","parameterSet","signatureInterface","preHash","externalMu")}
            selected["tests"] = [
                {k: t[k] for k in ("tcId","testPassed","pk","message","context","signature","reason")
                 if k in t} for t in group["tests"]]
            groups.append(selected)
        fixture = dict(algorithm=original["algorithm"],revision=original["revision"],
                       source=dict(repository="usnistgov/ACVP-Server",commit=commit,url=url,
                                   original_sha256=digest(root/rec["stdout"]),
                                   extraction="External pure verification groups; signing keys and internal/prehash groups omitted."),
                       testGroups=groups)
        path = root/"tests/acvp_sigver.json"
        with path.open("x",encoding="ascii") as f:
            json.dump(fixture,f,separators=(",",":"))
            f.write("\n")
        details = dict(fixture="tests/acvp_sigver.json",sha256=digest(path),
                       groups=[dict(level=g["parameterSet"],tests=len(g["tests"]),
                                    valid=sum(t["testPassed"] for t in g["tests"])) for g in groups])
        run.finish(0,details)
        return 0
    except (OSError,RuntimeError,KeyError,ValueError) as exc:
        details["failure"]=str(exc)
        run.finish(1,details)
        return 1


if __name__ == "__main__":
    sys.exit(main())
