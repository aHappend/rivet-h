#!/usr/bin/env python3
"""Portable RIVET-H2 acceptance entry using only Python's standard library.

behavior: Icarus (PARTIAL_BEATS=0,1 x seeds 17,89,2027), full independent
hashlib/hmac comparisons, RFC vectors, million-a, context ownership, protocol
faults/reset/cancellation, exact boundary-cycle fixtures and Verilator subsets.
compatibility: immutable H1 and default H2 separately compared with hashlib.
defects: six compiling disposable mutations, each with a passing original
witness and an executed functional-assertion rejection.
synthesis: both legal configurations, checked hierarchy, Yosys synthesis,
driven outputs, substantive storage/arithmetic, zero latches/blackboxes/loops.
portable: a fresh source-only directory executes the bounded SHA/HMAC/context/
stall/cancel subset and default synthesis, NOT the full behavior matrix.

Invoke --check behavior|compatibility|defects|synthesis|portable --output
evidence/<fresh-name>. Every child has a 3600-second tool deadline, raw logs
and a source-bound receipt; simulation also has explicit cycle watchdogs.
Measurements and comparison denominators come from executed public-pin
assertions and per-message ledgers. --probe is advisory preparation only:
it never substitutes for the five shared-runtime acceptance checks.
"""
import argparse
import collections
import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import random
import shutil
import subprocess
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import IV, compress, digest, self_test, state_int
from scenarios import (Workload, arbitration, cancellation, compatibility_workload,
                       interleave, main_workload, malformed, mask_errors,
                       mutation_workload, near_limit, portable_workload, residues, vectors,
                       KEY_LENGTHS, MESSAGE_LENGTHS)

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 3600
SELECTORS = ("rtl/*.sv", "design/*.md", "rivet_h1_reference/rtl/*.sv", "tests/*")
TOOLS = {
    "python3": ["python3", "--version"],
    "iverilog": ["iverilog", "-V"], "vvp": ["vvp", "-V"],
    "verilator": ["verilator", "--version"], "yosys": ["yosys", "-V"],
    "make": ["make", "--version"], "g++": ["g++", "--version"],
}


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def sources():
    files = []
    for selector in SELECTORS:
        matches = sorted(p for p in ROOT.glob(selector) if p.is_file())
        if not matches:
            raise AssertionError(f"empty source selector: {selector}")
        files.extend(matches)
    return sorted(set(files))


def inventory():
    return {relative(p): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                          "bytes": p.stat().st_size,
                          "lines": len(p.read_bytes().splitlines()),
                          "modules": re.findall(r"^\s*module\s+(\w+)", p.read_text(), re.M)}
            for p in sources()}


def write_json(path, value):
    # All output directories are fresh; receipts are written once, never repaired.
    with path.open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")


