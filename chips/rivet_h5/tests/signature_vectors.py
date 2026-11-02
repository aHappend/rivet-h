"""Manifest/signature transactions with independently confirmed expectations."""

import json
import random
from collections import Counter

from mldsa_reference import (crosscheck_kats,keygen,sign,verify,decode_signature,
                             encode_signature)
from reference import PARAMS,Q


class Writer:
    def __init__(self, f):
        self.f = f
        self.counts = Counter()
        self.cases = []

    def record(self, opcode, *parts):
        self.f.write(str(opcode)+" "+" ".join(map(str,parts))+"\n")

    def reset(self, delay=0):
        self.record(14,delay)
        self.counts["resets"]+=1

    def command(self, level, op, ctxlen=0, msglen=0):
        self.record(10,level,op,ctxlen,msglen)
        self.counts["commands"]+=1

    def beat(self, kind, data, keep, last):
        self.record(11,kind,f"{data:08x}",keep,int(last))
        self.counts["beats"]+=1

    def section(self, kind, data):
        if not data:
            self.beat(kind,0,0,True)
        for offset in range(0,len(data),4):
            part = data[offset:offset+4]
            keep = {1:8,2:12,3:14,4:15}[len(part)]
            self.beat(kind,int.from_bytes(part.ljust(4,b"\0"),"big"),
                      keep,offset+len(part)==len(data))

    def result(self, status, auth=False, locked=True, check=b"", label=None, hold=False):
        self.record(15 if hold else 12,status,int(auth),int(locked),len(check),
                    f"{int.from_bytes(check,'little'):0128x}")
        self.counts["results"]+=1
        self.counts["challenge_bytes"]+=len(check)
        self.counts["stalls"]+=4
        self.cases.append(dict(result_index=self.counts["results"],label=label,
                               expected_status=status,expected_auth=auth,
                               expected_locked=locked,challenge=check.hex()))

    def provision(self, pk, level):
        self.command(level,0)
        self.section(0,pk)
        self.result(0,label=f"provision_level_{level}")

    def verification(self, pk, sig, message, context, level, label):
        expected = verify(pk,sig,message,context,level)
        self.command(level,1,len(context),len(message))
        self.section(1,sig)
        if expected["status"] not in (3,4):
            self.section(2,context)
            self.section(3,message)
        self.result(expected["status"],expected["auth"],True,
                    bytes.fromhex(expected.get("challenge","")),label)
        self.cases[-1]["oracle"] = expected
        return expected

    def cancel(self, delay=0, locked=True):
        self.record(13,delay,int(locked))
        self.counts["cancels"]+=1


