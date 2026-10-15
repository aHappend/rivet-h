#!/usr/bin/env python3
"""RIVET-H3 independent execution entry point.

Requirements map: scenarios.py defines functional matrices; reference.py owns
cryptographic/context expectations; bridge.py checks only public pins.
Synthesis checks retained preflatten connectivity and generic lowered logic.
Every subprocess has a retained invocation receipt and raw logs. Preparation
uses a fresh evidence/preparation directory and is advisory, never acceptance.
Repeating an output path retains its contents and runs the entire check in a
fresh attempt subdirectory; interrupted runs never supply passing comparisons.
"""

import argparse
import collections
import datetime
import difflib
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bridge import testbench
import reference
import scenarios

ROOT = Path(__file__).resolve().parent.parent
SELECTORS = ("rtl/*.sv", "design/SPEC.md", "design/ARCHITECTURE.md",
             "tests/*.py", "rivet_h2_reference/rtl/*.sv")
CHECKS = ("behavior", "compatibility", "defects", "synthesis", "portable")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def relative(path):
    return str(path.resolve().relative_to(ROOT))


def sources():
    result = []
    for selector in SELECTORS:
        matches = sorted(ROOT.glob(selector))
        if not matches:
            raise RuntimeError(f"missing declared sources: {selector}")
        result.extend(matches)
    return result


