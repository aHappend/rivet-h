"""Directed byte candidates exercise the unchanged RTL sampler parser."""

import re
import secrets

from execution import digest
from reference import N, Q, PARAMS, pack_fields
from simulation import cleanup_objects


def expected(op, level, data):
    p = PARAMS[level]
    out = []
    offset = 0
    rejects = collisions = 0
    if op in (0,1):
        while len(out) < N:
            candidate = int.from_bytes(data[offset:offset+3],"little") & 0x7fffff
            offset += 3
            if candidate < Q:
                out.append(candidate)
            else:
                rejects += 1
    elif op == 2:
        for byte in data:
            for value in (byte & 15, byte >> 4):
                if value < (15 if p["eta"]==2 else 9):
                    out.append((p["eta"]-(value % 5 if p["eta"]==2 else value)) % Q)
                else:
                    rejects += 1
                if len(out)==N:
                    return out,dict(rejected=rejects,collisions=0)
    elif op == 3:
        width = 18 if level==0 else 20
        packed = int.from_bytes(data,"little")
        out = [(p["gamma1"]-((packed>>(i*width)) & ((1<<width)-1))) % Q for i in range(N)]
    else:
        signs = int.from_bytes(data[:8],"little")
        offset = 8
        out = [0]*N
        for i in range(N-p["tau"],N):
            b = data[offset]; offset += 1
            while b>i:
                rejects += 1
                b = data[offset]; offset += 1
            collisions += int(out[b]!=0)
            out[i]=out[b]
            out[b]=(1-2*(signs&1)) % Q
            signs >>= 1
    if len(out)!=N:
        raise AssertionError("directed parser oracle lacked coefficients")
    return out,dict(rejected=rejects,collisions=collisions)


def vectors(coefficients, byte_path):
    inventory = []
    with coefficients.open("x") as coeff, byte_path.open("x") as stream:
        for level in range(3):
            p = PARAMS[level]
            for op in range(5):
                if op in (0,1):
                    candidates = [Q-1,Q,0x7fffff,0xffffff,0x800000+(Q-1),0]
                    candidates += list(range(N))
                    data = b"".join(c.to_bytes(3,"little") for c in candidates)
                elif op==2:
                    data = bytes([0xef,0x90,0x1e,0x87,0x54,0x32,0x10])*100
                elif op==3:
                    width = 18 if level==0 else 20
                    fields = [0,(1<<width)-1,p["gamma1"],p["gamma1"]-1,p["gamma1"]+1]
                    fields += [(i*13037) % (1<<width) for i in range(N-len(fields))]
                    data = pack_fields(fields,width)
                else:
                    # Reject 255 at the first index; repeated zero selections
                    # force genuine swaps of earlier nonzero coefficients.
                    data = bytes.fromhex("a55aa55a3cc39669")+bytes([255])+bytes(p["tau"])
                result, events = expected(op,level,data)
                coeff.write(f"{op} {level} "+" ".join(f"{x:x}" for x in result)+"\n")
                stream.write(str(len(data))+" "+" ".join(f"{x:x}" for x in data)+"\n")
                inventory.append(dict(op=op,level=level,events=events,bytes_sha256=__import__(
                    "hashlib").sha256(data).hexdigest()))
    return inventory


def suite(run):
    coefficient_path = run.path/("parser-coefficients-"+secrets.token_hex(4)+".txt")
    byte_path = run.path/("parser-bytes-"+secrets.token_hex(4)+".txt")
    inventory = vectors(coefficient_path,byte_path)
    sources = [str(p) for p in sorted(run.root.glob("rtl/*.sv")) if p.name!="rivet_h5_xof.sv"]
    sources += [str(run.root/"tests/sampler_parser_tb.sv")]
    obj = run.path/("compile-obj-parser-"+secrets.token_hex(4))
    run.command(["verilator","--binary","--timing","-Wno-fatal","--top-module","sampler_parser_tb",
                 "--Mdir",str(obj),"-j","2",*sources],"compile-directed-parser")
    try:
        rec,out,_ = run.command([str(obj/"Vsampler_parser_tb"),"+vectors="+str(coefficient_path),
                                 "+bytes="+str(byte_path)],"directed-parser")
        matches = re.findall(r"SUMMARY polynomials=(\d+) comparisons=(\d+) clocks=(\d+)",out)
        if len(matches)!=1 or tuple(map(int,matches[0][:2]))!=(15,15*N):
            raise AssertionError("directed parser observations disagree with independent inventory")
        return dict(inventory=inventory,polynomials=15,comparisons=15*N,
                    observed_clocks=int(matches[0][2]),stdout=rec["stdout"],stderr=rec["stderr"],
                    unchanged_sampler_sha256=digest(run.root/"rtl/rivet_h5_sampler.sv"),
                    test_only_byte_source_sha256=digest(run.root/"tests/sampler_parser_tb.sv"))
    finally:
        cleanup_objects(obj)
