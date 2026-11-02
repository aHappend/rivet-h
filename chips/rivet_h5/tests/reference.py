"""Independent mathematical and byte-level RIVET-H5 reference definitions.

No RTL tables, implementation state, or inherited test code is used.
"""

import hashlib
import functools

N = 256
Q = 8380417
PSI = 1753
R = 1 << 32
R_INV = pow(R, -1, Q)
PARAMS = (
    dict(k=4, l=4, eta=2, tau=39, beta=78, gamma1=131072,
         gamma2=95232, omega=80, cbytes=32, pkbytes=1312, sigbytes=2420),
    dict(k=6, l=5, eta=4, tau=49, beta=196, gamma1=524288,
         gamma2=261888, omega=55, cbytes=48, pkbytes=1952, sigbytes=3309),
    dict(k=8, l=7, eta=2, tau=60, beta=120, gamma1=524288,
         gamma2=261888, omega=75, cbytes=64, pkbytes=2592, sigbytes=4627),
)


def montgomery(a, b):
    assert 0 <= a < Q and 0 <= b < Q
    return a * b * R_INV % Q


def butterfly(inverse, u, v, zeta):
    if inverse:
        return (u + v) % Q, montgomery((u - v) % Q, zeta)
    t = montgomery(v, zeta)
    return (u + t) % Q, (u - t) % Q


def bitreverse8(i):
    return int(f"{i:08b}"[::-1], 2)


@functools.lru_cache(maxsize=2)
def evaluation_matrix(inverse):
    roots = [pow(PSI, 2 * bitreverse8(i) + 1, Q) for i in range(N)]
    if not inverse:
        return tuple(tuple(pow(root, j, Q) for j in range(N)) for root in roots)
    factor = pow(N, -1, Q)
    return tuple(tuple(pow(root, -j, Q) * factor % Q for root in roots)
                 for j in range(N))


def transform(a, inverse=False):
    assert len(a) == N and all(0 <= x < Q for x in a)
    return [sum(x * y for x, y in zip(a, row)) % Q
            for row in evaluation_matrix(inverse)]


def convolution(a, b):
    """Schoolbook negacyclic product, without using either transform."""
    out = [0] * N
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            ij = i + j
            out[ij % N] += x * y * (1 if ij < N else -1)
    return [x % Q for x in out]


class XOF:
    """Hashlib's prefix API converted to an unbounded byte cursor."""

    def __init__(self, data, alg):
        self.hash = (hashlib.shake_128 if alg == 0 else hashlib.shake_256)(data)
        self.offset = 0
        self.prefix = b""
        self.rate = 168 if alg == 0 else 136

    def read(self, n):
        end = self.offset + n
        if end > len(self.prefix):
            self.prefix = self.hash.digest(max(end, 2 * max(256, len(self.prefix))))
        result = self.prefix[self.offset:end]
        self.offset = end
        return result


def sample(op, level, seed, nonce, counters=None):
    """FIPS 204 samplers and separately specified SHAKE256 uniform mode."""
    assert op in range(5) and level in range(3) and len(seed) == 64
    p = PARAMS[level]
    size = 32 if op == 0 else p["cbytes"] if op == 4 else 64
    data = seed[:size] + (b"" if op == 4 else nonce.to_bytes(2, "little"))
    xof = XOF(data, 0 if op == 0 else 1)
    out = []
    rejected = 0
    swaps = 0
    self_swaps = 0
    if op in (0, 1):
        while len(out) < N:
            candidate = int.from_bytes(xof.read(3), "little") & 0x7FFFFF
            if candidate < Q:
                out.append(candidate)
            else:
                rejected += 1
    elif op == 2:
        while len(out) < N:
            byte = xof.read(1)[0]
            for t in (byte & 15, byte >> 4):
                if t < (15 if p["eta"] == 2 else 9):
                    out.append((p["eta"] - (t % 5 if p["eta"] == 2 else t)) % Q)
                    if len(out) == N:
                        break
                else:
                    rejected += 1
    elif op == 3:
        width = 18 if level == 0 else 20
        packed = int.from_bytes(xof.read(N * width // 8), "little")
        out = [(p["gamma1"] - ((packed >> (i * width)) & ((1 << width) - 1))) % Q
               for i in range(N)]
    else:
        out = [0] * N
        signs = int.from_bytes(xof.read(8), "little")
        for i in range(N - p["tau"], N):
            b = xof.read(1)[0]
            while b > i:
                rejected += 1
                b = xof.read(1)[0]
            swaps += int(out[b] != 0)
            self_swaps += int(b == i)
            out[i] = out[b]
            out[b] = (1 - 2 * (signs & 1)) % Q
            signs >>= 1
    if counters is not None:
        counters.update(bytes=xof.offset, rejected=rejected, swaps=swaps,
                        self_swaps=self_swaps, rate_blocks=(xof.offset - 1) // xof.rate + 1)
    assert len(out) == N and all(0 <= x < Q for x in out)
    return out


def decompose(a, gamma2):
    assert 0 <= a < Q
    alpha = 2 * gamma2
    a0 = a % alpha
    if a0 > gamma2:
        a0 -= alpha
    if a - a0 == Q - 1:
        return 0, a0 - 1
    return (a - a0) // alpha, a0


def usehint(a, hint, level44):
    gamma2 = 95232 if level44 else 261888
    a1, a0 = decompose(a, gamma2)
    return (a1 + (1 if a0 > 0 else -1)) % (44 if level44 else 16) if hint else a1


def pack_fields(values, width):
    assert all(0 <= v < 1 << width for v in values)
    bits = sum(v << (width * i) for i, v in enumerate(values))
    return bits.to_bytes((len(values) * width + 7) // 8, "little")


def unpack_fields(data, width, count):
    assert len(data) * 8 == width * count
    bits = int.from_bytes(data, "little")
    return [(bits >> (width * i)) & ((1 << width) - 1) for i in range(count)]