def hashes():
    return {relative(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources()}


class Execution:
    def __init__(self, out, repair_of=None):
        requested_out = out
        if out.exists():
            if not out.is_dir() or out.is_symlink():
                raise ValueError("existing output must be a nonsymlink directory")
            out = out / ("attempt-" + uuid.uuid4().hex)
            if repair_of is None and (requested_out / "receipt.json").is_file():
                repair_of = relative(requested_out / "receipt.json")
        self.out = out
        out.mkdir(parents=True, exist_ok=False)
        self.identity = hashes()
        self.started = now()
        self.records = []
        self.versions = {}
        self.ledger = []
        self.summary = {"started_at": self.started, "source_sha256": self.identity,
                        "argv": sys.orig_argv, "cwd": relative(ROOT),
                        "requested_out": relative(requested_out),
                        "actual_out": relative(out),
                        "tools": self.versions, "runs": self.records,
                        "coverage_ledger": self.ledger, "status": "running"}
        if repair_of:
            self.summary["repair_of"] = repair_of
        write_json(out / "receipt.json", self.summary)

    def run(self, argv, name, cwd=ROOT, expected_exit=0, timeout=3600):
        if timeout < 3600:
            raise ValueError("functional/synthesis subprocess timeout must be >=3600")
        folder = self.out / name
        folder.mkdir(parents=True, exist_ok=False)
        rec = dict(argv=[str(x) for x in argv], cwd=relative(cwd),
                   started_at=now(), timeout_s=timeout, timeout=False,
                   status="running", exit=None,
                   stdout=relative(folder / "stdout.txt"),
                   stderr=relative(folder / "stderr.txt"),
                   source_sha256=self.identity, tool_versions=dict(self.versions))
        invoked_inputs = {}
        for arg in rec["argv"]:
            arg = arg.removeprefix("+PROGRAM=")
            path = cwd / arg
            try:
                is_file = path.is_file()
            except OSError as exc:
                if exc.errno != errno.ENAMETOOLONG:
                    raise
                # Inline command arguments need not be valid filesystem names.
                is_file = False
            if is_file:
                try:
                    label = relative(path)
                except ValueError:
                    # Tool executables are identified by version; don't hash host files.
                    continue
                invoked_inputs[label] = hashlib.sha256(path.read_bytes()).hexdigest()
        rec["invoked_input_sha256"] = invoked_inputs
        self.records.append(rec)
        write_json(folder / "receipt.json", rec)
        write_json(self.out / "receipt.json", self.summary)
        start = time.monotonic()
        try:
            with (folder / "stdout.txt").open("w") as stdout, (
                    folder / "stderr.txt").open("w") as stderr:
                proc = subprocess.run(rec["argv"], cwd=cwd, stdout=stdout,
                                      stderr=stderr, timeout=timeout, check=False)
                rec["exit"] = proc.returncode
        except subprocess.TimeoutExpired:
            rec.update(timeout=True, exit=None)
        except OSError as exc:
            rec.update(exit=None, infrastructure_error=str(exc))
        rec.update(status="finished", ended_at=now(), elapsed_s=time.monotonic() - start)
        write_json(folder / "receipt.json", rec)
        write_json(self.out / "receipt.json", self.summary)
        text = (folder / "stdout.txt").read_text() + (folder / "stderr.txt").read_text()
        if rec["timeout"] or rec.get("infrastructure_error"):
            raise RuntimeError(f"tool infrastructure failure: {relative(folder / 'receipt.json')}")
        if expected_exit is not None and rec["exit"] != expected_exit:
            raise RuntimeError(f"unexpected tool exit {rec['exit']}: "
                               f"{relative(folder / 'receipt.json')}\n{text[-4000:]}")
        return rec, text

    def prerequisites(self, tools):
        for tool in tools:
            if not shutil.which(tool):
                raise RuntimeError(f"missing prerequisite executable: {tool}")
            flag = "-V" if tool in ("iverilog", "vvp") else (
                "-V" if tool == "yosys" else "--version")
            _, version = self.run([tool, flag], f"version-{tool}")
            self.versions[tool] = version.strip()

    def finish(self, status, **extra):
        if status == "passed" and any(row["status"] != "passed" for row in self.ledger):
            raise AssertionError("cannot pass with incomplete planned run ledger")
        if status == "failed":
            for row in self.ledger:
                if row["status"] == "running":
                    row["status"] = "failed"
        self.summary.update(status=status, ended_at=now(), **extra)
        write_json(self.out / "receipt.json", self.summary)

    def case(self, name, status, **details):
        rows = [row for row in self.ledger if row["name"] == name]
        if not rows:
            row = dict(name=name)
            self.ledger.append(row)
        else:
            row = rows[0]
        row.update(status=status, **details)
        write_json(self.out / "receipt.json", self.summary)


def simulate(ex, name, build, partial=0, seed=17, standalone=False, rtl=None,
             rejection=None):
    ex.case(name, "running", partial_beats=partial, seed=seed,
            top="rivet_h2_top" if standalone else "rivet_h3_top")
    work = ex.out / name
    work.mkdir()
    tb = work / "tb.sv"
    tb.write_text(testbench(partial, standalone))
    program = scenarios.Program(work / "program.txt", partial, seed, standalone)
    build(program)
    manifest = program.close()
    write_json(work / "stimulus.json", manifest)
    executable = work / "sim.vvp"
    rtl = sorted((ROOT / "rtl").glob("*.sv")) if rtl is None else rtl
    ex.run(["iverilog", "-g2012", "-Wall", "-s", "tb", "-o", relative(executable),
            relative(tb)] + [relative(p) for p in rtl], f"{name}/compile")
    rec, text = ex.run(["vvp", relative(executable),
                        "+PROGRAM=" + relative(program.path)],
                       f"{name}/simulate", expected_exit=None)
    if rejection:
        if rec["exit"] == 0 or not re.search(rejection, text):
            raise AssertionError(f"mutant not functionally rejected ({rejection}): {name}")
        result = dict(status="functional_rejection", assertion=rejection,
                      execution=relative(work / "simulate/receipt.json"))
        write_json(work / "result.json", result)
        ex.case(name, "passed", actual="compiled functional rejection",
                assertion=rejection, receipt=result["execution"])
        return result
    if rec["exit"] != 0:
        raise AssertionError(f"simulation failure: {relative(work / 'simulate/receipt.json')}"
                             f"\n{text[-4000:]}")
    summaries = re.findall(r"^SUMMARY (.*)$", text, re.M)
    if len(summaries) != 1:
        raise AssertionError(f"missing unique completion marker: {name}")
    rows = [list(map(int, line.split())) for line in re.findall(r"^DIGEST (.*)$", text, re.M)]
    observed = [r[0] for r in rows]
    required = {m["id"]: m for m in manifest["messages"]
                if m["category"] != "reset_aborted_digest"}
    if len(observed) != len(set(observed)) or set(observed) != set(required):
        raise AssertionError(f"response conservation failure {name}: "
                             f"missing={set(required)-set(observed)} extra={set(observed)-set(required)}")
    coverage = collections.Counter(required[r[0]]["category"] for r in rows)
    check_names = {identifier: name for name, identifier in manifest["check_ids"].items()}
    checked_events = collections.Counter()
    for identifier in re.findall(r"^COVER (\d+) \d+$", text, re.M):
        if int(identifier) not in check_names:
            raise AssertionError("unknown functional coverage identifier")
        checked_events[check_names[int(identifier)]] += 1
    if checked_events != collections.Counter(manifest["required_checks"]):
        raise AssertionError(f"incomplete asserted-event coverage: {name}")
    planned = next(row for row in ex.ledger if row["name"] == name)
    if "required_comparisons" in planned and len(rows) != planned["required_comparisons"]:
        raise AssertionError(f"required comparison count not met: {name}")
    for category, floor in planned.get("required", {}).items():
        if coverage[category] < floor:
            raise AssertionError(f"required {category} coverage not met: {name}")
    result = dict(status="passed", partial_beats=partial, seed=seed,
                  comparisons=len(rows), mismatches=0, actual_coverage=dict(coverage),
                  asserted_event_coverage=dict(checked_events),
                  summary=list(map(int, summaries[0].split())), digests=rows,
                  marks=[list(map(int, s.split())) for s in
                         re.findall(r"^MARK (.*)$", text, re.M)],
                  saved_contexts=[dict(channel=int(ch), cycle=int(cycle), data=value)
                                  for ch, cycle, value in re.findall(
                                      r"^CONTEXT (\d+) (\d+) ([0-9a-fA-F]+)$", text, re.M)],
                  error_checks=[list(map(int, s.split())) for s in
                                re.findall(r"^ERROR_CHECK (.*)$", text, re.M)],
                  execution=relative(work / "simulate/receipt.json"))
    write_json(work / "result.json", result)
    ex.case(name, "passed", actual_comparisons=len(rows), actual_coverage=dict(coverage),
            asserted_event_coverage=dict(checked_events),
            units="complete digest comparisons; zero bit errors",
            receipt=result["execution"])
    return result


def parameters(ex):
    for top in ("rivet_h3_top", "rivet_h2_top"):
        for value in (-1, 2):
            name = f"parameter-{top}-{value}"
            work = ex.out / name
            work.mkdir()
            tb = work / "tb.sv"
            tb.write_text(f"module tb; {top} #(.PARTIAL_BEATS({value})) dut(); "
                          "initial begin #10;$fatal(1,\"missing rejection\");end endmodule\n")
            exe = work / "sim.vvp"
            ex.run(["iverilog", "-g2012", "-Wall", "-s", "tb", "-o", relative(exe),
                    relative(tb)] + [relative(p) for p in sorted(ROOT.glob("rtl/*.sv"))],
                   name + "/compile")
            rec, text = ex.run(["vvp", relative(exe)], name + "/simulate", expected_exit=None)
            if rec["exit"] == 0 or "PARAMETER ERROR" not in text:
                raise AssertionError(f"explicit illegal parameter rejection missing: {top} {value}")


def benchmark_result(result):
    marks = {row[0]: row for row in result["marks"]}
    if 1 not in marks or 2 not in marks:
        raise AssertionError("missing benchmark interval endpoints")
    cycles = marks[2][1] - marks[1][1]
    rows = result["digests"]
    payload = sum(r[3] for r in rows)
    if cycles <= 0 or not rows:
        raise AssertionError("empty benchmark interval")
    return dict(interval="post key-setup MARK 1 through last retirement MARK 2",
                start_cycle=marks[1][1], end_cycle=marks[2][1], elapsed_cycles=cycles,
                total_simulated_cycles=result["summary"][4],
                pre_steady_state_setup_cycles=marks[1][1] - result["summary"][8],
                messages=len(rows), payload_bytes=payload, cycles_per_message=cycles / len(rows),
                cycles_per_byte=cycles / payload if payload else None,
                payload_bytes_per_cycle=payload / cycles,
                first_beat_to_digest_valid=[r[6] - r[4] for r in rows],
                first_beat_to_retirement=[r[7] - r[4] for r in rows],
                last_beat_to_digest_valid=[r[6] - r[5] for r in rows],
                reset_cycles=result["summary"][8],
                timestamp_convention="rising-edge pre-NBA valid/ready samples; cycle counter starts at first edge",
                key_setup_intervals=[(a[0], a[1], b[1], b[1] - a[1])
                                     for a, b in zip(result["marks"], result["marks"][1:])
                                     if 10000 <= a[0] < 20000 and b[0] == a[0] + 10000],
                channel_messages=dict(collections.Counter(str(r[1]) for r in rows)))


def required_protocol_bins():
    required = {"digest_round_robin_four_pending_late_arrival",
                "context_round_robin_four_pending", "stalls_64_and_simultaneous_retirement",
                "hmac_invalid_key_context", "cancel_key_loading", "key_command_priority",
                "independent_simultaneous_inputs", "stream_command_priority",
                "reset_priority_with_valid_inputs", "random_stalls_and_source_bubbles",
                "invalid_command_2", "invalid_command_7",
                f"high_count_a2_count{(1 << 65) + 111}"}
    for alg in range(3):
        required.add(f"length_overflow_a{alg}")
        required.add(f"staging_a{alg}")
        required.add(f"reset_stalled_digest_a{alg}")
        required.add(f"reset_stalled_context_a{alg}")
        for keyport in ((0, 1) if alg == 1 else (0,)):
            required.add(f"terminator_a{alg}_key{keyport}")
            for last in (0, 1):
                for keep in range(16):
                    required.add(f"mask_a{alg}_key{keyport}_last{last}_keep{keep}")
        block = 128 if alg == 2 else 64
        for n in (0, 1, block - 1, block, block + 1):
            for kind in ("save", "continue", "migrate"):
                required.add(f"context_{kind}_a{alg}_n{n}")
        for opcode in (0, 1, 2, 6):
            required.add(f"nonempty_init_a{alg}_op{opcode}")
        for phase in (0, 1, 4, 6, 7, 8, 70, 86):
            for action in ("cancel", "reset"):
                required.add(f"{action}_a{alg}_phase{phase}")
        bits = ([2048, 2080, 2090, 1672, 128, 135, 0, 648, 136, 125, 2088]
                if alg == 2 else
                [0, 32, 42, 1400, 112, 119, 48, 888, 120, 109, 376, 40,
                 2048, 2080, 2090, 1536, 2088])
        for bit in bits:
            required.add(f"malformed_a{alg}_bit{bit}")
    return required


def behavior(ex):
    for partial in (0, 1):
        for seed in (17, 89, 2026):
            ex.case(f"p{partial}-seed{seed}", "not_run", partial_beats=partial, seed=seed,
                    required={"directed": 312, "random": 72, "long": 3,
                              "published_sha": 6, "published_hmac": 6,
                              "context_migration": 15, "high_count": 7})
    for bits in (32, 64):
        ex.case(f"compression-timing-{bits}", "not_run", required_comparisons=1)
    for alg in range(3):
        for length in (0, 112, 128, 1024):
            for channels in (1, 4):
                ex.case(f"benchmark-a{alg}-n{length}-c{channels}", "not_run",
                        required_comparisons=16 * channels,
                        payload_bytes=16 * channels * length)
    ex.case("benchmark-mixed", "not_run", required_comparisons=64)
    compression_timing(ex)
    results = []
    for partial in (0, 1):
        for seed in (17, 89, 2026):
            result = simulate(ex, f"p{partial}-seed{seed}", scenarios.behavior, partial, seed)
            coverage = result["actual_coverage"]
            missing = required_protocol_bins() - set(result["asserted_event_coverage"])
            if missing:
                ex.case(f"p{partial}-seed{seed}", "failed", missing_bins=sorted(missing))
                raise AssertionError(f"missing mandatory protocol coverage: {sorted(missing)}")
            for name, floor in (("directed", 312), ("random", 72), ("long", 3),
                                ("published_sha", 6), ("published_hmac", 6),
                                ("context_migration", 15), ("high_count", 7)):
                if coverage.get(name, 0) < floor:
                    raise AssertionError(f"mandatory coverage {name}: {coverage.get(name, 0)} < {floor}")
            manifest = json.loads((ex.out / f"p{partial}-seed{seed}/stimulus.json").read_text())
            rows = manifest["messages"]
            actual_directed = collections.Counter(
                (m["channel"], m["algorithm"], m["length"],
                 m["key_length"] if m["algorithm"] == 1 else 0)
                for m in rows if m["category"] == "directed")
            required_directed = collections.Counter()
            for ch in range(4):
                for alg, lengths in ((0, scenarios.SHA256_LENGTHS),
                                     (2, scenarios.SHA512_LENGTHS)):
                    for n in lengths:
                        required_directed[ch, alg, n, 0] += 1
                for kn in scenarios.KEY_LENGTHS:
                    for n in scenarios.HMAC_LENGTHS:
                        required_directed[ch, 1, n, kn] += 1
            if actual_directed != required_directed:
                raise AssertionError("directed boundary/channel/key coverage matrix incomplete")
            for alg in range(3):
                random_rows = [m for m in rows
                               if m["category"] == "random" and m["algorithm"] == alg]
                if len(random_rows) < 24 or {m["channel"] for m in random_rows} != set(range(4)):
                    raise AssertionError("random algorithm/channel coverage incomplete")
                if any(not 0 <= m["length"] <= 8192 for m in random_rows):
                    raise AssertionError("random length outside admitted range")
                if not any(m["category"] == "long" and m["algorithm"] == alg
                           and m["length"] == 65536 for m in rows):
                    raise AssertionError("missing long-message algorithm comparison")
            results.append(result)
    metrics = {}
    for alg in range(3):
        for length in (0, 112, 128, 1024):
            for channels in (1, 4):
                name = f"benchmark-a{alg}-n{length}-c{channels}"
                result = simulate(ex, name,
                                  lambda p, a=alg, n=length, c=channels:
                                  scenarios.benchmark(p, a, n, c))
                metrics[name] = benchmark_result(result)
            one = metrics[f"benchmark-a{alg}-n{length}-c1"]
            four = metrics[f"benchmark-a{alg}-n{length}-c4"]
            four["messages_per_cycle_ratio_vs_single"] = (
                four["messages"] / four["elapsed_cycles"]) / (
                    one["messages"] / one["elapsed_cycles"])
    result = simulate(ex, "benchmark-mixed",
                      lambda p: scenarios.benchmark(p, 0, 128, 4, mixed=True))
    metrics["benchmark-mixed"] = benchmark_result(result)
    write_json(ex.out / "measurements.json", metrics)
    return dict(runs=6, comparisons=sum(r["comparisons"] for r in results),
                mismatches=0, benchmarks=len(metrics))


def compatibility(ex):
    for original in sorted(ROOT.glob("rivet_h2_reference/rtl/*.sv")):
        copied = ROOT / "rtl" / original.name
        if copied.read_bytes() != original.read_bytes():
            raise AssertionError(f"parent byte mismatch: {relative(copied)}")
    results = []
    for partial in (0, 1):
        def producer(p):
            for alg in (0, 1):
                p.setup(0, alg, b"interop key")
                p.bytes(0, b"four", final=False)
                p.snapshot(0, alg, b"four", b"interop key")
                p.drain()
                p.cmd(0, 5)
        exported = simulate(ex, f"h3-export-p{partial}", producer, partial)
        def suite(p):
            scenarios.published(p)
            for alg in (0, 1):
                for length in scenarios.SHA256_LENGTHS:
                    p.message(0, alg, scenarios.random_data(p, length), b"x" * 131,
                              "standalone_hashlib")
            scenarios.contexts(p)
            scenarios.mask_errors(p)
            scenarios.faults(p)
            scenarios.limits(p)
            scenarios.interruptions(p)
            scenarios.modes(p)
            for alg, saved in enumerate(exported["saved_contexts"]):
                p.cmd(0, 5)
                payload = int(saved["data"], 16) & ((1 << 1536) - 1)
                p.cmd(0, 4, payload)
                p.expect(0, alg, b"suffix", b"interop key",
                         reference.digest(alg, b"foursuffix", b"interop key"),
                         "h3_to_h2_restore")
                p.bytes(0, b"suffix")
                p.drain()
        results.append(simulate(ex, f"h2-p{partial}", suite, partial, standalone=True))
        legacy = simulate(ex, f"h2-export-p{partial}", producer, partial, standalone=True)
        def import_actual(p):
            for alg, saved in enumerate(legacy["saved_contexts"]):
                p.cmd(0, 5)
                p.cmd(0, 4, int(saved["data"], 16))
                p.expect(0, alg, b"suffix", b"interop key",
                         reference.digest(alg, b"foursuffix", b"interop key"),
                         "h2_to_h3_restore")
                p.bytes(0, b"suffix")
                p.drain()
        results.append(simulate(ex, f"h3-import-p{partial}", import_actual, partial))
    parameters(ex)
    return dict(parent_byte_equality=True, comparisons=sum(r["comparisons"] for r in results))


def compression_timing(ex):
    """Direct compressor ports prove the separate round/feed-forward convention."""
    for bits, module, cycles in ((32, "rivet_h2_compress", 65),
                                 (64, "rivet_h3_sha512_compress", 81)):
        name = f"compression-timing-{bits}"
        ex.case(name, "running")
        work = ex.out / name
        work.mkdir()
        block_size = bits * 2
        block = bytes((i * 37 + 19) % 256 for i in range(block_size))
        chain = [x ^ 0x12345678 for x in reference.iv(bits)]
        expected = reference.pack(reference.compress(chain, block, bits), bits).hex()
        chain_hex = reference.pack(chain, bits).hex()
        state_width = bits * 8
        tb = work / "tb.sv"
        tb.write_text(f"""
`timescale 1ns/1ps
module tb;
reg clk=0,rst_n,clear=0,start=0;
always #5 clk=~clk;
wire busy,done;
wire [{state_width-1}:0] state_out;
{module} dut(.clk(clk),.rst_n(rst_n),.clear(clear),.start(start),
 .block_data({block_size*8}'h{block.hex()}),.state_in({state_width}'h{chain_hex}),
 .busy(busy),.done(done),.state_out(state_out));
integer i;
initial begin
 rst_n=0;#1;
 if ({{busy,done,state_out}} !== {state_width+2}'d0) $fatal(1,"UNIT_RESET");
 repeat(3) @(negedge clk);
 rst_n=1;start=1;
 @(posedge clk);#1;
 if(busy !== 1'b1 || done !== 1'b0) $fatal(1,"UNIT_START");
 @(negedge clk);start=0;
 for(i=1;i<={cycles};i=i+1) begin
   @(posedge clk);#1;
   if(done !== (i=={cycles})) $fatal(1,"ASSERT COMPRESSION_CYCLE i=%0d",i);
   if(i<{cycles} && busy !== 1'b1) $fatal(1,"UNIT_BUSY");
 end
 if(state_out !== {state_width}'h{expected} || busy !== 1'b0)
   $fatal(1,"ASSERT COMPRESSION_ORACLE");
 @(posedge clk);#1;if(done !== 1'b0) $fatal(1,"UNIT_DONE_PULSE");
 $display("COMPRESSION_TIMING {module} {cycles}");$finish;
end
endmodule
""")
        executable = work / "sim.vvp"
        ex.run(["iverilog", "-g2012", "-Wall", "-s", "tb", "-o", relative(executable),
                relative(tb)] + [relative(p) for p in sorted(ROOT.glob("rtl/*.sv"))],
               name + "/compile")
        _, text = ex.run(["vvp", relative(executable)], name + "/simulate")
        if f"COMPRESSION_TIMING {module} {cycles}" not in text:
            raise AssertionError("compression timing comparison missing")
        ex.case(name, "passed", actual_comparisons=1, latency_cycles=cycles,
                receipt=relative(work / "simulate/receipt.json"))


def defects(ex):
    cases = [
        ("arithmetic", "rivet_h3_sha512_schedule.sv",
         "sigma1 + words[9] + sigma0 + words[0]",
         "sigma1 + words[9] + sigma0 + words[0] + 64'd1",
         lambda p: p.message(0, 2, b"abc"), "ASSERT DIGEST_ORACLE"),
        ("padding", "rivet_h3_sha512.sv", "used_bytes < 8'd112",
         "used_bytes < 8'd113",
         lambda p: p.message(0, 2, b"x" * 112), "ASSERT DIGEST_ORACLE"),
        ("association", "rivet_h3_top.sv",
         "? digest_grant : 2'd0", "? (digest_grant ^ 2'd1) : 2'd0",
         lambda p: p.message(0, 2, b"abc"), "ASSERT EXTRA_DIGEST|ASSERT DIGEST_ORACLE"),
        ("stability", "rivet_h3_top.sv",
         "if (digest_locked) begin", "if (digest_locked) begin\n"
         "                if (!m_ready) digest_grant <= digest_grant + 2'd1;",
         scenarios.stalls, "ASSERT DIGEST_STABILITY"),
    ]
    results = {}
    for name, filename, old, new, build, assertion in cases:
        copy = ex.out / ("mutant-" + name)
        copy.mkdir()
        for source in sorted(ROOT.glob("rtl/*.sv")):
            shutil.copyfile(source, copy / source.name)
        target = copy / filename
        before = target.read_text()
        if before.count(old) != 1:
            raise AssertionError(f"mutation anchor not unique: {name}")
        after = before.replace(old, new)
        target.write_text(after)
        (copy / "delta.patch").write_text("".join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True),
            fromfile="rtl/" + filename, tofile="mutant/" + filename)))
        results[name] = simulate(ex, name, build, rtl=sorted(copy.glob("*.sv")),
                                 rejection=assertion)
    if hashes() != ex.identity:
        raise AssertionError("accepted sources changed during defect campaign")
    return results


