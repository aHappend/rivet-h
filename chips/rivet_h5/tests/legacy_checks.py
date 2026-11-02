"""Public-pin parent comparison and independent hashlib/HMAC/Merkle checking."""

import re
import secrets
import shutil

from execution import digest
from legacy_vectors import generate
from simulation import cleanup_objects


def ports(path):
    header = path.read_text().split(");", 1)[0]
    result = []
    pattern = r"\b(input|output)\s+wire\s*(\[[^]]+\])?\s*([^;()]+?)(?=,\s*(?:input|output)|\s*$)"
    # Match declaration groups including compressed multiple-name H5 ports.
    for match in re.finditer(pattern, header.split(") (", 1)[-1], re.S):
        direction, width, names = match.groups()
        for name in names.split(","):
            name = name.strip()
            if not re.fullmatch(r"[A-Za-z_]\w*", name):
                raise AssertionError(f"unparsed public port {name!r}")
            result.append((direction, width or "", name))
    if not result or len({n for _, _, n in result}) != len(result):
        raise AssertionError("empty/duplicate public interface inventory")
    return result


def parent_copy(run):
    folder = run.path / ("immutable-parent-" + secrets.token_hex(4))
    folder.mkdir()
    sources = sorted(run.root.glob("rivet_h4_reference/rtl/*.sv"))
    names = [p.stem for p in sources]
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
    ledger = {}
    for source in sources:
        dest = folder / source.name
        text = pattern.sub(lambda m: "reference_" + m[0], source.read_text())
        with dest.open("x") as f:
            f.write(text)
        ledger[source.name] = dict(original_sha256=digest(source), renamed_sha256=digest(dest))
    return sorted(folder.glob("*.sv")), ledger


def wiring(run, directory, parameter_only=False):
    current = ports(run.root / "rtl/rivet_h5_top.sv")
    parent = ports(run.root / "rivet_h4_reference/rtl/rivet_h4_top.sv")
    current_map = {n: (d, w) for d, w, n in current}
    for d, w, n in parent:
        if current_map.get(n) != (d, w):
            raise AssertionError(f"changed inherited public interface {n}")
    if not {"n_cmd_ready", "sam_cmd_ready", "pq_cmd_ready"}.issubset(current_map):
        raise AssertionError("missing H5 service ports")
    lines = []
    for direction, width, name in current:
        if name in ("clk", "rst_n"):
            continue
        lines.append(f"{'reg' if direction == 'input' else 'wire'} {width} {name}"
                     + ("=0;" if direction == "input" else ";"))
    lines.append("rivet_h5_top #(.PARTIAL_BEATS(PARTIAL_BEATS), "
                 ".MAX_PAGE_BYTES(MAX_PAGE_BYTES)) dut (.*);")
    comparisons = []
    if not parameter_only:
        connections = []
        for direction, width, name in parent:
            if direction == "output":
                lines.append(f"wire {width} parent_{name};")
                connections.append(f".{name}(parent_{name})")
                comparisons.append(name)
            else:
                connections.append(f".{name}({name})")
        lines.append("reference_rivet_h4_top #(.PARTIAL_BEATS(PARTIAL_BEATS), "
                     ".MAX_PAGE_BYTES(MAX_PAGE_BYTES)) parent (" + ",".join(connections) + ");")
        lines.append("task automatic parent_check; begin")
        for name in comparisons:
            lines.append(f'if ({name} !== parent_{name}) '
                         f'$fatal(1,"parent interface mismatch: {name} clock=%0d",cycles);')
            lines.append(f'if ((^{name}) === 1\'bx) '
                         f'$fatal(1,"legacy public X/Z: {name} clock=%0d",cycles);')
        lines.append("differential_samples=differential_samples+1; end endtask")
    include = directory / "legacy_wires.svh"
    with include.open("x") as f:
        f.write("\n".join(lines) + "\n")
    return include, comparisons


