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

    def result(self, status, auth=False, locked=True, check=b"", label=None):
        self.record(12,status,int(auth),int(locked),len(check),
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
            w.provision(pk,level)
            result = w.verification(pk,bytes.fromhex(t["signature"]),
                                    bytes.fromhex(t["message"]),bytes.fromhex(t["context"]),
                                    level,f"public_kat_level_{level}_tc_{t['tcId']}")
            assert result["auth"]
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
