#!/usr/bin/env python3
"""RIVET-H1 executable acceptance.

behavior: published/hashlib/FIPS comparisons, protocol, arithmetic and cycles.
sensitivity: three executing, independent semantic mutants and pristine controls.
synthesis: real Yosys hierarchy, process/memory lowering, synth and check -assert.
portable: declared-source-only fresh-directory child smoke execution.
smoke: bounded public transaction, internal-reference, stall and reset checks.

All suites fail closed, preserve raw children and never modify deliverable RTL.
Run from the delivered project root; no third-party Python packages are needed.
"""
import argparse
import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import LENGTH, TOP
from model import PUBLISHED, reference

BOUNDARIES = [0, 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 54, 55, 56, 57,
              62, 63, 64, 65, 119, 120, 127, 128, 129]
LONG = [4097, 8191, 8192, 8193, 16384, 32768, 65535, 65536]
SEEDS = [11, 29, 89]
RTL = [Path("rtl") / (n + ".sv") for n in (
    "rivet_h1_top", "rivet_h1_length", "rivet_h1_pad",
    "rivet_h1_compress", "rivet_h1_schedule",
)]
DOCS = [Path("design/SPEC.md"), Path("design/ARCHITECTURE.md")]
TIMEOUT = 86400


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    return RTL + sorted(Path("tests").glob("*.py")) + DOCS


def inventory(paths):
    return {p.as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size,
                           "lines": len(p.read_bytes().splitlines())} for p in paths}


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Runner:
    def __init__(self, out):
        self.out = out
        self.versions = {"python3": sys.version}
        self.executions = []
        self.binding = inventory(sources())

    def run(self, name, argv, cwd=Path("."), allow_failure=False):
        folder = self.out / name
        folder.mkdir(parents=True, exist_ok=False)
        record = {
            "argv": [str(x) for x in argv], "cwd": cwd.as_posix(),
            "start": utc(), "timeout_s": TIMEOUT, "source_hashes": self.binding,
            "tool_versions": dict(self.versions), "stdout": (folder / "stdout.txt").as_posix(),
            "stderr": (folder / "stderr.txt").as_posix(),
        }
        execution_inputs = []
        for arg in record["argv"]:
            candidate = arg.split("=", 1)[1] if arg.startswith("+stimulus=") else arg
            path = cwd / candidate
            if path.is_file():
                execution_inputs.append(path)
        record["execution_input_hashes"] = inventory(execution_inputs)
        start = time.monotonic()
        process = None
        failure = None
        with (folder / "stdout.txt").open("wb") as stdout, (folder / "stderr.txt").open("wb") as stderr:
            try:
                process = subprocess.Popen(record["argv"], cwd=cwd, stdout=stdout,
                                           stderr=stderr, start_new_session=True)
                record["exit_code"] = process.wait(timeout=TIMEOUT)
                record["timed_out"] = False
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                record["exit_code"] = process.wait()
                record["timed_out"] = True
                failure = "bounded child timed out"
            except OSError as exc:
                record["exit_code"] = None
                record["timed_out"] = False
                record["launch_error"] = str(exc)
                failure = str(exc)
        record.update(end=utc(), elapsed_s=time.monotonic() - start,
                      settled=process is None or process.poll() is not None)
        write_json(folder / "receipt.json", record)
        self.executions.append((folder / "receipt.json").as_posix())
        require(record["settled"] and not record["timed_out"] and not failure,
                f"{name}: tool execution failed; see {folder}/receipt.json")
        if not allow_failure:
            require(record["exit_code"] == 0, f"{name}: exit {record['exit_code']}; see {folder}")
        return (folder / "stdout.txt").read_text(), record

    def version(self, tool, flag):
        text, record = self.run("version-" + tool, [tool, flag])
        err = Path(record["stderr"]).read_text()
        self.versions[tool] = (text + err).strip()


def pattern(n):
    return bytes((i * 73 + (i >> 3) * 19 + 0xA5) & 255 for i in range(n))


def case(data, label, *, mode=0, stall=0, detail=False, seed=0, group=None):
    return dict(data=data, label=label, mode=mode, stall=stall, detail=detail,
                seed=seed, group=group)