def synthesis(ex, default_only=False):
    sizes = {}
    for p in sorted(ROOT.glob("rtl/*.sv")):
        text = p.read_text()
        sizes[relative(p)] = dict(bytes=p.stat().st_size, lines=len(text.splitlines()),
                                 modules=len(re.findall(r"^\s*module\s", text, re.M)))
    results = {}
    for partial in ((0,) if default_only else (0, 1)):
        work = ex.out / f"yosys-p{partial}"
        work.mkdir()
        script = work / "synth.ys"
        pre = work / "preflatten.json"
        net = work / "netlist.json"
        script.write_text(
            "read_verilog -sv " + " ".join(relative(p) for p in sorted(ROOT.glob("rtl/*.sv"))) + "\n"
            f"chparam -set PARTIAL_BEATS {partial} rivet_h3_top\n"
            "hierarchy -check -top rivet_h3_top\n"
            "proc\nopt\ncheck -assert\n"
            f"write_json {relative(pre)}\n"
            "memory\nopt\ncheck -assert\n"
            "synth -noabc\ncheck -assert\nstat\n"
            f"write_json {relative(net)}\n")
        ex.run(["yosys", "-Q", "-T", "-s", relative(script)], f"yosys-p{partial}/execute")
        hierarchy = json.loads(pre.read_text())["modules"]
        final = json.loads(net.read_text())["modules"]
        def top_name(modules):
            candidates = [name for name, body in modules.items()
                          if int(body.get("attributes", {}).get("top", "0"), 2)]
            if len(candidates) != 1:
                raise AssertionError("missing unique synthesis top")
            name = candidates[0]
            identity = modules[name].get("attributes", {}).get("hdlname", name)
            if identity.split()[0].lstrip("\\") != "rivet_h3_top":
                raise AssertionError("synthesis top is not rivet_h3_top")
            return name
        pre_top = top_name(hierarchy)
        final_top = top_name(final)
        instance_counts = collections.Counter()
        connected = []

        def visit(module, path=""):
            body = hierarchy[module]
            for name, cell in body.get("cells", {}).items():
                typ = cell["type"]
                if "latch" in typ.lower():
                    raise AssertionError(f"inferred latch {path}/{name}")
                if typ in hierarchy:
                    identity = hierarchy[typ].get("attributes", {}).get("hdlname", typ)
                    identity = identity.split()[0].lstrip("\\")
                    instance_counts[identity] += 1
                    child_path = path + "/" + name
                    ports = hierarchy[typ].get("ports", {})
                    for port, definition in ports.items():
                        bits = cell.get("connections", {}).get(port, [])
                        if len(bits) != len(definition["bits"]):
                            raise AssertionError(f"unconnected hierarchy port {child_path}.{port}")
                        if definition["direction"] == "output" and not any(
                                isinstance(bit, int) for bit in bits):
                            raise AssertionError(f"constant/missing output {child_path}.{port}")
                    connected.append(child_path)
                    visit(typ, child_path)
        visit(pre_top)
        expected = {"rivet_h3_channel": 4, "rivet_h2_top": 4,
                    "rivet_h3_sha512": 4, "rivet_h3_sha512_compress": 4,
                    "rivet_h3_sha512_schedule": 4, "rivet_h2_compress": 4,
                    "rivet_h2_schedule": 4}
        for module, count in expected.items():
            if instance_counts[module] != count:
                raise AssertionError(f"hierarchy count {module}: {instance_counts[module]} != {count}")
        cell_types = collections.Counter()
        memories = 0
        def count_final(module_name):
            nonlocal memories
            module = final[module_name]
            memories += len(module.get("memories", {}))
            for cell in module.get("cells", {}).values():
                typ = cell["type"]
                cell_types[typ] += 1
                if "latch" in typ.lower():
                    raise AssertionError("latch in final netlist")
                if typ not in final and not typ.startswith("$"):
                    raise AssertionError(f"unresolved cell: {typ}")
                if typ in final:
                    count_final(typ)
        count_final(final_top)
        sequential = sum(n for typ, n in cell_types.items()
                         if "dff" in typ.lower() or "dffe" in typ.lower())
        if sequential == 0:
            raise AssertionError("no real sequential state")
        top = final[final_top]
        driven = {bit for cell in top["cells"].values()
                  for port, direction in cell.get("port_directions", {}).items()
                  if direction == "output" for bit in cell["connections"][port]}
        for port in ("m_valid", "m_channel", "m_alg", "m_digest", "ctx_valid",
                     "ctx_channel", "ctx_data", "error", "s_ready", "k_ready", "cmd_ready"):
            if not any(isinstance(b, int) and b in driven for b in top["ports"][port]["bits"]):
                raise AssertionError(f"missing output-driving logic: {port}")
        results[str(partial)] = dict(instance_counts=dict(instance_counts),
                                     connected_instances=connected,
                                     elaborated_instances_including_top=1 + sum(instance_counts.values()),
                                     cell_types=dict(cell_types), state_cells=sequential,
                                     generic_leaf_cells=sum(n for typ, n in cell_types.items()
                                                            if typ not in final),
                                     memories=memories, source_size=sizes,
                                     source_totals={key: sum(row[key] for row in sizes.values())
                                                    for key in ("bytes", "lines", "modules")})
    ex.run(["iverilog", "-g2012", "-Wall", "-t", "null", "-s", "rivet_h2_top"] +
           [relative(p) for p in sorted(ROOT.glob("rtl/*.sv"))], "h2-elaboration")
    write_json(ex.out / "resource-measurements.json", results)
    return results