def build(run, partial=0, page=4096, simulator="verilator", source_root=None):
    directory = run.path / ("legacy-build-" + secrets.token_hex(4))
    directory.mkdir()
    wiring(run, directory)
    parent, ledger = parent_copy(run)
    root = run.root if source_root is None else source_root
    sources = [str(run.root / "tests/legacy_tb.sv"),
               *map(str, sorted(root.glob("rtl/*.sv"))), *map(str, parent)]
    if simulator == "icarus":
        binary = directory / "legacy.vvp"
        argv = ["iverilog", "-g2012", "-Wall", "-s", "legacy_tb", "-I", str(directory),
                f"-Plegacy_tb.PARTIAL_BEATS={partial}", f"-Plegacy_tb.MAX_PAGE_BYTES={page}",
                "-o", str(binary), *sources]
        run.command(argv, "compile-legacy-icarus")
        return ["vvp", str(binary)], None, ledger
    obj = directory / ("compile-obj-" + secrets.token_hex(4))
    argv = ["verilator", "--binary", "--timing", "-Wno-fatal", "--top-module", "legacy_tb",
            "-I" + str(directory), f"-GPARTIAL_BEATS={partial}", f"-GMAX_PAGE_BYTES={page}",
            "--Mdir", str(obj), "-j", "2", *sources]
    run.command(argv, "compile-legacy-verilator")
    return [str(obj / "Vlegacy_tb")], obj, ledger


def check_counts(stdout, inventory):
    names = ("operations", "digests", "sponge_bytes", "merkle_results", "replay_bytes",
             "contexts", "errors", "stalls", "differential_samples", "clocks")
    pattern = "SUMMARY " + " ".join(n + r"=(\d+)" for n in names)
    matches = re.findall(pattern, stdout)
    if len(matches) != 1:
        raise AssertionError("absent/duplicate legacy summary")
    observed = dict(zip(names, map(int, matches[0])))
    for name in names[:7]:
        if observed[name] != inventory.get(name, 0):
            raise AssertionError(f"legacy observed {name}: {observed[name]} != {inventory.get(name, 0)}")
    if observed["stalls"] <= 0 or observed["differential_samples"] < 2 * observed["clocks"] - 4:
        raise AssertionError("legacy stalls/dual-edge parent comparison not exercised")
    return observed


def suite(run, compact=False):
    results = []
    configs = [(0, 3), (1, 3)] if compact else [
        (partial, page) for partial in (0, 1) for page in (1, 3, 4, 5, 4095, 4096)]
    for partial, page in configs:
        path = run.path / (f"legacy-p{partial}-page{page}-" + secrets.token_hex(4) + ".txt")
        inventory = generate(path, partial, page, compact=compact)
        argv, obj, ledger = build(run, partial, page)
        try:
            rec, out, _ = run.command([*argv, "+vectors=" + str(path)],
                                     f"legacy-p{partial}-page{page}")
            results.append(dict(partial_beats=partial, max_page_bytes=page, inventory=inventory,
                                observed=check_counts(out, inventory), parent_copy=ledger,
                                stdout=rec["stdout"], stderr=rec["stderr"]))
        finally:
            cleanup_objects(obj)
    # IEEE simulation covers a genuinely compact legacy/top configuration.
    path = run.path / ("legacy-icarus-vectors-" + secrets.token_hex(4) + ".txt")
    inventory = generate(path, 1, 3, compact=True)
    argv, obj, ledger = build(run, 1, 3, simulator="icarus")
    rec, out, _ = run.command([*argv, "+vectors=" + str(path)], "legacy-icarus", timeout=600)
    observed = check_counts(out, inventory)
    if observed["clocks"] > 500000:
        raise AssertionError("legacy Icarus smoke exceeded compact clock bound")
    results.append(dict(simulator="icarus", inventory=inventory, observed=observed,
                        parent_copy=ledger, stdout=rec["stdout"], stderr=rec["stderr"]))
    return results
