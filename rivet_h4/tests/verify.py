#!/usr/bin/env python3
"""Portable independent L1: simulation, crypto/protocol matrices, mutants, synthesis.

Run from the project root:
    python3 tests/verify.py --suite all --output-root evidence/l1
Compact mode is an additional packaging/probe check, never the complete matrix.
Native FPGA timing and hardware gates are owned by the shared runtime.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
import reference
import vectors

ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATTERNS = ("rtl/*.sv", "design/*.md", "tests/*", "rivet_h3_reference/rtl/*.sv")
TOOLS = {"python3": ["python3", "--version"], "iverilog": ["iverilog", "-V"],
         "vvp": ["vvp", "-V"], "verilator": ["verilator", "--version"],
         "yosys": ["yosys", "-V"]}


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_sources():
    sources = []
    for pattern in SOURCE_PATTERNS:
        found = sorted(p for p in ROOT.glob(pattern) if p.is_file())
        if not found:
            raise RuntimeError(f"Declared source pattern has no inputs: {pattern}")
        sources.extend(found)
    return sources


def relative(path):
    return os.path.relpath(path, ROOT)


class Execution:
    def __init__(self, output_root, repair_of=None):
        self.folder = Path(str(output_root) + "-" + stamp())
        self.folder.mkdir(parents=True, exist_ok=False)
        self.hashes = {relative(p): sha(p) for p in project_sources()}
        self.versions = {}
        self.records = []
        self.results = []
        self.sequence = 0
        self.repair_of = repair_of
        self.started = datetime.now(timezone.utc).isoformat()
        self.began = time.monotonic()
        self.stdout_log = self.folder / "entry.stdout.txt"
        self.stderr_log = self.folder / "entry.stderr.txt"
        self.original_stdout, self.original_stderr = sys.stdout, sys.stderr
        sys.stdout = Tee(sys.stdout, self.stdout_log)
        sys.stderr = Tee(sys.stderr, self.stderr_log)
        write_json(self.folder / "inputs.json", self.hashes)

    def directory(self, stem):
        self.sequence += 1
        p = self.folder / f"{stem}-{stamp()}-{self.sequence:04d}"
        p.mkdir(exist_ok=False)
        return p

    def run(self, argv, stem, expected_failure=None, extra_sources=(), cwd=None, timeout=3600):
        folder = self.directory(stem)
        stdout = folder / "stdout.txt"
        stderr = folder / "stderr.txt"
        cwd = ROOT if cwd is None else cwd
        record = {"argv": [str(a) for a in argv], "cwd": relative(cwd),
                  "source_sha256": self.hashes | {relative(p): sha(p) for p in extra_sources},
                  "tool_version": self.versions.get(str(argv[0]), "version probe"),
                  "start_time": datetime.now(timezone.utc).isoformat(),
                  "timeout_s": timeout, "stdout_path": relative(stdout),
                  "stderr_path": relative(stderr), "repair_of": self.repair_of}
        began = time.monotonic()
        timed_out = False
        exit_code = None
        print(f"RUN {stem}", flush=True)
        try:
            with stdout.open("wb") as out, stderr.open("wb") as err:
                process = subprocess.Popen([str(a) for a in argv], cwd=cwd, stdout=out, stderr=err)
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        timed_out = True
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        break
                    try:
                        process.wait(timeout=min(25, max(0.01, deadline - time.monotonic())))
                    except subprocess.TimeoutExpired:
                        print(f"PROGRESS {stem} elapsed_s={time.monotonic()-began:.0f}", flush=True)
                exit_code = process.returncode
        except OSError as error:
            record["launch_error"] = str(error)
            raise
        finally:
            record.update({"end_time": datetime.now(timezone.utc).isoformat(),
                           "duration_s": time.monotonic() - began, "timed_out": timed_out,
                           "exit_code": exit_code})
            write_json(folder / "receipt.json", record)
            self.records.append(relative(folder / "receipt.json"))
        text = stdout.read_text(errors="replace")
        error_text = stderr.read_text(errors="replace")
        if timed_out:
            raise RuntimeError(f"Tool lifetime exceeded: {relative(folder / 'receipt.json')}")
        if expected_failure:
            if exit_code == 0 or expected_failure not in text + error_text:
                raise RuntimeError(f"Expected observable rejection {expected_failure!r}, got exit={exit_code}: "
                                   f"{relative(folder / 'receipt.json')}")
        elif exit_code != 0:
            raise RuntimeError(f"{stem} exit={exit_code}: {relative(folder / 'receipt.json')}\n"
                               f"{(text + error_text)[-5000:]}")
        return text, folder

    def tools(self):
        for name, argv in TOOLS.items():
            if not shutil.which(name):
                raise RuntimeError(f"Required installed tool unavailable: {name}")
            text, folder = self.run(argv, "version-" + name)
            combined = text + (folder / "stderr.txt").read_text(errors="replace")
            self.versions[name] = combined.splitlines()[0] if combined.splitlines() else "empty version response"
        write_json(self.folder / "versions.json", self.versions)

    def finish(self, status, error=None):
        now = {relative(p): sha(p) for p in project_sources()}
        source_changes = None
        if now != self.hashes:
            status = "failed"
            error = "Baseline source changed during execution"
            source_changes = {
                "added": sorted(now.keys() - self.hashes.keys()),
                "removed": sorted(self.hashes.keys() - now.keys()),
                "changed": sorted(p for p in now.keys() & self.hashes.keys()
                                  if now[p] != self.hashes[p])}
        result = {"status": status, "suite": ARGS.suite, "source_sha256": self.hashes,
                  "tools": self.versions, "runs": self.results, "receipts": self.records,
                  "error": error, "repair_of": self.repair_of,
                  "source_changes": source_changes, "observed_source_sha256": now,
                  "thresholds": {"numerical_mismatches": 0, "protocol_mismatches": 0,
                                 "unauthorized_tile_bytes": 0, "latch_cells": 0}}
        write_json(self.folder / "summary.json", result)
        print(f"{status.upper()} {relative(self.folder / 'summary.json')}", flush=True)
        if error:
            print(error, file=sys.stderr, flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        write_json(self.folder / "receipt.json", {
            "argv": ["python3", *sys.argv], "cwd": ".",
            "source_sha256": self.hashes, "tool_version": self.versions.get("python3"),
            "start_time": self.started, "end_time": datetime.now(timezone.utc).isoformat(),
            "duration_s": time.monotonic() - self.began, "timeout_s": None,
            "timed_out": False, "exit_code": 0 if status == "passed" else 1,
            "stdout_path": relative(self.stdout_log), "stderr_path": relative(self.stderr_log),
            "repair_of": self.repair_of, "subordinate_receipts": self.records})
        return status == "passed"


class Tee:
    def __init__(self, stream, path):
        self.stream = stream
        self.log = path.open("w")

    def write(self, value):
        self.stream.write(value)
        return self.log.write(value)

    def flush(self):
        self.stream.flush()
        self.log.flush()


def rtl_sources(folder=None):
    return sorted((ROOT / "rtl" if folder is None else folder).glob("*.sv"))


def compile_sim(ex, partial, capacity, simulator, parent=False, source_folder=None, leaf=False, stem="build"):
    folder = ex.directory(stem)
    sources = sorted((ROOT / "rivet_h3_reference/rtl").glob("*.sv")) if parent else rtl_sources(source_folder)
    top = "keccak_tb" if leaf else "bridge"
    bench = ROOT / "tests" / (top + ".sv")
    if leaf:
        sources = [next(p for p in sources if p.name == "rivet_h4_keccak.sv")]
    defines = [f"-DPB={partial}", f"-DPAGE_CAP={capacity}"] + (["-DPARENT"] if parent else [])
    if simulator == "icarus":
        binary = folder / "simulation.vvp"
        argv = ["iverilog", "-g2012", "-Wall", "-s", top, *defines, "-o", relative(binary),
                *map(relative, sources), relative(bench)]
    else:
        object_folder = folder / ("obj-" + stamp())
        binary = object_folder / ("V" + top)
        argv = ["verilator", "--binary", "--timing", "-j", "2", "-Wno-fatal", "--top-module", top,
                "--output-split", "10000", "--output-split-cfuncs", "500",
                "--Mdir", relative(object_folder), *defines,
                *map(relative, sources), relative(bench)]
    ex.run(argv, stem + "-compile", extra_sources=tuple(sources))
    if not binary.is_file():
        raise RuntimeError(f"Compiler did not produce {relative(binary)}")
    return binary


def clean_intermediates(binary):
    if binary.suffix == ".vvp":
        return
    # Keep the settled simulator, generated C++ and logs. Remove only compiler intermediates.
    for pattern in ("*.o", "*.a", "*.gch"):
        for path in binary.parent.glob(pattern):
            path.unlink()


def simulate(ex, binary, path, manifest, simulator="verilator", stem="behavior", expected_failure=None):
    argv = (["vvp", relative(binary)] if simulator == "icarus" else [relative(binary)])
    argv += ["+vectors=" + relative(path)]
    if simulator == "icarus":
        argv += ["+limit=500000"]
    text, folder = ex.run(argv, stem, expected_failure, extra_sources=(path,),
                          timeout=600 if simulator == "icarus" else 3600)
    if expected_failure:
        ex.results.append({"kind": "mutant", "name": stem, "status": "detected",
                           "intended_mismatch": expected_failure, "receipt": relative(folder / "receipt.json"),
                           "vectors_sha256": sha(path)})
        return text
    summary = re.search(r"SUMMARY rows=(\d+) cycles=(\d+) comparisons=(\d+) transfers=(\d+) stalls=(\d+) resets=(\d+)", text)
    if not summary:
        raise RuntimeError(f"No executed comparison summary: {relative(folder / 'receipt.json')}")
    rows, cycles, comparisons, transfers, stalls, resets = map(int, summary.groups())
    if rows != manifest["rows"] or comparisons <= 0 or transfers <= 0:
        raise RuntimeError("Simulation comparison/transaction conservation failure")
    observed = {}
    for identifier, compared, transferred in re.findall(r"COVER (\d+) comparisons=(\d+) transfers=(\d+)", text):
        identifier = int(identifier)
        if identifier in observed:
            raise RuntimeError(f"Duplicate case result {identifier}")
        observed[identifier] = (int(compared), int(transferred))
    required = {case["id"] for case in manifest["cases"]}
    if set(observed) != required:
        raise RuntimeError(f"Missing/extraneous observed coverage: {required ^ set(observed)}")
    coverage = []
    for case in manifest["cases"]:
        compared, transferred = observed[case["id"]]
        if compared < case["minimum_comparisons"]:
            raise RuntimeError(f"Unobserved required comparison: {case['bin']}")
        coverage.append(case | {"observed_comparisons": compared, "observed_transfers": transferred})
    write_json(folder / "coverage.json", coverage)
    ex.results.append({"kind": "behavior", "name": stem, "simulator": simulator,
                       "partial": manifest["partial"], "capacity": manifest["capacity"],
                       "rows": rows, "cycles": cycles, "comparisons": comparisons,
                       "transfers": transfers, "stalls": stalls, "resets": resets,
                       "coverage_bins_observed": len(coverage), "status": "passed",
                       "receipt": relative(folder / "receipt.json"),
                       "coverage": relative(folder / "coverage.json")})
    return text


def generate(ex, stem, generator, *args):
    folder = ex.directory(stem + "-vectors")
    path = folder / "vectors.txt"
    manifest = generator(path, *args)
    write_json(folder / "manifest.json", manifest)
    return path, manifest


def static_check(ex):
    stripped = {}
    for source in rtl_sources():
        text = source.read_text()
        text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)
        text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
        stripped[source.name] = text
        if re.search(r"(?<![/])[/%%](?![/])", text):
            raise RuntimeError(f"Forbidden division/remainder operator: {relative(source)}")
        # Loop induction variables are elaboration/control counters, not sequential state.
        for match in re.finditer(r"always\s*@\s*\(\s*posedge\b", text):
            tail = text[match.start():]
            nesting = 0
            finish = None
            for token in re.finditer(r"\bbegin\b|\bend\b", tail):
                nesting += 1 if token.group() == "begin" else -1
                if nesting == 0:
                    finish = token.end()
                    break
            if finish is None:
                raise RuntimeError(f"Unparsed sequential block: {relative(source)}")
            block = tail[:finish]
            block = re.sub(r"for\s*\([^)]*\)", "", block)
            if re.search(r"\b[\w]+(?:\[[^;\n]*?\])?\s*=(?!=)", block):
                raise RuntimeError(f"Blocking state assignment in sequential block: {relative(source)}")
    top = stripped["rivet_h4_top.sv"]
    for module, instance in (("rivet_h3_top", "u_legacy"), ("rivet_h4_sponge", "u_sponge"),
                             ("rivet_h4_merkle", "u_merkle")):
        if not re.search(rf"\b{module}\b(?:\s*#\s*\(.*?\))?\s+{instance}\s*\(", top, re.S):
            raise RuntimeError(f"Missing required literal hierarchy: {module} {instance}")
    for forbidden in ("/data/", "/home/", "JTAG_CABLE", "PCI_BDF"):
        for pattern in ("tests/*", "design/*.md"):
            for path in ROOT.glob(pattern):
                if path.is_file() and forbidden in path.read_text(errors="replace") and path.name != "verify.py":
                    raise RuntimeError(f"Nonportable shipped path/device: {relative(path)}")
    ex.results.append({"kind": "static", "status": "passed", "rtl_files": len(stripped),
                       "division_remainder_operators": 0, "blocking_sequential_state_assignments": 0})


def permutation_check(ex, simulator):
    folder = ex.directory("permutation-vectors")
    path = folder / "vectors.txt"
    count = vectors.permutation_vectors(path)
    binary = compile_sim(ex, 0, 3, simulator, leaf=True, stem="keccak-" + simulator)
    argv = ["vvp", relative(binary)] if simulator == "icarus" else [relative(binary)]
    text, record_folder = ex.run(argv + ["+vectors=" + relative(path)], "keccak-" + simulator,
                                 extra_sources=(path,), timeout=600 if simulator == "icarus" else 3600)
    if f"permutation_comparisons={count} latency=96 clear_priority=1" not in text:
        raise RuntimeError("Permutation numerical/latency/clear coverage not observed")
    clean_intermediates(binary)
    ex.results.append({"kind": "permutation", "simulator": simulator, "states": count,
                       "latency_cycles": 96, "status": "passed",
                       "receipt": relative(record_folder / "receipt.json")})


def illegal_parameters(ex):
    for partial, capacity in ((-1, 3), (2, 3), (0, 0), (0, 4097)):
        # Legal sized diagnostic shell; either explicit elaboration rejection or $fatal is allowed.
        folder = ex.directory(f"illegal-p{partial}-m{capacity}")
        binary = folder / "illegal.vvp"
        argv = ["iverilog", "-g2012", "-Wall", "-s", "bridge", f"-DPB={partial}",
                f"-DPAGE_CAP={capacity}", "-o", relative(binary),
                *map(relative, rtl_sources()), "tests/bridge.sv"]
        ex.run(argv, "illegal-compile")
        _, record = ex.run(["vvp", relative(binary)], "illegal-rejection",
                           expected_failure="PARAMETER ERROR", timeout=600)
        ex.results.append({"kind": "parameter-rejection", "partial": partial,
                           "capacity": capacity, "status": "rejected",
                           "receipt": relative(record / "receipt.json")})


def synthesis(ex, partial, capacity):
    folder = ex.directory(f"synthesis-p{partial}-m{capacity}")
    netlist = folder / "netlist.json"
    script = folder / "synthesis.ys"
    script.write_text("read_verilog -sv " + " ".join(map(relative, rtl_sources())) + "\n" +
                      f"chparam -set PARTIAL_BEATS {partial} -set MAX_PAGE_BYTES {capacity} rivet_h4_top\n" +
                      "hierarchy -check -top rivet_h4_top\n"
                      "proc\nopt_expr\nopt_clean\ncheck -assert\n"
                      "memory -nomap\nopt_clean\ncheck -assert\nstat\n" +
                      "write_json " + relative(netlist) + "\n")
    text, receipt_folder = ex.run(["yosys", "-Q", "-s", relative(script)],
                                  f"yosys-p{partial}-m{capacity}", extra_sources=(script,))
    if not netlist.is_file():
        raise RuntimeError("Yosys missing complete top netlist")
    modules = json.loads(netlist.read_text())["modules"]
    if "rivet_h4_top" not in modules:
        raise RuntimeError("Synthesized top is missing")
    latch_cells = 0
    memory_bits = 0
    total_sequential = 0
    for name, module in modules.items():
        if int(module.get("attributes", {}).get("blackbox", "0"), 2):
            raise RuntimeError(f"Black box in synthesized hierarchy: {name}")
        for cell in module.get("cells", {}).values():
            kind = cell["type"]
            if "latch" in kind.lower():
                latch_cells += 1
            if kind in ("$div", "$mod", "$divfloor", "$modfloor"):
                raise RuntimeError(f"Forbidden synthesized arithmetic cell: {kind}")
            if re.search(r"dff|ff$", kind, re.I):
                total_sequential += len(cell["connections"].get("Q", []))
            if kind.startswith("$mem"):
                parameters = cell["parameters"]
                if "WIDTH" in parameters and "SIZE" in parameters:
                    memory_bits += int(parameters["WIDTH"], 2) * int(parameters["SIZE"], 2)
            if not kind.startswith("$") and kind not in modules:
                raise RuntimeError(f"Unresolved live cell: {kind}")
    if latch_cells or total_sequential < 10000:
        raise RuntimeError(f"Latch/state failure: latches={latch_cells}, bits={total_sequential}")

    def sequential_bits(module_name, seen=None):
        seen = set() if seen is None else seen
        if module_name in seen:
            raise RuntimeError("Recursive synthesized hierarchy")
        module = modules[module_name]
        bits = 0
        for cell in module.get("cells", {}).values():
            kind = cell["type"]
            if re.search(r"dff|ff$", kind, re.I):
                bits += len(cell["connections"].get("Q", []))
            if kind in modules:
                bits += sequential_bits(kind, seen | {module_name})
        return bits

    top_cells = modules["rivet_h4_top"]["cells"]
    branch_bits = {}
    for instance in ("u_legacy", "u_sponge", "u_merkle"):
        if instance not in top_cells:
            raise RuntimeError(f"Removed required live branch: {instance}")
        cell = top_cells[instance]
        if not any(isinstance(bit, int) for bits in cell["connections"].values() for bit in bits):
            raise RuntimeError(f"Disconnected branch: {instance}")
        branch_bits[instance] = sequential_bits(cell["type"])
        if branch_bits[instance] < {"u_legacy": 10000, "u_sponge": 4000, "u_merkle": 1000}[instance]:
            raise RuntimeError(f"Trivial sequential state in {instance}")
    # Verify the quarantined page specifically, not an unrelated schedule RAM.
    merkle_module = modules[top_cells["u_merkle"]["type"]]
    page_memory = [cell for name, cell in merkle_module["cells"].items()
                   if cell["type"].startswith("$mem") and "page_ram" in name]
    expected_bits = ((capacity + 3) // 4) * 32
    page_bits = sum(int(c["parameters"]["WIDTH"], 2) * int(c["parameters"]["SIZE"], 2)
                    for c in page_memory if "WIDTH" in c["parameters"] and "SIZE" in c["parameters"])
    if page_bits != expected_bits:
        raise RuntimeError(f"Page RAM inference failed: expected={expected_bits}, actual={page_bits}")
    if "Warning: Wire" in text or re.search(r"found and reported \d+ problems", text):
        raise RuntimeError("Synthesis connectivity diagnostics")
    ex.results.append({"kind": "synthesis", "partial": partial, "capacity": capacity,
                       "status": "passed", "latch_cells": latch_cells,
                       "sequential_bits": total_sequential, "branch_bits": branch_bits,
                       "memory_bits": memory_bits, "page_ram_bits": page_bits,
                       "receipt": relative(receipt_folder / "receipt.json"),
                       "netlist": relative(netlist)})


MUTATIONS = (
    ("round-constant", "rivet_h4_keccak.sv", "64'h0000000000000001;", "64'h0000000000000003;", "SPONGE_NUMERICAL"),
    ("suffix", "rivet_h4_sponge.sv", "x_alg[1] ? 8'h1f : 8'h06", "x_alg[1] ? 8'h06 : 8'h1f", "SPONGE_NUMERICAL"),
    ("squeeze", "rivet_h4_sponge.sv", "else if (position == rate) begin",
     "else if (position == rate) begin\n                            sponge_state <= 1600'd0;", "SPONGE_NUMERICAL"),
    ("sibling-order", "rivet_h4_merkle.sv", "if (index_shift[0])", "if (!index_shift[0])", "MERKLE_VERDICT"),
    ("root-decision", "rivet_h4_merkle.sv", "if (&equal_words)", "if (1'b1)", "MERKLE_VERDICT"),
    ("release-gate", "rivet_h4_merkle.sv",
     "assign tile_valid = rst_n && release_eligible && (state == REPLAY_SEND);",
     "assign tile_valid = rst_n && ((release_eligible && (state == REPLAY_SEND)) || (state == PAGE));",
     "AUTH_RELEASE"),
)


def mutations(ex, baseline=None):
    if baseline is None:
        baseline = compile_sim(ex, 0, 3, "verilator", stem="mutation-baseline")
    for name, filename, original, replacement, mismatch in MUTATIONS:
        folder = ex.directory("mutant-" + name)
        for source in rtl_sources():
            shutil.copyfile(source, folder / source.name)
        target = folder / filename
        text = target.read_text()
        if text.count(original) != 1:
            raise RuntimeError(f"Mutation anchor ambiguous/absent: {name}")
        target.write_text(text.replace(original, replacement, 1))
        write_json(folder / "mutation.json", {"name": name, "baseline_sha256": ex.hashes,
                                             "mutant_sha256": {p.name: sha(p) for p in rtl_sources(folder)},
                                             "file": filename, "original": original,
                                             "replacement": replacement, "intended_mismatch": mismatch})
        path, manifest = generate(ex, name, vectors.mutation_vectors, name)
        # Prove the identical checker/vector accepts baseline before counting mutant detection.
        simulate(ex, baseline, path, manifest, stem=name + "-valid-baseline")
        clean_intermediates(baseline)
        binary = compile_sim(ex, 0, 3, "verilator", source_folder=folder, stem=name + "-mutant")
        simulate(ex, binary, path, manifest, stem=name + "-mutant-rejection", expected_failure=mismatch)
        clean_intermediates(binary)


def compact(ex, parent=True):
    binaries = {}
    permutation_check(ex, "icarus")
    for partial in (0, 1):
        path, manifest = generate(ex, f"smoke-p{partial}", vectors.smoke, partial, 3)
        for simulator in ("icarus", "verilator"):
            binary = compile_sim(ex, partial, 3, simulator, stem=f"smoke-{simulator}-p{partial}")
            simulate(ex, binary, path, manifest, simulator, f"smoke-{simulator}-p{partial}")
            clean_intermediates(binary)
            if simulator == "verilator":
                binaries[(partial, 3)] = binary
        if parent:
            path, manifest = generate(ex, f"parent-trace-p{partial}", vectors.smoke, partial, 3, True)
            observed = []
            for use_parent in (True, False):
                binary = compile_sim(ex, partial, 3, "icarus", parent=use_parent,
                                     stem=f"compatibility-{use_parent}-p{partial}")
                text = simulate(ex, binary, path, manifest, "icarus", f"compatibility-{use_parent}-p{partial}")
                observed.append(re.findall(r"^OBS .+$", text, re.M))
            if observed[0] != observed[1]:
                raise RuntimeError("Unmodified parent/H4 compact public result/context trace mismatch")
            ex.results.append({"kind": "parent-compatibility", "partial": partial,
                               "observed_trace_records": len(observed[0]), "status": "passed"})
    return binaries


def complete(ex):
    binaries = compact(ex)
    permutation_check(ex, "verilator")
    illegal_parameters(ex)
    for partial in (0, 1):
        binary = compile_sim(ex, partial, 4096, "verilator", stem=f"full-p{partial}-m4096")
        for name, generator, args in (
            ("sponge-matrix", vectors.sponge_matrix, (partial,)),
            ("sponge-protocol", vectors.sponge_protocol, (partial,)),
            ("legacy-matrix", vectors.legacy_matrix, (partial,)),
            ("merkle-matrix", vectors.merkle_matrix, (partial, 4096)),
        ):
            path, manifest = generate(ex, name, generator, *args)
            simulate(ex, binary, path, manifest, stem=f"{name}-p{partial}-m4096")
        for seed in vectors.SEEDS:
            path, manifest = generate(ex, "merkle-protocol", vectors.merkle_protocol, partial, 4096, seed)
            simulate(ex, binary, path, manifest, stem=f"merkle-protocol-p{partial}-m4096-seed{seed}")
        clean_intermediates(binary)
        for capacity in (1, 3):
            binary = binaries.get((partial, capacity))
            if binary is None:
                binary = compile_sim(ex, partial, capacity, "verilator", stem=f"boundary-p{partial}-m{capacity}")
            path, manifest = generate(ex, "merkle-matrix", vectors.merkle_matrix, partial, capacity)
            simulate(ex, binary, path, manifest, stem=f"merkle-matrix-p{partial}-m{capacity}")
            for seed in vectors.SEEDS:
                path, manifest = generate(ex, "merkle-protocol", vectors.merkle_protocol, partial, capacity, seed)
                simulate(ex, binary, path, manifest, stem=f"merkle-protocol-p{partial}-m{capacity}-seed{seed}")
            clean_intermediates(binary)
        for capacity in (1, 3, 4096):
            synthesis(ex, partial, capacity)
    mutations(ex, binaries[(0, 3)])
    reproduction(ex)


def reproduction(ex):
    folder = ex.directory("clean-reproduction")
    # A fresh ordinary temporary directory tests the shipped relative command/input set.
    with tempfile.TemporaryDirectory(prefix="rivet-h4-reproduction-") as temporary:
        copied = Path(temporary)
        for source in project_sources():
            target = copied / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        copied_hashes = {str(p.relative_to(copied)): sha(p)
                         for pattern in SOURCE_PATTERNS for p in copied.glob(pattern) if p.is_file()}
        if copied_hashes != ex.hashes:
            raise RuntimeError("Clean reproduction source bindings differ")
        text, record = ex.run(["python3", "tests/verify.py", "--suite", "compact",
                               "--output-root", "evidence/reproduction"], "clean-reproduction",
                              cwd=copied)
        summaries = list((copied / "evidence").glob("reproduction-*/summary.json"))
        if len(summaries) != 1 or json.loads(summaries[0].read_text())["status"] != "passed":
            raise RuntimeError("Clean reproduction did not execute/accept its compact comparisons")
        shutil.copytree(summaries[0].parent, folder / ("retained-" + stamp()))
        ex.results.append({"kind": "clean-reproduction", "status": "passed",
                           "source_sha256": copied_hashes,
                           "receipt": relative(record / "receipt.json"),
                           "retained_artifacts": relative(folder)})


def main():
    os.chdir(ROOT)
    ex = Execution(Path(ARGS.output_root), ARGS.repair_of)
    try:
        ex.tools()
        reference.self_check()
        static_check(ex)
        if ARGS.suite == "all":
            complete(ex)
        elif ARGS.suite == "compact":
            compact(ex)
        elif ARGS.suite == "diagnostic":
            binary = compile_sim(ex, ARGS.partial, ARGS.capacity, "verilator", stem="diagnostic")
            generators = {"legacy": vectors.legacy_matrix, "sponge": vectors.sponge_protocol,
                          "sponge-matrix": vectors.sponge_matrix,
                          "merkle": vectors.merkle_protocol, "merkle-matrix": vectors.merkle_matrix}
            generator = generators[ARGS.focus]
            args = (ARGS.partial, ARGS.capacity) if ARGS.focus.startswith("merkle") else (ARGS.partial,)
            path, manifest = generate(ex, ARGS.focus, generator, *args)
            simulate(ex, binary, path, manifest, stem="diagnostic-" + ARGS.focus)
            clean_intermediates(binary)
        elif ARGS.suite == "synthesis":
            synthesis(ex, ARGS.partial, ARGS.capacity)
        elif ARGS.suite == "sensitivity":
            mutations(ex)
        else:
            raise RuntimeError("Unknown suite")
        return 0 if ex.finish("passed") else 1
    except Exception as error:
        traceback.print_exc()
        ex.finish("failed", str(error))
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("all", "compact", "diagnostic", "synthesis", "sensitivity"), default="all")
    parser.add_argument("--output-root", default="evidence/l1")
    parser.add_argument("--repair-of")
    parser.add_argument("--partial", type=int, choices=(0, 1), default=0)
    parser.add_argument("--capacity", type=int, default=3)
    parser.add_argument("--focus", choices=("legacy", "sponge", "sponge-matrix", "merkle", "merkle-matrix"), default="merkle")
    ARGS = parser.parse_args()
    sys.exit(main())
