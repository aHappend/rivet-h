"""Genuine Yosys lowering, complete structural inspection and lossless retention."""

import gzip
import hashlib
import json
from pathlib import Path
import secrets

from execution import digest


REQUIRED_PATHS = {
    "u_parent": "rivet_h4_top",
    "u_ntt": "rivet_h5_ntt",
    "u_ntt.u_butterfly": "rivet_h5_butterfly",
    "u_ntt.u_butterfly.u_montgomery": "rivet_h5_montgomery",
    "u_sampler": "rivet_h5_sampler",
    "u_sampler.u_xof": "rivet_h5_xof",
    "u_sampler.u_xof.u_keccak": "rivet_h4_keccak",
    "u_verify": "rivet_h5_verify",
    "u_verify.u_ntt": "rivet_h5_ntt",
    "u_verify.u_ntt.u_butterfly": "rivet_h5_butterfly",
    "u_verify.u_ntt.u_butterfly.u_montgomery": "rivet_h5_montgomery",
    "u_verify.u_sampler": "rivet_h5_sampler",
    "u_verify.u_sampler.u_xof": "rivet_h5_xof",
    "u_verify.u_sampler.u_xof.u_keccak": "rivet_h4_keccak",
    "u_verify.u_hash": "rivet_h5_xof",
    "u_verify.u_hash.u_keccak": "rivet_h4_keccak",
}


def module_name(name,module):
    hdlname = module.get("attributes",{}).get("hdlname",name)
    return hdlname.split()[0].lstrip("\\")


def inspect(data, top, mapped=False):
    modules = data["modules"]
    if top not in modules:
        raise AssertionError("missing synthesis top")
    totals = dict(cells=0,registered_bits=0,memory_bits=0,arithmetic_cells=0,
                  latches=0,division_modulo=0)
    paths = {}
    path_metrics = {}
    path_connections = {}
    visited = set()

    def visit(name,path,ancestors):
        if name in ancestors:
            raise AssertionError("recursive/unresolved synthesis hierarchy")
        module = modules[name]
        if path:
            paths[path] = module_name(name,module)
        counts = dict(registered_bits=0,memory_bits=0,arithmetic_cells=0)
        for cell_name,cell in module.get("cells",{}).items():
            typ = cell["type"]
            if typ in modules:
                child_path = f"{path}.{cell_name}".strip(".")
                path_connections[child_path] = sum(
                    isinstance(bit,int) for bits in cell.get("connections",{}).values() for bit in bits)
                child = visit(typ,child_path,ancestors|{name})
                for k in counts:
                    counts[k]+=child[k]
                continue
            if not typ.startswith("$"):
                raise AssertionError(f"unresolved synthesis module/cell {typ}")
            lowered = typ.lower()
            if "dlatch" in lowered:
                raise AssertionError(f"latch at {path}.{cell_name}: {typ}")
            if lowered.startswith(("$div","$mod","$divfloor","$modfloor")):
                raise AssertionError(f"division/modulo at {path}.{cell_name}: {typ}")
            if not cell.get("port_directions"):
                raise AssertionError(f"missing primitive port directions {path}.{cell_name}")
            if "dff" in lowered:
                counts["registered_bits"]+=len(cell.get("connections",{}).get("Q",[]))
            if lowered.startswith("$mem"):
                params = cell.get("parameters",{})
                def integer(key):
                    v = params.get(key,0)
                    return int(v,2) if isinstance(v,str) else v
                counts["memory_bits"]+=integer("WIDTH")*integer("SIZE")
            if typ in ("$mul","$add","$sub","$alu") or (mapped and typ.startswith(("$_AND","$_XOR","$_MUX"))):
                counts["arithmetic_cells"]+=1
        if name not in visited:
            totals["cells"]+=len(module.get("cells",{}))
            visited.add(name)
        path_metrics[path] = dict(counts)
        return counts

    counts = visit(top,"",set())
    totals.update(counts)
    if counts["registered_bits"]<=0 or counts["arithmetic_cells"]<=0:
        raise AssertionError("synthesized machine has no meaningful registered arithmetic")
    if top in ("rivet_h5_top","rivet_h5_ntt","rivet_h5_sampler","rivet_h5_verify") and counts["memory_bits"]<=0:
        raise AssertionError("expected retained polynomial/key memory")
    if top=="rivet_h5_top":
        for path, expected in REQUIRED_PATHS.items():
            if paths.get(path)!=expected:
                raise AssertionError(f"missing substantive hierarchy {path}: {paths.get(path)}")
            if path_metrics[path]["registered_bits"]<=0 or path_connections[path]<=0:
                raise AssertionError(f"decorative or disconnected required instance: {path}")
            if expected=="rivet_h5_montgomery" and path_metrics[path]["arithmetic_cells"]<=0:
                raise AssertionError(f"missing arithmetic in {path}")
    return dict(top=top,mapped=mapped,structural=totals,hierarchy=paths,path_metrics=path_metrics,
                retained_modules=sorted(visited))