def boundaries(w, pk, sig, message, context, level):
    p = PARAMS[level]
    c, z, hints = decode_signature(sig, level)
    limit = p["gamma1"] - p["beta"]
    for signum in (-1, 1):
        for delta in (0, -1):
            zs = [[0] * 256 for _ in range(p["l"])]
            zs[0][0] = (signum * (limit + delta)) % Q
            forged = encode_signature(bytes(p["cbytes"]), zs, [[0]*256 for _ in range(p["k"])], level)
            expected = w.verification(pk, forged, b"", b"", level, f"norm_{signum}_{delta}")
            assert expected["status"] == (4 if delta == 0 else 5)
    hint_base = p["sigbytes"] - p["omega"] - p["k"]
    for name in ("omega", "omega_plus_one", "descending", "duplicate", "decreasing_endpoints", "unused"):
        zs = [[0]*256 for _ in range(p["l"])]
        hs = [[0]*256 for _ in range(p["k"])]
        hs[0][:p["omega"]] = [1]*p["omega"]
        raw = bytearray(encode_signature(bytes(p["cbytes"]), zs, hs, level))
        if name == "omega_plus_one":
            raw[hint_base+p["omega"]:] = bytes([p["omega"]+1])*p["k"]
        elif name == "descending":
            raw[hint_base:hint_base+2] = b"\x02\x01"
        elif name == "duplicate":
            raw[hint_base:hint_base+2] = b"\x01\x01"
        elif name == "decreasing_endpoints":
            raw[hint_base+p["omega"]+1] = p["omega"]-1
        elif name == "unused":
            raw[hint_base+p["omega"]:] = bytes(p["k"])
            raw[hint_base] = 1
        outcome = w.verification(pk, bytes(raw), b"", b"", level, "hint_" + name)
        assert outcome["status"] == (5 if name == "omega" else 3)
    # Each malformed stream is stopped at the first invalid transfer, not hidden
    # behind a fixture parse failure or an unanswered continuation.
    for name in ("early_last", "late_last", "overflow", "wrong_kind", "invalid_mask", "nonfinal_partial"):
        w.command(level, 1, 0, 0)
        if name in ("early_last", "wrong_kind", "invalid_mask", "nonfinal_partial"):
            w.beat(0 if name == "wrong_kind" else 1, int.from_bytes(sig[:4], "big"),
                   5 if name == "invalid_mask" else 8 if name == "nonfinal_partial" else 15,
                   name == "early_last")
        else:
            for offset in range(0, len(sig), 4):
                chunk = sig[offset:offset+4]
                final = offset+len(chunk) == len(sig)
                if final:
                    w.beat(1, int.from_bytes(chunk.ljust(4, b"\0"), "big"),
                           15 if name == "overflow" else {1:8,2:12,3:14,4:15}[len(chunk)], False)
                else:
                    w.beat(1, int.from_bytes(chunk, "big"), 15, False)
        w.result(2, label="signature_framing_" + name)
    for section in ("context", "message"):
        for name in ("early", "late", "overflow", "wrong_kind", "empty_nonzero"):
            length = 0 if name == "empty_nonzero" else 4 if name == "late" else 3 if name == "overflow" else 8
            w.command(level, 1, length if section == "context" else 0,
                      length if section == "message" else 0)
            w.section(1, sig)
            if section == "message":
                w.section(2, b"")
            kind = 2 if section == "context" else 3
            w.beat(1 if name == "wrong_kind" else kind, 0x01020304, 15, name != "late")
            w.result(2, label=section + "_framing_" + name)
    # Level mismatch preserves the provisioned trusted key.
    w.command((level+1) % 3, 1)
    w.result(1, label="mismatched_key_level")
    # CANCEL and reset while an actual, already compared result is pending.
    valid = verify(pk, sig, message, context, level)
    assert valid["auth"]
    for termination in ("cancel", "reset"):
        w.command(level, 1, len(context), len(message))
        w.section(1, sig); w.section(2, context); w.section(3, message)
        w.result(0, True, True, bytes.fromhex(valid["challenge"]), "pending_" + termination, hold=True)
        if termination == "cancel":
            w.cancel()
        else:
            w.reset()
            w.provision(pk, level)
        w.verification(pk, sig, message, context, level, termination + "_output_recovery")
    for phase in ("receive", "compute"):
        w.command(level, 1, len(context), len(message))
        if phase == "receive":
            w.beat(1, int.from_bytes(sig[:4], "big"), 15, False)
            w.reset()
        else:
            w.section(1, sig)
            w.reset(delay=200)
        w.command(level, 1); w.result(1, locked=False, label="reset_" + phase + "_cleared_key")
        w.provision(pk, level)
        w.verification(pk, sig, message, context, level, "reset_" + phase + "_recovery")


def boundary_probe(path, fixture_path):
    fixture = json.loads(fixture_path.read_text())
    kats = crosscheck_kats(fixture)
    with path.open("x", encoding="ascii") as f:
        w = Writer(f)
        for group in fixture["testGroups"]:
            level = ("ML-DSA-44","ML-DSA-65","ML-DSA-87").index(group["parameterSet"])
            case = next(case for case in group["tests"] if case["testPassed"])
            pk, sig, message, context = (bytes.fromhex(case[key]) for key in
                                         ("pk", "signature", "message", "context"))
            w.reset()
            provision_frames(w,pk,level)
            w.provision(pk, level)
            boundaries(w, pk, sig, message, context, level)
    return dict(counts=dict(w.counts), cases=w.cases, public_kat_validation=kats)


def provision_frames(w,pk,level):
    # Invalid public-key framing cannot atomically pin a key.
    for kind,keep,last in ((1,15,0),(0,5,0),(0,15,1),(0,8,0)):
        w.command(level,0); w.beat(kind,int.from_bytes(pk[:4],"big"),keep,last)
        w.result(2,locked=False,label="provision_framing")
    w.command(level,0)
    for offset in range(0,len(pk),4):
        w.beat(0,int.from_bytes(pk[offset:offset+4],"big"),15,False)
    w.result(2,locked=False,label="provision_missing_last")


