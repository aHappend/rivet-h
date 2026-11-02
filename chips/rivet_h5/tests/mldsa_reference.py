"""Pure contextual ML-DSA oracle derived from FIPS 204 algorithms.

The fast transform uses a twisted cyclic DFT, not the DUT's butterfly schedule.
It is cross-checked against direct root evaluation before cryptographic use.
"""

import hashlib
import random
from functools import lru_cache

from reference import (N, Q, PSI, PARAMS, bitreverse8, transform, sample,
                       decompose, usehint, pack_fields, unpack_fields)


def h(data, n):
    return hashlib.shake_256(data).digest(n)


@lru_cache(maxsize=2)
def cyclic_twiddles(inverse):
    omega = pow(PSI, 2, Q)
    if inverse:
        omega = pow(omega, -1, Q)
    return tuple(tuple(pow(omega, j*N//length, Q) for j in range(length//2))
                 for length in (2,4,8,16,32,64,128,256))


def cyclic_dft(a, inverse):
    out = [a[bitreverse8(i)] for i in range(N)]
    for stage, length in enumerate((2,4,8,16,32,64,128,256)):
        half = length//2
        twiddles = cyclic_twiddles(inverse)[stage]
        for base in range(0,N,length):
            for j in range(half):
                u = out[base+j]
                v = out[base+j+half]*twiddles[j] % Q
                out[base+j] = (u+v) % Q
                out[base+j+half] = (u-v) % Q
    if inverse:
        factor = pow(N,-1,Q)
        out = [x*factor % Q for x in out]
    return out


@lru_cache(maxsize=2)
def twist(inverse):
    return tuple(pow(PSI,-i if inverse else i,Q) for i in range(N))


def ntt(a):
    natural = cyclic_dft([x*t % Q for x,t in zip(a,twist(False))],False)
    return [natural[bitreverse8(i)] for i in range(N)]


def intt(a):
    natural = [a[bitreverse8(i)] for i in range(N)]
    return [x*t % Q for x,t in zip(cyclic_dft(natural,True),twist(True))]


def validate_transforms():
    rng = random.Random(917)
    for a in ([0]*N,[int(i==1) for i in range(N)],[rng.randrange(Q) for _ in range(N)]):
        assert ntt(a) == transform(a)
        assert intt(a) == transform(a,True)
        assert intt(ntt(a)) == a


def centered(a):
    return a if a <= Q//2 else a-Q


def norm(a):
    return max(abs(centered(x)) for x in a)


def matrix(rho, level):
    p = PARAMS[level]
    seed = rho+b"\0"*32
    return [[sample(0,level,seed,(row<<8)|col) for col in range(p["l"])]
            for row in range(p["k"])]


def matrix_product(a, zh):
    return [[sum(aij[i]*zj[i] for aij,zj in zip(row,zh)) % Q for i in range(N)]
            for row in a]


def vector_add(a,b,subtract=False):
    return [[(x-y if subtract else x+y) % Q for x,y in zip(ar,br)]
            for ar,br in zip(a,b)]


def challenge_product(ch, polys):
    return [intt([c*x % Q for c,x in zip(ch,ntt(poly))]) for poly in polys]


def encode_w1(rows, level):
    width = 6 if level==0 else 4
    return b"".join(pack_fields(row,width) for row in rows)


def decode_signature(signature, level):
    p = PARAMS[level]
    if len(signature) != p["sigbytes"]:
        raise ValueError("signature length")
    width = 18 if level==0 else 20
    stride = N*width//8
    z = [[(p["gamma1"]-v) % Q for v in unpack_fields(
        signature[p["cbytes"]+j*stride:p["cbytes"]+(j+1)*stride],width,N)]
        for j in range(p["l"])]
    hint_base = p["cbytes"]+p["l"]*stride
    index_bytes = signature[hint_base:hint_base+p["omega"]]
    endpoints = signature[hint_base+p["omega"]:]
    hints = []
    previous = 0
    for end in endpoints:
        if end < previous or end > p["omega"]:
            raise ValueError("hint endpoints")
        indices = list(index_bytes[previous:end])
        if any(a>=b for a,b in zip(indices,indices[1:])):
            raise ValueError("hint ordering")
        row = [0]*N
        for i in indices:
            row[i]=1
        hints.append(row)
        previous = end
    if any(index_bytes[previous:]):
        raise ValueError("unused hints")
    return signature[:p["cbytes"]],z,hints


def verify(pk, signature, message, context, level):
    p = PARAMS[level]
    if len(pk)!=p["pkbytes"] or len(context)>255 or len(signature)!=p["sigbytes"]:
        return dict(auth=False,status=2)
    # The admitted RTL checks z before hint encoding. Preserve that precedence.
    width = 18 if level==0 else 20
    stride = N*width//8
    z = [[(p["gamma1"]-v) % Q for v in unpack_fields(
        signature[p["cbytes"]+j*stride:p["cbytes"]+(j+1)*stride],width,N)]
        for j in range(p["l"])]
    if any(norm(poly)>=p["gamma1"]-p["beta"] for poly in z):
        return dict(auth=False,status=4)
    try:
        ctilde,z,hints = decode_signature(signature,level)
    except ValueError as exc:
        return dict(auth=False,status=3,reason=str(exc))
    rho = pk[:32]
    t1 = [unpack_fields(pk[32+320*i:32+320*(i+1)],10,N) for i in range(p["k"])]
    mu = h(h(pk,64)+b"\0"+bytes([len(context)])+context+message,64)
    c = sample(4,level,ctilde.ljust(64,b"\0"),0)
    ch = ntt(c)
    wh = matrix_product(matrix(rho,level),[ntt(row) for row in z])
    rows = []
    wraps = {"increment":0,"decrement":0}
    for row, t1row, hintrow in zip(wh,t1,hints):
        th = ntt([x*8192 for x in t1row])
        w = intt([(x-ci*ti) % Q for x,ci,ti in zip(row,ch,th)])
        high = []
        limit = 44 if level==0 else 16
        for a,hintbit in zip(w,hintrow):
            a1,a0 = decompose(a,p["gamma2"])
            if hintbit:
                wraps["increment"] += int(a1==limit-1 and a0>0)
                wraps["decrement"] += int(a1==0 and a0<=0)
            high.append(usehint(a,hintbit,level==0))
        rows.append(high)
    check = h(mu+encode_w1(rows,level),p["cbytes"])
    return dict(auth=check==ctilde,status=0 if check==ctilde else 5,
                challenge=check.hex(),mu=mu.hex(),hint_count=sum(map(sum,hints)),wraps=wraps)


def encode_signature(ctilde,z,hints,level):
    p = PARAMS[level]
    width = 18 if level==0 else 20
    packed_z = b"".join(pack_fields([p["gamma1"]-centered(x) for x in row],width) for row in z)
    indices = []
    endpoints = []
    for row in hints:
        indices.extend(i for i,bit in enumerate(row) if bit)
        endpoints.append(len(indices))
    if len(indices)>p["omega"]:
        raise ValueError("too many hints to encode")
    return ctilde+packed_z+bytes(indices).ljust(p["omega"],b"\0")+bytes(endpoints)


def keygen(seed,level):
    assert len(seed)==32
    p = PARAMS[level]
    expanded = h(seed+bytes([p["k"],p["l"]]),128)
    rho,rhoprime,key = expanded[:32],expanded[32:96],expanded[96:]
    a = matrix(rho,level)
    s1 = [sample(2,level,rhoprime,j) for j in range(p["l"])]
    s2 = [sample(2,level,rhoprime,p["l"]+j) for j in range(p["k"])]
    t = vector_add([intt(row) for row in matrix_product(a,[ntt(row) for row in s1])],s2)
    t1,t0 = [],[]
    for row in t:
        lows = [((x+4095) % 8192)-4095 for x in row]
        t1.append([(x-low)//8192 for x,low in zip(row,lows)])
        t0.append([low % Q for low in lows])
    pk = rho+b"".join(pack_fields(row,10) for row in t1)
    return pk,dict(level=level,rho=rho,key=key,tr=h(pk,64),s1=s1,s2=s2,t0=t0,a=a)


def sign(sk,message,context,rnd=bytes(32)):
    level = sk["level"]
    p = PARAMS[level]
    assert len(context)<=255 and len(rnd)==32
    mu = h(sk["tr"]+b"\0"+bytes([len(context)])+context+message,64)
    rhoprime = h(sk["key"]+rnd+mu,64)
    nonce = 0
    while nonce+p["l"]<=65536:
        y = [sample(3,level,rhoprime,nonce+j) for j in range(p["l"])]
        nonce += p["l"]
        w = [intt(row) for row in matrix_product(sk["a"],[ntt(row) for row in y])]
        w1 = [[decompose(x,p["gamma2"])[0] for x in row] for row in w]
        ctilde = h(mu+encode_w1(w1,level),p["cbytes"])
        ch = ntt(sample(4,level,ctilde.ljust(64,b"\0"),0))
        z = vector_add(y,challenge_product(ch,sk["s1"]))
        if any(norm(row)>=p["gamma1"]-p["beta"] for row in z):
            continue
        r = vector_add(w,challenge_product(ch,sk["s2"]),subtract=True)
        if any(max(abs(decompose(x,p["gamma2"])[1]) for x in row)>=p["gamma2"]-p["beta"] for row in r):
            continue
        ct0 = challenge_product(ch,sk["t0"])
        if any(norm(row)>=p["gamma2"] for row in ct0):
            continue
        a = vector_add(r,ct0)
        hints = [[int(decompose(x,p["gamma2"])[0]!=target) for x,target in zip(row,high)]
                 for row,high in zip(a,w1)]
        if sum(map(sum,hints))>p["omega"]:
            continue
        return encode_signature(ctilde,z,hints,level)
    raise RuntimeError("signing nonce range exhausted")


def crosscheck_kats(fixture):
    validate_transforms()
    outcomes = []
    for group in fixture["testGroups"]:
        level = ("ML-DSA-44","ML-DSA-65","ML-DSA-87").index(group["parameterSet"])
        for t in group["tests"]:
            observed = verify(bytes.fromhex(t["pk"]),bytes.fromhex(t["signature"]),
                              bytes.fromhex(t["message"]),bytes.fromhex(t["context"]),level)
            if observed["auth"] != t["testPassed"]:
                raise AssertionError(f"public FIPS204 KAT mismatch level={level} tcId={t['tcId']}: {observed}")
            outcomes.append(dict(level=level,tcId=t["tcId"],expected=t["testPassed"],observed=observed))
    for level in range(3):
        assert any(row["level"]==level and row["expected"] for row in outcomes)
        assert any(row["level"]==level and not row["expected"] for row in outcomes)
    return outcomes