def compress_complete(path):
    raw_size = path.stat().st_size
    raw_hash = digest(path)
    zipped = path.with_suffix(path.suffix+".gz")
    with path.open("rb") as src, zipped.open("xb") as dest:
        with gzip.GzipFile(fileobj=dest,mode="wb",mtime=0) as z:
            while chunk:=src.read(1024*1024):
                z.write(chunk)
    restored = hashlib.sha256()
    restored_size = 0
    with gzip.open(zipped,"rb") as z:
        while chunk:=z.read(1024*1024):
            restored.update(chunk)
            restored_size+=len(chunk)
    if restored_size!=raw_size or restored.hexdigest()!=raw_hash:
        raise AssertionError("lossless synthesis retention round-trip failed")
    result = dict(compressed_sha256=digest(zipped),compressed_bytes=zipped.stat().st_size,
                  decompressed_sha256=raw_hash,decompressed_bytes=raw_size)
    path.unlink()
    return zipped,result


def synthesize(run,top,partial=0,page=4096,mapped=False):
    ident = f"{top}-p{partial}-page{page}-"+secrets.token_hex(4)
    script = run.path/(ident+".ys")
    netlist = run.path/(ident+".json")
    sources = sorted(run.root.glob("rtl/*.sv"))
    # Production paths are constructed at execution, not private host literals.
    read = "read_verilog -sv "+" ".join('"'+str(p)+'"' for p in sources)
    lines = [read]
    if top=="rivet_h5_top":
        lines += [f"chparam -set PARTIAL_BEATS {partial} -set MAX_PAGE_BYTES {page} {top}"]
    lines += [f"hierarchy -check -top {top}"]
    if mapped:
        if top not in ("rivet_h5_montgomery","rivet_h5_butterfly"):
            raise ValueError("mapped flow is bounded to arithmetic leaves")
        lines += [f"synth -top {top}", "check -assert", "stat"]
    else:
        lines += ["proc", "opt_expr", "opt_clean", "check -assert",
                  "memory -nomap", "opt_clean", "check -assert", "stat"]
    lines += ['write_json "'+str(netlist)+'"']
    with script.open("x") as f:
        f.write("\n".join(lines)+"\n")
    record,_,_ = run.command(["yosys","-Q","-s",str(script)],"synthesize-"+ident)
    with netlist.open() as f:
        data = json.load(f)
    result = inspect(data,top,mapped)
    zipped,retention = compress_complete(netlist)
    result.update(partial_beats=partial,max_page_bytes=page,
                  netlist=run.relative(zipped),retention=retention,
                  yosys_stdout=record["stdout"],yosys_stderr=record["stderr"])
    return result


def suite(run):
    results = []
    for partial in (0,1):
        for page in (1,3,4096):
            results.append(synthesize(run,"rivet_h5_top",partial,page))
    for top in ("rivet_h5_montgomery","rivet_h5_butterfly","rivet_h5_ntt",
                "rivet_h5_xof","rivet_h5_sampler","rivet_h5_usehint","rivet_h5_verify"):
        results.append(synthesize(run,top))
    for top in ("rivet_h5_montgomery","rivet_h5_butterfly"):
        results.append(synthesize(run,top,mapped=True))
    return results