def matrix(full, selected_seed=None):
    result = []
    # Independently computed reference must agree even for the million-byte vector.
    for i, (data, expected) in enumerate(PUBLISHED if full else PUBLISHED[:2]):
        digest, _ = reference(data)
        require(digest == expected, f"published reference vector {i}")
        result.append(case(data, f"published-{i}", detail=len(data) < 1000))
    for n in BOUNDARIES if full else [55, 56, 63, 64, 65, 129]:
        result.append(case(pattern(n), f"boundary-{n}", detail=True))
    if full:
        result += [case(bytes([n]), f"byte-{n}") for n in range(256)]
        result += [case(pattern(n), f"long-{n}", detail=n == 4097) for n in LONG]
        for seed in [selected_seed] if selected_seed is not None else SEEDS:
            rng = random.Random(seed)
            # The first 64 lengths explicitly cover every residue; the next 64
            # explore the full range including zero and the upper endpoint.
            lengths = [64 * rng.randrange(64) + residue for residue in range(64)]
            lengths += [0, 4096] + [rng.randrange(4097) for _ in range(62)]
            require(set(n % 64 for n in lengths) == set(range(64)), "random residue coverage")
            for j, n in enumerate(lengths):
                result.append(case(rng.randbytes(n), f"random-{seed}-{j}", mode=2,
                                   stall=rng.randrange(12), seed=seed * 1000 + j))
        # Always-valid/ready runs are consecutive, including across reservations.
        for n in [64, 1024]:
            result += [case(pattern(n), f"sustained-{n}-{i}", group=f"sustained-{n}")
                       for i in range(100)]
    # Replays are traffic coverage, not additional unique messages.
    for n in [0, 1, 2, 3, 4, 55, 56, 63, 64, 65, 129]:
        result.append(case(pattern(n), f"traffic-{n}", mode=2, stall=256,
                           seed=89 + n, detail=n == 129))
    result.append(case(b"abcdefg", "paused-input", mode=2, stall=7, detail=True))
    return result