def generate(path,fixture_path,compact=False,seeds=(17,29,43)):
    fixture = json.loads(fixture_path.read_text())
    kat_outcomes = crosscheck_kats(fixture)
    with path.open("x",encoding="ascii") as f:
        w = Writer(f)
        # Public externally produced signatures exercise a second source of inputs,
        # not merely agreement between the shipped signer and verifier.
        for group in fixture["testGroups"]:
            level = ("ML-DSA-44","ML-DSA-65","ML-DSA-87").index(group["parameterSet"])
            t = next(t for t in group["tests"] if t["testPassed"])
            pk = bytes.fromhex(t["pk"])
            w.reset()
            if not compact:
                provision_frames(w,pk,level)
            w.provision(pk,level)
            result = w.verification(pk,bytes.fromhex(t["signature"]),
                                    bytes.fromhex(t["message"]),bytes.fromhex(t["context"]),
                                    level,f"public_kat_level_{level}_tc_{t['tcId']}")
            assert result["auth"]
            if not compact:
                boundaries(w, pk, bytes.fromhex(t["signature"]), bytes.fromhex(t["message"]),
                           bytes.fromhex(t["context"]), level)
        if not compact:
            for seed in seeds:
                rng = random.Random(seed)
                for level in range(3):
                    pk,sk = keygen(rng.randbytes(32),level)
                    w.reset()
                    w.command(level,1)
                    w.result(1,locked=False,label="verification_before_provision")
                    w.provision(pk,level)
                    w.command(level,0)
                    w.result(6,label="locked_key_overwrite")
                    w.command(3,1)
                    w.result(1,label="invalid_level")
                    w.command(level,3)
                    w.result(1,label="invalid_command")
                    for case in range(4):
                        message = rng.randbytes((0,1,513,4096)[case])
                        context = rng.randbytes((0,1,255,37)[case])
                        sig = sign(sk,message,context,rng.randbytes(32))
                        valid = w.verification(pk,sig,message,context,level,
                                               f"valid_seed_{seed}_level_{level}_case_{case}")
                        assert valid["auth"]
                        altered = message+b"\x01" if not message else bytes([message[0]^1])+message[1:]
                        assert not w.verification(pk,sig,altered,context,level,"forged_message")["auth"]
                        altered_context = context+b"\x01" if not context else bytes([context[0]^1])+context[1:]
                        assert not w.verification(pk,sig,message,altered_context,level,"forged_context")["auth"]
                        c,z,hints = decode_signature(sig,level)
                        altered_c = bytes([c[0]^1])+c[1:]
                        forged = encode_signature(altered_c,z,hints,level)
                        assert not w.verification(pk,forged,message,context,level,"forged_challenge")["auth"]
                        altered_z = [row[:] for row in z]
                        altered_z[0][0]=(altered_z[0][0]+1)%Q
                        forged = encode_signature(c,altered_z,hints,level)
                        assert not w.verification(pk,forged,message,context,level,"forged_z")["auth"]
                        altered_h = [row[:] for row in hints]
                        changed = False
                        for row in altered_h:
                            if any(row):
                                row[row.index(1)]=0
                                changed=True
                                break
                        assert changed,"valid signature fixture must contain nonzero hints"
                        forged = encode_signature(c,z,altered_h,level)
                        assert not w.verification(pk,forged,message,context,level,"forged_hints")["auth"]
                    # Exact norm threshold and inside threshold are independently decoded.
                    p = PARAMS[level]
                    for delta in (0,-1):
                        altered_z = [[0]*256 for _ in range(p["l"])]
                        altered_z[0][0]=p["gamma1"]-p["beta"]+delta
                        forged = encode_signature(bytes(p["cbytes"]),altered_z,
                                                  [[0]*256 for _ in range(p["k"])],level)
                        result = w.verification(pk,forged,b"",b"",level,f"norm_limit_delta_{delta}")
                        assert result["status"]==(4 if delta==0 else 5)
                    # Cancel work during signature reception, then recover with pinned key.
                    w.command(level,1,0,0)
                    w.beat(1,int.from_bytes(sig[:4],"big"),15,False)
                    w.cancel()
                    w.verification(pk,sig,message,context,level,"cancel_receive_recovery")
                    w.command(level,1,len(context),len(message))
                    w.section(1,sig)
                    w.cancel(delay=200)
                    w.verification(pk,sig,message,context,level,"cancel_compute_recovery")
                    wrong_pk,_ = keygen(rng.randbytes(32),level)
                    w.reset()
                    w.provision(wrong_pk,level)
                    assert not w.verification(wrong_pk,sig,message,context,level,"wrong_pinned_key")["auth"]
    return dict(counts=dict(w.counts),cases=w.cases,public_kat_validation=kat_outcomes)