def portable(ex):
    bundle = ex.out / "project"
    bundle.mkdir()
    for source in sources():
        target = bundle / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    rec, text = ex.run(["python3", "tests/verify.py", "--check", "portable",
                        "--portable-child", "--out", "evidence/reproduction"],
                       "reproduce", cwd=bundle)
    result = json.loads((bundle / "evidence/reproduction/receipt.json").read_text())
    if result["status"] != "passed":
        raise AssertionError("portable child incomplete")
    return dict(status="passed", bundle=relative(bundle),
                receipt=relative(bundle / "evidence/reproduction/receipt.json"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=CHECKS)
    parser.add_argument("--out")
    parser.add_argument("--portable-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    name = args.out or "evidence/complete-" + uuid.uuid4().hex[:12]
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.parts[:1] != ("evidence",):
        parser.error("--out must be a project-relative path below evidence/")
    out = ROOT / candidate
    if out.resolve() == (ROOT / "evidence").resolve() or out.is_symlink():
        parser.error("--out must name a fresh evidence subdirectory")
    ex = Execution(out)
    try:
        checks = [args.check] if args.check else list(CHECKS)
        tools = ["python3", "iverilog", "vvp"]
        if any(c in checks for c in ("synthesis", "portable")):
            tools.append("yosys")
        ex.prerequisites(tools)
        reference.self_check()
        results = {}
        if args.portable_child:
            if args.check != "portable":
                raise ValueError("--portable-child requires --check portable")
            results["smoke"] = simulate(ex, "smoke", scenarios.smoke)
            parameters(ex)
            results["synthesis"] = synthesis(ex, default_only=True)
        else:
            for check in checks:
                results[check] = globals()[check](ex)
        if hashes() != ex.identity:
            raise AssertionError("sources changed during verification")
        ex.finish("passed", results=results)
        print(json.dumps(dict(status="passed", receipt=relative(ex.out / "receipt.json"))))
    except Exception as exc:
        ex.finish("failed", error=f"{type(exc).__name__}: {exc}")
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