def stimulus(path, cases):
    metadata = []
    with path.open("w") as f:
        for ident, item in enumerate(cases):
            data = item["data"]
            rng = random.Random(item["seed"])
            digest = hashlib.sha256(data).hexdigest()
            nbeats = max(1, (len(data) + 3) // 4)
            f.write(f"{ident} {len(data)} {nbeats} {item['mode']} {item['stall']} "
                    f"{int(item['detail'])} {digest}\n")
            for i in range(nbeats):
                part = data[4 * i:4 * i + 4]
                last = i == nbeats - 1
                word = part + rng.randbytes(4 - len(part))
                keep = (15 << (4 - len(part))) & 15 if part else 0
                gap = rng.randrange(4) if item["mode"] else 0
                if item["label"] == "paused-input":
                    gap = 300
                f.write(f"{int.from_bytes(word, 'big'):08x} {keep} {int(last)} {gap}\n")
            metadata.append({k: v for k, v in item.items() if k != "data"} |
                            {"id": ident, "length": len(data), "sha256": digest})
    write_json(path.with_suffix(".json"), {
        "transactions": metadata, "stimulus_sha256": sha(path),
        "random_algorithm": "Python random.Random / MT19937",
        "ignored_final_lanes": "independently randomized",
    })
    return metadata


def parse_sim(text, cases, allow_mismatch=False, protocol=False):
    digests, times, details = {}, {}, {}
    end = None
    p = None
    for line in text.splitlines():
        if line.startswith("D "):
            fields = line.split()
            require(len(fields) == 3 and re.fullmatch("[0-9a-f]{64}", fields[2]) is not None,
                    "malformed/unknown digest record")
            ident = int(fields[1])
            require(ident not in digests, "extra/duplicate digest")
            digests[ident] = fields[2]
        elif line.startswith("T "):
            fields = list(map(int, line.split()[1:]))
            require(len(fields) == 9 and fields[0] not in times, "malformed/duplicate timing")
            times[fields[0]] = fields[1:]
        elif line.startswith(("B ", "W ", "C ")):
            fields = line.split()
            kind, ident, block = fields[0], int(fields[1]), int(fields[2])
            entry = details.setdefault((ident, block), {"schedule": []})
            if kind == "B":
                require(len(fields) == 6 and "block" not in entry, "duplicate/malformed block")
                entry.update(launch=int(fields[3]), block=fields[4], incoming=fields[5])
            elif kind == "W":
                require(len(fields) == 5 and int(fields[3]) == len(entry["schedule"]),
                        "missing/extra/out-of-order round")
                entry["schedule"].append(int(fields[4], 16))
            else:
                require(len(fields) == 5 and "outgoing" not in entry, "duplicate/malformed completion")
                entry.update(completion=int(fields[3]), outgoing=fields[4])
        elif line.startswith("END "):
            require(end is None, "duplicate END")
            end = list(map(int, line.split()[1:]))
        elif line.startswith("P "):
            require(p is None, "duplicate protocol")
            p = list(map(int, line.split()[1:]))
        elif line.startswith(("FATAL", "ERROR", "WARNING")):
            raise AssertionError("simulator diagnostic: " + line)
        elif line.startswith("$finish") or " $finish called at " in line:
            pass
        elif line.strip():
            raise AssertionError("unrecognized simulation output: " + line)
    require(end is not None and len(end) == 8 and end[0] == len(cases), "missing/truncated END")
    require(set(digests) == set(range(len(cases))) == set(times), "missing/extra transactions")
    mismatches = []
    bit_errors = 0
    ledger = []
    for ident, item in enumerate(cases):
        expected = hashlib.sha256(item["data"]).hexdigest()
        actual = digests[ident]
        if actual != expected:
            errors = (int(actual, 16) ^ int(expected, 16)).bit_count()
            bit_errors += errors
            mismatches.append({"id": ident, "label": item["label"],
                               "actual": actual, "expected": expected, "bit_mismatches": errors})
        first, final, valid, retire, stall, blocks, rounds, length = times[ident]
        n = len(item["data"])
        require(length == n and first <= final < valid < retire, "invalid timing interval")
        latency = 135 if n % 64 >= 56 or (n > 0 and n % 64 == 0) else 68
        require(valid - final == latency and retire - valid - 1 == stall == item["stall"],
                "latency/stall mismatch")
        require(blocks == (n + 72) // 64 and rounds == 64 * blocks, "blocks/rounds mismatch")
        ledger.append(dict(id=ident, label=item["label"], first_input=first, final_input=final,
                           first_valid=valid, retirement=retire, output_stall_cycles=stall,
                           blocks=blocks, rounds=rounds, message_bytes=n,
                           final_to_valid_cycles=valid-final, first_to_valid_cycles=valid-first,
                           elapsed_inclusive_cycles=retire-first+1))
        if item["detail"] and not allow_mismatch:
            _, expected_detail = reference(item["data"], detail=True)
            require({b for i, b in details if i == ident} == set(range(len(expected_detail))),
                    "missing/extra reference block")
            for block, ref in enumerate(expected_detail):
                observed = details[(ident, block)]
                for key in ["block", "incoming", "schedule", "outgoing"]:
                    require(observed.get(key) == ref[key], f"FIPS boundary {ident}/{block}/{key}")
                require(observed["completion"] - observed["launch"] == 65, "compression cycles")
    expected_detail_keys = {(i, b) for i, c in enumerate(cases) if c["detail"]
                            for b in range((len(c["data"]) + 72) // 64)}
    require(set(details) == expected_detail_keys, "unexpected/missing detailed trace")
    require(end[5] >= 2, "reset checks absent")
    if protocol:
        require(p == [31, 10, 258, 1, 3], f"protocol coverage missing: {p}")
        require(end[6] >= 10, "asynchronous cancellation absent")
    require(allow_mismatch or not mismatches, f"digest mismatch: {mismatches[:1]}")
    return {
        "transactions": len(cases), "unique_messages": len({c["data"] for c in cases}),
        "digest_mismatches": len(mismatches), "digest_bit_mismatches": bit_errors,
        "missing_outputs": 0, "extra_outputs": 0, "mismatches": mismatches,
        "transaction_ledger": ledger, "observed_reference_blocks": len(details),
        "compression_blocks_including_protocol_and_canceled": end[1],
        "round_update_edges_including_protocol_and_canceled": end[2],
        "completed_blocks_including_protocol": end[3], "total_elapsed_cycles": end[4],
        "reset_observations": end[5], "asynchronous_resets": end[6],
        "public_output_handshakes_including_recovery": end[7],
        "protocol_coverage": p,
        "protocol_coverage_fields": [
            "sticky_fault_and_recovery_cases", "reset_cancellation_phases",
            "continuous_next_valid_output_stall_cycles",
            "coincident_retirement_without_input_acceptance",
            "reset_priority_input_illegal_input_output",
        ],
        "checker_verdict": "rejected-digest-mismatch" if mismatches else "accepted",
    }


def simulate(runner, name, cases, rtl=None, protocol=False, allow_mismatch=False):
    rtl = rtl or RTL
    directory = runner.out / name
    directory.mkdir()
    tb = directory / "tb.sv"
    tb.write_text(TOP)
    stim = directory / "stimulus.txt"
    stimulus(stim, cases)
    image = directory / "simulation.vvp"
    runner.run(name + "-compile", ["iverilog", "-g2012", "-Wall", "-s", "tb",
                                   "-o", image, tb, *rtl])
    text, _ = runner.run(name + "-execute", ["vvp", image, f"+stimulus={stim}",
                                             f"+protocol={int(protocol)}"])
    result = parse_sim(text, cases, allow_mismatch=allow_mismatch, protocol=protocol)
    write_json(directory / "result.json", result)
    return result


def arithmetic(runner):
    path = runner.out / "length.sv"
    path.write_text(LENGTH)
    image = runner.out / "length.vvp"
    runner.run("length-compile", ["iverilog", "-g2012", "-Wall", "-s", "tb",
                                "-o", image, path, RTL[1]])
    text, _ = runner.run("length-execute", ["vvp", image])
    records = []
    seen = set()
    for line in text.splitlines():
        if line.startswith("A "):
            fields = line.split()
            require(len(fields) == 7, "malformed arithmetic record")
            base, n, accept, clear, proposed, observed = (
                int(fields[1], 16), int(fields[2]), int(fields[3]), int(fields[4]),
                int(fields[5], 16), int(fields[6], 16))
            require((base, n, accept, clear) not in seen, "duplicate arithmetic record")
            seen.add((base, n, accept, clear))
            expected = 0 if clear else base + n if accept and base+n <= 2**61-1 else base
            require(proposed == base + n and observed == expected, "arithmetic reference mismatch")
            records.append(dict(base=base, bytes=n, accept=accept, clear=clear,
                                proposed=proposed, observed=observed))
        elif line.startswith("LEND "):
            require(line == "LEND 135", "length comparison count")
        elif line.startswith("$finish") or " $finish called at " in line:
            pass
        elif line.strip():
            raise AssertionError("unexpected length trace: " + line)
    require(len(records) == 135 and "LEND 135" in text, "incomplete length coverage")
    write_json(runner.out / "arithmetic.json", {
        "scope": "state-seeded length arithmetic, NOT end-to-end near-limit hashing",
        "comparisons": len(records), "records": records,
    })
    return len(records)


def behavior(runner, full, selected_seed):
    cases = matrix(full, selected_seed)
    result = simulate(runner, "messages", cases, protocol=True)
    result["arithmetic_comparisons"] = arithmetic(runner)
    result["scope"] = "full" if full else "bounded smoke, not full acceptance"
    result["source_inventory"] = runner.binding
    result["rtl_module_count"] = sum(
        len(re.findall(r"^\s*module\s+", p.read_text(), flags=re.MULTILINE)) for p in RTL)
    require(result["rtl_module_count"] == 5, "module count")
    result["source_size_totals"] = {
        kind: {"bytes": sum(runner.binding[p.as_posix()]["bytes"] for p in paths),
               "lines": sum(runner.binding[p.as_posix()]["lines"] for p in paths)}
        for kind, paths in [("rtl", RTL), ("verification", sorted(Path("tests").glob("*.py")))]
    }
    result["published_vectors_executed"] = len(PUBLISHED) if full else 2
    result["random_coverage"] = {}
    if full:
        for seed in [selected_seed] if selected_seed is not None else SEEDS:
            chosen = [c for c in cases if c["label"].startswith(f"random-{seed}-")]
            require(len(chosen) >= 128, "random threshold")
            residues = sorted({len(c["data"]) % 64 for c in chosen})
            require(residues == list(range(64)), "random residue threshold")
            result["random_coverage"][str(seed)] = {"transactions": len(chosen), "residues": residues}
        result["sustained"] = {}
        for n in [64, 1024]:
            entries = [result["transaction_ledger"][i] for i, c in enumerate(cases)
                       if c["group"] == f"sustained-{n}"]
            require(len(entries) == 100, "sustained threshold")
            for a, b in zip(entries, entries[1:]):
                require(b["first_input"] == a["retirement"] + 1, "externally gapped sustained run")
            cycles = entries[-1]["retirement"] - entries[0]["first_input"] + 1
            result["sustained"][str(n)] = {
                "messages": len(entries), "payload_bytes": n * len(entries),
                "inclusive_cycles": cycles, "cycles_per_message": cycles / len(entries),
                "payload_bytes_per_cycle": n * len(entries) / cycles,
                "first_input": entries[0]["first_input"], "last_retirement": entries[-1]["retirement"],
                "interval_definition": "first accepted input through last output handshake inclusive",
                "external_input_gaps": 0, "external_output_stalls": 0,
            }
    return result


def sensitivity(runner):
    pristine = {p: p.read_bytes() for p in RTL}
    experiments = [
        ("padding-length", "rivet_h1_pad.sv", "block_data[63:0] <= bit_length;",
         "block_data[63:0] <= bit_length ^ 64'd8;", b"abc"),
        ("schedule-rotation", "rivet_h1_schedule.sv",
         "{words[1][6:0], words[1][31:7]}",
         "{words[1][7:0], words[1][31:8]}", pattern(55)),
        ("interblock-chain", "rivet_h1_top.sv",
         ".block_data(block_data), .state_in(chain_state),",
         ".block_data(block_data), .state_in(INITIAL_STATE),", pattern(65)),
    ]
    results = []
    for name, filename, original, changed, data in experiments:
        witnesses = [case(data, name + "-witness")]
        control = simulate(runner, name + "-control", witnesses)
        directory = runner.out / (name + "-mutant")
        directory.mkdir()
        mutant_paths = []
        differences = []
        for path in RTL:
            target = directory / path.name
            text = pristine[path].decode()
            if path.name == filename:
                require(text.count(original) == 1, "mutation site absent/ambiguous")
                mutated = text.replace(original, changed)
                differences.extend(difflib.unified_diff(text.splitlines(True),
                                   mutated.splitlines(True), fromfile=path.as_posix(),
                                   tofile=(Path("mutant") / path.name).as_posix()))
            else:
                mutated = text
            target.write_text(mutated)
            mutant_paths.append(target)
        (directory / "mutation.diff").write_text("".join(differences))
        outcome = simulate(runner, name + "-witness", witnesses, rtl=mutant_paths,
                           allow_mismatch=True)
        require(outcome["digest_mismatches"] == 1, f"semantic mutation not detected: {name}")
        require(all(p.read_bytes() == data for p, data in pristine.items()), "deliverable RTL modified")
        results.append({
            "name": name, "detected_by": "observed digest mismatch after successful compile/execution",
            "control_mismatches": control["digest_mismatches"],
            "first_mismatch": outcome["mismatches"][0],
            "original_sources": {p.as_posix(): sha(p) for p in RTL},
            "mutated_sources": {p.as_posix(): sha(p) for p in mutant_paths},
            "diff": (directory / "mutation.diff").as_posix(),
        })
    return {"semantic_mutants": 3, "detected": len(results), "experiments": results}


def inspect_netlist(path, hierarchy=False):
    netlist = json.loads(path.read_text())
    modules = netlist["modules"]
    require("rivet_h1_top" in modules, "missing synthesized top")
    all_cells = [c for m in modules.values() for c in m.get("cells", {}).values()]
    require(not any("latch" in c["type"].lower() for c in all_cells), "inferred latch")
    for name, module in modules.items():
        require(not int(module.get("attributes", {}).get("blackbox", "0"), 2),
                f"unresolved blackbox: {name}")
    if hierarchy:
        expected = {
            "rivet_h1_top": {"u_length": "rivet_h1_length", "u_pad": "rivet_h1_pad",
                             "u_compress": "rivet_h1_compress"},
            "rivet_h1_compress": {"u_schedule": "rivet_h1_schedule"},
        }
        require(set(modules) == {p.stem for p in RTL}, "literal functional module inventory")
        for parent, children in expected.items():
            cells = modules[parent]["cells"]
            for instance, kind in children.items():
                require(instance in cells and cells[instance]["type"].lstrip("\\") == kind,
                        f"missing functional hierarchy {parent}/{instance}")
        for name, module in modules.items():
            seq = [c for c in module["cells"].values() if "dff" in c["type"].lower()]
            require(seq, f"no substantive sequential state in {name}")
    sequential = [c for c in all_cells if "dff" in c["type"].lower()]
    require(len(all_cells) > 100 and len(sequential) >= 10, "empty/trivial optimized design")
    counts = {}
    for c in all_cells:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    return {"modules": len(modules), "generic_cells_across_module_definitions": len(all_cells),
            "sequential_cells": len(sequential), "latches": 0, "cell_types": counts}


def synthesis(runner):
    script = runner.out / "synthesis.ys"
    pre = runner.out / "pre.json"
    post = runner.out / "netlist.json"
    stats = runner.out / "stats.json"
    script.write_text(
        "read_verilog -sv " + " ".join(map(str, RTL)) + "\n"
        "hierarchy -check -top rivet_h1_top\n"
        "proc\nopt\nmemory\nopt\ncheck -assert\n"
        f"write_json {pre}\n"
        "synth -top rivet_h1_top\ncheck -assert\n"
        f"write_json {post}\n"
        f"tee -o {stats} stat -json\n")
    text, record = runner.run("yosys", ["yosys", "-s", script])
    require("0 problems" in text, "Yosys consistency results absent")
    before = inspect_netlist(pre, hierarchy=True)
    after = inspect_netlist(post)
    stat = json.loads(stats.read_text())
    require("modules" in stat and stat["modules"], "missing machine-readable synthesis stats")
    return {
        "before_synthesis": before, "after_generic_synthesis": after,
        "statistics": stats.as_posix(), "netlist": post.as_posix(),
        "scope": "generic synthesis only; NOT physical area, timing closure, FPGA or silicon security",
        "receipt": (runner.out / "yosys/receipt.json").as_posix(),
    }


def portable(runner):
    bundle = runner.out / "bundle"
    bundle.mkdir()
    copied = []
    for source in sources():
        dest = bundle / source
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        require(sha(dest) == sha(source), "portable copy differs")
        copied.append({"path": source.as_posix(), "sha256": sha(dest)})
    write_json(runner.out / "copied_inventory.json", copied)
    text, record = runner.run("child-smoke", [
        "python3", "tests/verify.py", "--suite", "smoke", "--out", "evidence/smoke",
    ], cwd=bundle)
    child_runs = list((bundle / "evidence/smoke").glob("run-*/result.json"))
    require(len(child_runs) == 1, "portable child results absent/ambiguous")
    child = json.loads(child_runs[0].read_text())
    require(child["status"] == "passed" and child["result"]["digest_mismatches"] == 0,
            "portable child failed comparisons")
    require(child["result"]["transactions"] >= 8 and
            child["result"]["protocol_coverage"] == [31, 10, 258, 1, 3],
            "portable smoke coverage")
    return {"copied_inventory": copied, "child_result": child_runs[0].as_posix(),
            "child_receipt": (runner.out / "child-smoke/receipt.json").as_posix(),
            "child_transactions": child["result"]["transactions"],
            "scope": "fresh declared-source-only smoke, not full matrix replay"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["behavior", "sensitivity", "synthesis", "portable", "smoke"],
                        required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, choices=SEEDS)
    parser.add_argument("--repair-of", help="project-relative prior failed preparation receipt")
    args = parser.parse_args()
    require(not args.out.is_absolute() and ".." not in args.out.parts, "--out must be project-relative")
    require(Path("tests/verify.py").is_file(), "run from delivered project root")
    root = args.out
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = root / ("run-" + stamp)
    out.mkdir()
    runner = Runner(out)
    started = utc()
    result = None
    error = None
    try:
        if args.suite == "synthesis":
            runner.version("yosys", "-V")
            result = synthesis(runner)
        elif args.suite == "portable":
            result = portable(runner)
        else:
            runner.version("iverilog", "-V")
            runner.version("vvp", "-V")
            result = (sensitivity(runner) if args.suite == "sensitivity" else
                      behavior(runner, args.suite == "behavior", args.seed))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    report = {
        "suite": args.suite, "status": "failed" if error else "passed",
        "error": error, "result": result, "source_inventory": runner.binding,
        "tool_versions": runner.versions, "execution_receipts": runner.executions,
        "start": started, "end": utc(), "repair_of": args.repair_of,
    }
    write_json(out / "result.json", report)
    # Each suite invocation has its own immutable receipt, including preparation.
    write_json(out / "receipt.json", {
        "argv": ["python3", "tests/verify.py", *sys.argv[1:]], "cwd": ".",
        "source_hashes": runner.binding, "tool_versions": runner.versions,
        "start": started, "end": report["end"], "timeout_s": TIMEOUT,
        "exit_code": 1 if error else 0, "timed_out": False,
        "child_receipts": runner.executions, "repair_of": args.repair_of,
        "stdout": (out / "stdout.txt").as_posix(), "stderr": (out / "stderr.txt").as_posix(),
    })
    output = json.dumps({"status": report["status"], "result": (out / "result.json").as_posix(),
                         "error": error})
    (out / "stdout.txt").write_text(output + "\n")
    (out / "stderr.txt").write_text((error + "\n") if error else "")
    print(output)
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
