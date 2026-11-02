"""Deterministic independent core stimulus, with expected comparison counts."""

import hashlib
import random
from collections import Counter

from reference import (N, Q, PARAMS, R, montgomery, butterfly, transform,
                       convolution, sample, usehint)


def generate(path, compact=False, seeds=(17, 29, 43)):
    coverage = Counter()
    sampler_events = Counter()
    boundary = [0, 1, 2, 4190208, 4190209, Q-3, Q-2, Q-1]
    with path.open("x", encoding="ascii") as f:
        def record(kind, *parts):
            f.write(str(kind) + " " + " ".join(str(x) for x in parts) + "\n")
            coverage["operations"] += 1

        def hexes(values):
            return " ".join(f"{x:x}" for x in values)

        def ntt(a, inverse, label):
            expected = transform(a, inverse)
            record(2, int(inverse), N, 0, hexes(a), hexes(expected))
            coverage[label] += 1
            coverage["comparisons"] += 257
            return expected

        for seed in seeds[:1] if compact else seeds:
            rng = random.Random(seed)
            pairs = [(a, b) for a in boundary for b in boundary]
            pairs += [(rng.randrange(Q), rng.randrange(Q))
                      for _ in range(8 if compact else 4096)]
            for a, b in pairs:
                record(0, f"{a:x}", f"{b:x}", f"{montgomery(a,b):x}")
                coverage[f"montgomery_seed_{seed}"] += 1
                coverage["comparisons"] += 1
            for inverse in (False, True):
                triples = [(u, v, z) for u in (0, Q-1) for v in boundary
                           for z in (0, 1, R % Q, Q-1)]
                triples += [(rng.randrange(Q), rng.randrange(Q), rng.randrange(Q))
                            for _ in range(8 if compact else 1024)]
                for u, v, z in triples:
                    ea, eb = butterfly(inverse, u, v, z)
                    record(1, int(inverse), f"{u:x}", f"{v:x}", f"{z:x}",
                           f"{ea:x}", f"{eb:x}")
                    coverage[f"butterfly_{int(inverse)}_seed_{seed}"] += 1
                    coverage["comparisons"] += 2
            directed = [[0]*N, [1]*N, [Q-1]*N, [0,Q-1]*(N//2)]
            directed += [[int(j == i) for j in range(N)] for i in (0,1,127,255)]
            polys = directed[:2] if compact else directed + [
                [rng.randrange(Q) for _ in range(N)] for _ in range(16)]
            for poly in polys:
                forward = ntt(poly, False, f"forward_seed_{seed}")
                assert ntt(forward, True, f"inverse_forward_seed_{seed}") == poly
                if not compact:
                    inverse = ntt(poly, True, f"inverse_seed_{seed}")
                    assert ntt(inverse, False, f"forward_inverse_seed_{seed}") == poly
            for _ in range(0 if compact else 8):
                a = [rng.randrange(Q) for _ in range(N)]
                b = [rng.randrange(Q) for _ in range(N)]
                ah = ntt(a, False, f"convolution_a_seed_{seed}")
                bh = ntt(b, False, f"convolution_b_seed_{seed}")
                product = [x*y % Q for x,y in zip(ah,bh)]
                expected = convolution(a,b)
                assert transform(product, True) == expected
                record(2, 1, N, 0, hexes(product), hexes(expected))
                coverage[f"convolution_seed_{seed}"] += 1
                coverage["comparisons"] += 257
            for level in range(3):
                for op in range(5):
                    for case in range(1 if compact else 4):
                        seed_bytes = rng.randbytes(64)
                        # Distinct off-diagonal row/column encodings.
                        row = (case+1) % PARAMS[level]["k"]
                        col = (case+2) % PARAMS[level]["l"]
                        nonce = (row << 8) | col if op == 0 else rng.randrange(65536)
                        events = {}
                        expected = sample(op,level,seed_bytes,nonce,events)
                        for name, value in events.items():
                            sampler_events[f"op_{op}_{name}"] += value
                        record(3,op,level,f"{int.from_bytes(seed_bytes,'little'):0128x}",
                               f"{nonce:x}",0,hexes(expected))
                        coverage[f"sampler_{op}_level_{level}_seed_{seed}"] += 1
                        coverage["comparisons"] += 257
            for alg, rate in ((0,168),(1,136)):
                for length in (0,rate-1,rate,rate+1,3*rate+7):
                    message = rng.randbytes(length)
                    outlen = 3*rate+13
                    expected = (hashlib.shake_128 if alg==0 else hashlib.shake_256)(message).digest(outlen)
                    record(4,alg,length,outlen,hexes(message),hexes(expected))
                    coverage[f"xof_alg_{alg}_length_{length}_seed_{seed}"] += 1
                    coverage["comparisons"] += outlen
            for mode in (False, True):
                gamma2 = 95232 if mode else 261888
                values = set(boundary)
                for multiple in range(45 if mode else 17):
                    for delta in (-gamma2-1,-gamma2,-gamma2+1,-1,0,1,
                                  gamma2-1,gamma2,gamma2+1):
                        a = 2*gamma2*multiple+delta
                        if 0<=a<Q:
                            values.add(a)
                for a in sorted(values):
                    for hint in (False, True):
                        record(5,int(mode),int(hint),f"{a:x}",f"{usehint(a,hint,mode):x}")
                        coverage[f"usehint_mode_{int(mode)}_seed_{seed}"] += 1
                        coverage["comparisons"] += 1
            record(8)
        record(6,0,1,1,"0")
        coverage["comparisons"] += 1
        record(6,0,256,2,hexes([0]*255+[Q]))
        coverage["comparisons"] += 1
        for op in range(5,8):
            record(7,op,0,"0","0",1)
            coverage["comparisons"] += 1
        for op in range(5):
            record(7,op,3,"0","0",1)
            coverage["comparisons"] += 1
    return dict(coverage), dict(sampler_events)
