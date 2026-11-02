"""Reusable builds and test-only observation, without editing production RTL."""

from pathlib import Path
import re
import secrets
import shutil

from execution import digest


def instrument_signature(root, directory):
    source = root/"rtl/rivet_h5_verify.sv"
    text = source.read_text()
    port_marker = "output wire pq_key_locked\n"
    register_marker = "reg [511:0] tr, mu, challenge, reconstructed_challenge;"
    if text.count(port_marker)!=1 or text.count(register_marker)!=1:
        raise AssertionError("signature observation anchor not unique")
    text = text.replace(port_marker,
                        "output wire pq_key_locked,\n    output wire [511:0] verification_challenge\n")
    text = text.replace(register_marker,register_marker+
                        "\n    assign verification_challenge = reconstructed_challenge;")
    out = directory/"rivet_h5_verify_observed.sv"
    with out.open("x") as f:
        f.write(text)
    return out, dict(production_sha256=digest(source),simulation_sha256=digest(out),
                     transformation="Add read-only test output for the computed challenge register; no datapath/control edits.")


def build(run, bench, simulator, source_root=None, observe=False, clock_limit=None):
    root = run.root if source_root is None else Path(source_root)
    files = sorted(root.glob("rtl/*.sv"))
    observation = None
    if observe:
        out,observation = instrument_signature(root,run.path)
        files = [p for p in files if p.name!="rivet_h5_verify.sv"]+[out]
    sources = [str(p) for p in files]
    testbench = str(run.root/f"tests/{bench}.sv")
    if simulator=="icarus":
        binary = run.path/(bench+"-"+secrets.token_hex(4)+".vvp")
        args = ["iverilog","-g2012","-Wall","-s",bench]
        if clock_limit is not None:
            args += [f"-P{bench}.CLOCK_LIMIT={clock_limit}"]
        args += ["-o",str(binary),testbench,*sources]
        run.command(args,f"compile-{bench}-icarus")
        return ["vvp",str(binary)], None, observation
    obj = run.path/("compile-obj-"+secrets.token_hex(4))
    args = ["verilator","--binary","--timing","-Wno-fatal","--top-module",bench,
            "--Mdir",str(obj),"-j","2"]
    if clock_limit is not None:
        args += [f"-GCLOCK_LIMIT={clock_limit}"]
    args += [testbench,*sources]
    run.command(args,f"compile-{bench}-verilator")
    return [str(obj/("V"+bench))], obj, observation


def simulate(run,argv,vectors,label,simulator):
    rec,out,_ = run.command([*argv,"+vectors="+str(vectors)],label,
                            timeout=600 if simulator=="icarus" else 2700)
    if "SUMMARY " not in out:
        raise AssertionError(f"{label}: missing observed simulation summary")
    return rec,out


def cleanup_objects(obj):
    if obj is not None:
        for p in sorted(obj.glob("*")):
            if p.is_file() and p.suffix in (".o",".a",".gch",".d"):
                p.unlink()