class Execution:
    def __init__(self, output, required):
        self.output = output
        self.inputs = inventory()
        self.records = []
        self.versions = {}
        self.repair_of = None
        self.started = utc()
        self.output.mkdir(parents=True, exist_ok=False)
        snapshot = output / "sources"
        for source in sources():
            target = snapshot / relative(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        self.required = required

    def establish_tools(self):
        for tool in self.required:
            if shutil.which(tool) is None:
                raise FileNotFoundError(f"required executable unavailable: {tool}")
            record = self.run(TOOLS[tool], f"version-{tool}")
            self.versions[tool] = Path(ROOT / record["stdout"]).read_text().splitlines()[:3]

    def run(self, argv, label, expect_success=True, cwd=ROOT, extra=None, env_remove=()):
        if inventory() != self.inputs:
            raise AssertionError("declared sources changed since snapshot; tool not launched")
        folder = self.output / label
        folder.mkdir(parents=True, exist_ok=False)
        stdout = folder / "stdout.txt"
        stderr = folder / "stderr.txt"
        argv = [str(x) for x in argv]
        start = utc()
        before = time.monotonic()
        timed_out = False
        code = None
        error = None
        try:
            with stdout.open("w") as out, stderr.open("w") as err:
                environment = {k: v for k, v in os.environ.items() if k not in env_remove}
                result = subprocess.run(argv, cwd=cwd, stdout=out, stderr=err,
                                        timeout=TIMEOUT, env=environment)
                code = result.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            error = "child tool wall-clock timeout (not a numerical result)"
        except OSError as exc:
            error = str(exc)
        unchanged = inventory() == self.inputs
        record = {
            "argv": argv, "cwd": relative(cwd) or ".", "started_at": start,
            "ended_at": utc(), "elapsed_s": time.monotonic() - before,
            "timeout_s": TIMEOUT, "exit_code": code, "timed_out": timed_out,
            "error": error, "source_inventory": self.inputs,
            "tool_versions": dict(self.versions), "stdout": relative(stdout),
            "stderr": relative(stderr), "extra": extra,
            "removed_environment_variables": list(env_remove),
            "sources_unchanged_after_execution": unchanged,
        }
        write_json(folder / "receipt.json", record)
        self.records.append(relative(folder / "receipt.json"))
        if not unchanged:
            raise AssertionError(f"sources changed during execution: {relative(folder / 'receipt.json')}")
        if timed_out or error or (expect_success and code != 0):
            raise AssertionError(f"tool failure: {relative(folder / 'receipt.json')} exit={code} {error or ''}")
        return record

    def finish(self, result, status="passed"):
        write_json(self.output / "receipt.json", {
            "kind": "advisory_preparation" if "preparation" in self.output.parts else "verification_check",
            "entry_argv": sys.argv, "cwd": ".",
            "started_at": self.started, "ended_at": utc(), "status": status,
            "exit_code": 0 if status == "passed" else 1,
            "timeout_s": TIMEOUT, "source_inventory": self.inputs,
            "tool_versions": self.versions, "execution_receipts": self.records,
            "result": result,
            "repair_of": self.repair_of,
        })


def compile_sim(ex, label, partial, h1=False, simulator="icarus", rtl=None):
    rtl = sorted((ROOT / "rtl").glob("*.sv")) if rtl is None else rtl
    # Both tops elaborate independently; unused hierarchy is discarded.
    inputs = [relative(p) for p in rtl]
    inputs += [relative(p) for p in sorted((ROOT / "rivet_h1_reference/rtl").glob("*.sv"))]
    destination = ex.output / label
    destination.mkdir()
    if simulator == "icarus":
        binary = destination / "simulation.vvp"
        argv = ["iverilog", "-g2012", "-Wall", "-s", "bridge",
                f"-Pbridge.PARTIAL={partial}", f"-Pbridge.H1={int(h1)}",
                "-o", relative(binary), "tests/bridge.sv"] + inputs
    else:
        obj = destination / "obj"
        binary = obj / "Vbridge"
        argv = ["verilator", "--binary", "--timing", "--assert", "-Wno-fatal",
                "--top-module", "bridge", f"-GPARTIAL={partial}", f"-GH1={int(h1)}",
                "--Mdir", relative(obj), "-j", "2", "tests/bridge.sv"] + inputs
    ex.run(argv, label + "-compile")
    return binary


def simulate(ex, binary, label, partial, seed, generator, h1=False, negative=False):
    folder = ex.output / label
    folder.mkdir()
    stim = folder / "stimulus.txt"
    workload = Workload(stim, partial, seed, h1)
    metadata = generator(workload)
    write_json(folder / "workload.json", metadata)
    argv = ([relative(binary)] if binary.suffix != ".vvp" else ["vvp", relative(binary)])
    argv += ["+stim=" + relative(stim)]
    rec = ex.run(argv, label + "-run", expect_success=not negative,
                 extra={"partial_beats": partial, "seed": seed, "h1": h1,
                        "stimulus_sha256": hashlib.sha256(stim.read_bytes()).hexdigest()})
    log = (ROOT / rec["stdout"]).read_text() + (ROOT / rec["stderr"]).read_text()
    if negative:
        if rec["exit_code"] == 0 or rec["timed_out"]:
            raise AssertionError("mutation not detected by a functional assertion")
        # Compilation was checked separately. Require a specific executed oracle.
        match = re.search(r"ASSERT_(DIGEST|CONTEXT|REGISTERED_CAPTURE|DIGEST_STALL|LATENCY)\b[^\n]*", log)
        if not match:
            raise AssertionError(f"mutation failed without identified functional witness: {rec['stdout']}")
        result = {"classification": "functional_assertion_rejection", "witness": match.group(0),
                  "receipt": relative(ex.output / (label + "-run") / "receipt.json"),
                  "partial_beats": partial, "seed": seed}
        write_json(folder / "result.json", result)
        return result
    rows = re.findall(r"^COMPARE (\d+) (\d+) (\d+) (\d+) (\d+)$", log, re.M)
    summaries = re.findall(r"^RESULT (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)$", log, re.M)
    if len(summaries) != 1:
        raise AssertionError(f"missing unique completed simulation ledger: {rec['stdout']}")
    counts = dict(zip(("comparisons", "sha", "hmac", "snapshots", "switches",
                       "cycles", "resets", "cancels"), map(int, summaries[0])))
    for field, expected in metadata["expected"].items():
        if field == "faults":
            actual = len(re.findall(r"^FAULT ", log, re.M))
        else:
            actual = counts[field]
        assert actual == expected, (label, field, actual, expected)
    assert len(rows) == counts["sha"] + counts["hmac"] == counts["comparisons"] > 0
    assert len({r[1] for r in rows}) == len(rows), "duplicate comparison identity"
    assert sum(int(row[0]) == 0 for row in rows) == counts["sha"]
    assert sum(int(row[0]) == 1 for row in rows) == counts["hmac"]
    assert len(metadata["comparisons"]) == len(rows)
    if "ASSERT_" in log or "FATAL" in log:
        raise AssertionError(f"assertion in simulator output: {rec['stdout']}")
    latency = [int(r[2]) for r in rows]
    measurements = []
    for row, expected in zip(rows, metadata["comparisons"]):
        assert int(row[1]) == expected["identity"]
        assert int(row[0]) == int(expected["mode"] == "hmac")
        measurements.append(dict(expected, last_beat_to_valid_cycles=int(row[2]),
                                 local_observation_span_cycles=int(row[3]),
                                 completion_cycle=int(row[4])))
    write_json(folder / "measurements.json", measurements)
    complete = [r for r in measurements if r["kind"] == "stream"]
    result = {
        "partial_beats": partial, "seed": seed, "h1": h1, "counts": counts,
        "digest_bit_mismatches": 0, "latency_units": "cycles",
        "latency_definition": "last accepted message beat to first observed m_valid (excluding output stall)",
        "latency_min": min(latency), "latency_max": max(latency),
        "local_observation_span_definition": "first accepted message beat since last reset/CANCEL/digest retirement to m_valid; context-resume spans are not whole-message latency",
        "whole_message_cycles_min": min((r["local_observation_span_cycles"] for r in complete), default=None),
        "whole_message_cycles_max": max((r["local_observation_span_cycles"] for r in complete), default=None),
        "whole_message_measurement_count": len(complete),
        "measurement_ledger": relative(folder / "measurements.json"),
        "throughput_definition": "completed compared messages / all simulated cycles (includes commands, stalls, resets)",
        "compared_messages_per_cycle": len(rows) / counts["cycles"],
        "receipt": relative(ex.output / (label + "-run") / "receipt.json"),
        "workload": relative(folder / "workload.json"),
    }
    write_json(folder / "result.json", result)
    return result


def compressor_check(ex):
    folder = ex.output / "compressor-unit"
    folder.mkdir()
    vectors = folder / "vectors.txt"
    rng = random.Random(7219)
    with vectors.open("w") as f:
        for i in range(40):
            state = IV if i < 20 else tuple(rng.getrandbits(32) for _ in range(8))
            block = rng.randbytes(64)
            expected = compress(state, block)
            f.write(f"{state_int(state):064x} {block.hex()} {state_int(expected):064x}\n")
    binary = folder / "unit.vvp"
    ex.run(["iverilog", "-g2012", "-Wall", "-s", "compress_tb", "-o", relative(binary),
            "tests/compress_tb.sv", "rtl/rivet_h2_compress.sv", "rtl/rivet_h2_schedule.sv"],
           "compressor-unit-compile")
    rec = ex.run(["vvp", relative(binary), "+vectors=" + relative(vectors)], "compressor-unit-run")
    log = (ROOT / rec["stdout"]).read_text()
    assert len(re.findall(r"^UNIT_COMPARE ", log, re.M)) == 40
    assert "UNIT_RESULT 40 66" in log and "ASSERT_" not in log
    return {"compared_blocks": 40, "clear_offsets": 66,
            "round_edges": 64, "feedforward_cycle_after_launch": 65,
            "controller_consumption_edge_after_launch": 66,
            "receipt": relative(ex.output / "compressor-unit-run/receipt.json")}


def behavior(ex, probe=False, probe_scenario="portable", probe_simulator="icarus"):
    result = {"model_crosscheck": self_test(), "matrix": [], "verilator": [], "million_a": []}
    if not probe or probe_scenario == "protocol":
        result["compressor_unit"] = compressor_check(ex)
    for partial in (0, 1):
        binary = compile_sim(ex, f"icarus-p{partial}", partial,
                             simulator=probe_simulator if probe else "icarus")
        for seed in ((17,) if probe else (17, 89, 2027)):
            generator = main_workload
            if probe:
                def generator(w):
                    if probe_scenario == "portable":
                        return portable_workload(w)
                    if probe_scenario == "protocol":
                        cancellation(w)
                        arbitration(w)
                        malformed(w)
                        near_limit(w)
                        mask_errors(w)
                    elif probe_scenario == "context":
                        residues(w, small=True)
                        interleave(w, 8)
                    elif probe_scenario == "vectors":
                        vectors(w)
                    return w.close()
            run = simulate(ex, binary, f"p{partial}-seed{seed}", partial, seed, generator)
            if not probe:
                assert run["counts"]["sha"] >= 100 and run["counts"]["hmac"] >= 100
                assert run["counts"]["switches"] >= 100
                metadata = json.loads((ROOT / run["workload"]).read_text())
                required = {"standard_sha", "rfc4231_all_seven_full_digests_and_case5_prefix",
                            "four_independent_contexts", "partial_block_roundtrip",
                            "save_after_finalization", "restore_after_finalization",
                            "key_replacement_without_cancel", "key_ingestion_exclusive",
                            "ready_high_before_output_creation", "public_cycle_table",
                            "near_limit_legal_padding", "whole_beat_overflow"}
                required.update(f"key_length_{n}" for n in KEY_LENGTHS)
                required.update(f"{mode}_message_length_{n}" for mode in ("sha", "hmac")
                                for n in MESSAGE_LENGTHS)
                for mode in ("sha", "hmac"):
                    required.update(
                        f"{'actual_save' if partial or r % 4 == 0 else 'import'}_{mode}_residue_{r}"
                        for r in range(64))
                assert all(metadata["scenarios"].get(name, 0) > 0 for name in required), (
                    "missing required completed scenario", sorted(required - metadata["scenarios"].keys()))
            result["matrix"].append(run)
        if not probe:
            def million(w):
                w.fresh()
                w.emit(17, 250000)
                w.expect(b"a" * 1000000)
                w.mark("sha_million_a")
                return w.close()
            result["million_a"].append(simulate(ex, binary, f"million-a-p{partial}", partial, 17, million))
            vbin = compile_sim(ex, f"verilator-p{partial}", partial, simulator="verilator")
            run = simulate(ex, vbin, f"verilator-subset-p{partial}", partial, 89,
                           lambda w: main_workload(w, full=False))
            assert run["counts"]["sha"] >= 25 and run["counts"]["hmac"] >= 25
            result["verilator"].append(run)
    if not probe:
        result["parameter_rejection"] = []
        for p in (-1, 2):
            binary = compile_sim(ex, f"invalid-p{p}", p)
            stim = ex.output / f"invalid-p{p}" / "empty.txt"
            stim.write_text("")
            rec = ex.run(["vvp", relative(binary), "+stim=" + relative(stim)],
                         f"invalid-p{p}-run", expect_success=False)
            log = (ROOT / rec["stdout"]).read_text()
            assert rec["exit_code"] != 0 and not rec["timed_out"]
            assert "PARAMETER ERROR: PARTIAL_BEATS" in log
            result["parameter_rejection"].append({"value": p, "receipt": relative(
                ex.output / f"invalid-p{p}-run/receipt.json")})
    return result


def compatibility(ex, probe=False):
    result = {"model_crosscheck": self_test(), "runs": []}
    for h1 in (True, False):
        binary = compile_sim(ex, "h1" if h1 else "h2-default", 0, h1=h1)
        run = simulate(ex, binary, "h1-paired" if h1 else "h2-paired", 0, 2027,
                       lambda w: compatibility_workload(w, full=not probe), h1=h1)
        if not probe:
            assert run["counts"]["sha"] >= 100
        result["runs"].append(run)
    # Pairing is by identical seed and source workload with independent
    # expected values; H2-only key ownership checks follow invalid traffic.
    expected_sequences = []
    for label in ("h1-paired", "h2-paired"):
        sequence = []
        for line in (ex.output / label / "stimulus.txt").read_text().splitlines():
            fields = line.split()
            if fields[0] == "2":
                sequence.append((fields[1], fields[4]))
        expected_sequences.append(sequence)
    assert expected_sequences[0] == expected_sequences[1]
    assert result["runs"][0]["counts"]["sha"] == result["runs"][1]["counts"]["sha"]
    result["paired_valid_messages"] = len(expected_sequences[0])
    return result


MUTATIONS = (
    ("sha_arithmetic", "rivet_h2_compress.sv", "32'h428a2f98", "32'h428a2f99"),
    ("ipad_opad", "rivet_h2_hmac.sv", "{64{8'h36}}", "{64{8'h37}}"),
    ("long_key", "rivet_h2_hmac.sv", "if (normalize && long_key)", "if (normalize && !long_key)"),
    ("restore_buffer", "rivet_h2_stream.sv", "block_data <= load_buffer;", "block_data <= 512'd0;"),
    ("restore_length", "rivet_h2_top.sv", "byte_count <= cmd_context[111:48];",
     "byte_count <= cmd_context[111:48] + 64'd1;"),
    ("restore_outer", "rivet_h2_hmac.sv", "outer_seed <= restore_outer;",
     "outer_seed <= restore_inner;"),
)


def defects(ex, only=None):
    result = {"model_crosscheck": self_test(), "mutations": []}
    for name, filename, before, after in MUTATIONS:
        if only is not None and name != only:
            continue
        copied = ex.output / ("mutant-" + name)
        copied.mkdir()
        rtl = []
        for source in sorted((ROOT / "rtl").glob("*.sv")):
            target = copied / source.name
            content = source.read_text()
            if source.name == filename:
                assert content.count(before) == 1
                original = content
                content = content.replace(before, after)
                (copied / "mutation.patch").write_text("".join(difflib.unified_diff(
                    original.splitlines(keepends=True), content.splitlines(keepends=True),
                    fromfile="rtl/" + filename, tofile="rtl/" + filename)))
            target.write_text(content)
            rtl.append(target)
        write_json(copied / "patch.json", {
            "file": "rtl/" + filename, "before": before, "after": after,
            "baseline_inventory": ex.inputs,
            "mutant_inventory": {relative(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in rtl},
            "witness": name, "h1_compatible_sha_witness": name == "sha_arithmetic",
            "interleaved_context_witness": name == "restore_outer",
            "unified_patch": relative(copied / "mutation.patch"),
        })
        generator = lambda w, kind=name: mutation_workload(w, kind)
        partial = 0 if name == "sha_arithmetic" else 1
        baseline = compile_sim(ex, "baseline-" + name, partial)
        good = simulate(ex, baseline, name + "-baseline", partial, 17, generator)
        binary = compile_sim(ex, name + "-mutant", partial, rtl=rtl)
        bad = simulate(ex, binary, name + "-witness", partial, 17, generator, negative=True)
        result["mutations"].append({"name": name, "baseline": good, "rejection": bad,
                                    "patch": relative(copied / "patch.json")})
    assert len(result["mutations"]) == (1 if only else 6)
    return result


def module_name(mod):
    names = mod.get("attributes", {}).get("hdlname", "").lstrip("\\").split()
    return names[0] if names else ""


def inspect_netlist(path, hierarchy=False):
    data = json.loads(path.read_text())
    modules = data["modules"]
    assert "rivet_h2_top" in modules
    counts = collections.Counter()
    state_bits = 0
    for name, mod in modules.items():
        attrs = mod.get("attributes", {})
        assert not int(str(attrs.get("blackbox", "0")), 2), ("blackbox", name)
        for cell in mod.get("cells", {}).values():
            typ = cell["type"]
            counts[typ] += 1
            assert "latch" not in typ.lower(), ("inferred latch", name, typ)
            assert typ in modules or typ.startswith("$"), ("unknown blackbox", name, typ)
            if "dff" in typ.lower():
                state_bits += len(cell["connections"].get("Q", []))
        drivers = set()
        for port in mod.get("ports", {}).values():
            if port["direction"] == "input":
                drivers.update(b for b in port["bits"] if isinstance(b, int))
        for cell in mod.get("cells", {}).values():
            for port, direction in cell.get("port_directions", {}).items():
                if direction == "output":
                    drivers.update(b for b in cell["connections"][port] if isinstance(b, int))
        for pname, port in mod.get("ports", {}).items():
            if port["direction"] == "output":
                assert all(not isinstance(b, int) or b in drivers for b in port["bits"]), (
                    "undriven output", name, pname)
    if hierarchy:
        top = modules["rivet_h2_top"]
        compressor = top["cells"]["u_compress"]["type"]
        assert module_name(modules[compressor]) == "rivet_h2_compress" or compressor == "rivet_h2_compress"
        scheduler = modules[compressor]["cells"]["u_schedule"]["type"]
        assert module_name(modules[scheduler]) == "rivet_h2_schedule" or scheduler == "rivet_h2_schedule"
        for instance, expected in (("u_stream", "rivet_h2_stream"),
                                   ("u_hmac", "rivet_h2_hmac"), ("u_context", "rivet_h2_context")):
            typ = top["cells"][instance]["type"]
            assert typ == expected or module_name(modules[typ]) == expected
        instances = collections.Counter()

        def visit(name):
            instances[module_name(modules[name]) or name] += 1
            for cell in modules[name].get("cells", {}).values():
                if cell["type"] in modules:
                    visit(cell["type"])

        visit("rivet_h2_top")
        assert instances == collections.Counter({
            "rivet_h2_top": 1, "rivet_h2_compress": 1, "rivet_h2_schedule": 1,
            "rivet_h2_stream": 1, "rivet_h2_hmac": 1, "rivet_h2_context": 1}), instances
        assert sum(v for k, v in counts.items() if k == "$add") > 10
        assert state_bits > 2000, ("missing substantive sequential storage", state_bits)
    else:
        assert state_bits > 2000
        assert sum(counts.values()) > 1000
    return {"modules": len(modules), "cell_instances_by_type": dict(sorted(counts.items())),
            "total_cell_instances": sum(counts.values()), "state_bits": state_bits,
            "latches": 0, "blackboxes": 0, "undriven_public_outputs": 0}


def synthesis(ex, partials=(0, 1), lower_only=False):
    result = []
    for partial in partials:
        folder = ex.output / f"yosys-p{partial}"
        folder.mkdir()
        before = folder / "hierarchy.json"
        after = folder / "synthesized.json"
        script = folder / "synthesis.ys"
        rtl = " ".join(relative(p) for p in sorted((ROOT / "rtl").glob("*.sv")))
        script.write_text(
            f"read_verilog -sv {rtl}\n"
            f"chparam -set PARTIAL_BEATS {partial} rivet_h2_top\n"
            "hierarchy -check -top rivet_h2_top\nproc\nopt\ncheck -assert\n"
            f"write_json {relative(before)}\n" +
            ("" if lower_only else "synth -top rivet_h2_top\ncheck -assert\nstat\n"
             f"write_json {relative(after)}\n"))
        rec = ex.run(["yosys", "-s", relative(script)], f"yosys-p{partial}-run")
        log = (ROOT / rec["stdout"]).read_text()
        assert "Found and reported 0 problems." in log
        assert not re.search(r"logic loop|found [1-9]\d* problems", log, re.I)
        assert not re.search(r"(?m)^\s*Latch inferred for signal", log)
        run = {"partial_beats": partial, "hierarchy": inspect_netlist(before, True),
               "synthesized": None if lower_only else inspect_netlist(after),
               "receipt": relative(ex.output / f"yosys-p{partial}-run/receipt.json")}
        write_json(folder / "result.json", run)
        result.append(run)
    return result


def portable(ex, probe=False):
    clean = ex.output / "clean"
    clean.mkdir()
    for source in sources():
        # Check shipped text, not generated tool logs or runtime-owned metadata.
        text = source.read_text()
        assert not re.search(r"/(?:data|home|root|tmp|Users|workspace)/", text), (
            "private absolute path", relative(source))
        assert not re.search(r"(?:\.vulcan|\.tooling|\.git)/|VULCAN[/]", text), (
            "runtime-owned dependency", relative(source))
        assert not re.search(
            r"gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text), (
                "credential material", relative(source))
        target = clean / relative(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # Fresh process resolves its own ROOT to the clean copy. No old executable,
    # oracle output, external PYTHONPATH or inherited runtime source is copied.
    child_output = "evidence/preparation/bounded-reproduction" if probe else "evidence/reproduction"
    cmd = ["python3", "tests/verify.py", "--check", "portable-child", "--output", child_output]
    if probe:
        cmd.append("--probe")
    rec = ex.run(cmd, "clean-reproduction", cwd=clean,
                 env_remove=("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"))
    child = json.loads((clean / child_output / "receipt.json").read_text())
    assert child["status"] == "passed"
    expected = ex.inputs
    assert child["source_inventory"] == expected
    return {"fresh_copy": relative(clean), "copied_inventory": expected,
            "child_result": child["result"], "receipt": relative(
                ex.output / "clean-reproduction/receipt.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True, choices=(
        "behavior", "compatibility", "defects", "synthesis", "portable", "portable-child"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probe", action="store_true",
                        help="bounded advisory smoke only; requires evidence/preparation output")
    parser.add_argument("--repair-of", type=Path,
                        help="project-relative retained preparation receipt repaired by this probe")
    parser.add_argument("--probe-scenario", choices=("portable", "protocol", "context", "vectors"),
                        default="portable", help="bounded advisory behavior selection, only with --probe")
    parser.add_argument("--probe-simulator", choices=("icarus", "verilator"), default="icarus")
    parser.add_argument("--probe-mutation", choices=tuple(m[0] for m in MUTATIONS),
                        default="restore_outer")
    args = parser.parse_args()
    if args.output.is_absolute() or ".." in args.output.parts:
        parser.error("--output must be project-relative without '..'")
    output = ROOT / args.output
    relative(output)
    if args.probe and args.output.parts[:2] != ("evidence", "preparation"):
        parser.error("--probe requires a unique evidence/preparation/<name> output")
    required = {
        "behavior": ("python3", "iverilog", "vvp", "verilator", "make", "g++"),
        "compatibility": ("python3", "iverilog", "vvp"),
        "defects": ("python3", "iverilog", "vvp"),
        "synthesis": ("python3", "yosys"),
        "portable": ("python3", "iverilog", "vvp", "yosys"),
        "portable-child": ("python3", "iverilog", "vvp", "yosys"),
    }[args.check]
    execution = None
    try:
        execution = Execution(output, required)
        execution.establish_tools()
        if args.repair_of:
            if args.repair_of.is_absolute() or ".." in args.repair_of.parts:
                raise ValueError("--repair-of must be project-relative")
            if not (ROOT / args.repair_of).is_file():
                raise FileNotFoundError(args.repair_of)
            execution.repair_of = args.repair_of.as_posix()
        if args.check == "behavior":
            result = behavior(execution, args.probe, args.probe_scenario, args.probe_simulator)
        elif args.check == "compatibility":
            result = compatibility(execution, args.probe)
        elif args.check == "defects":
            result = defects(execution, args.probe_mutation if args.probe else None)
        elif args.check == "synthesis":
            result = synthesis(execution, (0,) if args.probe else (0, 1), lower_only=args.probe)
        elif args.check == "portable":
            result = portable(execution, args.probe)
        else:
            model = self_test()
            binary = compile_sim(execution, "portable-p1", 1)
            run = simulate(execution, binary, "bounded-subset", 1, 17, portable_workload)
            result = {"bounded_behavior": run, "model_crosscheck": model,
                      "default_synthesis": synthesis(execution, (0,), lower_only=args.probe)}
        execution.finish(result)
        print(json.dumps({"check": args.check, "status": "passed",
                          "advisory_only": args.probe, "receipt": relative(output / "receipt.json")}))
        return 0
    except Exception as exc:
        if execution is not None:
            execution.finish({"error": str(exc), "traceback": traceback.format_exc()}, "failed")
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
