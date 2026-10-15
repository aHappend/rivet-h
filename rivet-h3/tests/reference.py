"""Independent FIPS references for serialized prefixes and artificial counts.

Ordinary message expectations always come from hashlib/hmac. Constants below
are generated from the FIPS prime-root definition, not read from DUT sources.
"""

import hashlib
import hmac
import math
from functools import lru_cache


def primes(n):
    result = []
    p = 2
    while len(result) < n:
        if all(p % q for q in result if q * q <= p):
            result.append(p)
        p += 1
    return result


def root_floor(n, degree):
    lo, hi = 0, 1 << ((n.bit_length() + degree - 1) // degree)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if mid**degree <= n:
            lo = mid
        else:
            hi = mid
    return lo


PRIMES = primes(80)


def iv(bits):
    mask = (1 << bits) - 1
    return [math.isqrt(p << (2 * bits)) & mask for p in PRIMES[:8]]


@lru_cache(maxsize=2)
def constants(bits):
    return tuple(root_floor(p << (3 * bits), 3) & ((1 << bits) - 1)
                 for p in PRIMES[:64 if bits == 32 else 80])


def compress(chain, block, bits):
    size = bits // 8
    mask = (1 << bits) - 1
    round_constants = constants(bits)

    def r(x, n):
        return ((x >> n) | (x << (bits - n))) & mask

    w = [int.from_bytes(block[i:i + size], "big")
         for i in range(0, len(block), size)]
    assert len(w) == 16
    s0, s1 = ((7, 18, 3), (17, 19, 10)) if bits == 32 else (
        (1, 8, 7), (19, 61, 6))
    b0, b1 = ((2, 13, 22), (6, 11, 25)) if bits == 32 else (
        (28, 34, 39), (14, 18, 41))
    for t in range(16, len(round_constants)):
        x, y = w[t - 15], w[t - 2]
        w.append((w[t - 16] + (r(x, s0[0]) ^ r(x, s0[1]) ^ (x >> s0[2]))
                  + w[t - 7] + (r(y, s1[0]) ^ r(y, s1[1]) ^ (y >> s1[2]))) & mask)
    a, b, c, d, e, f, g, h = chain
    for k, word in zip(round_constants, w):
        t1 = (h + (r(e, b1[0]) ^ r(e, b1[1]) ^ r(e, b1[2]))
              + ((e & f) ^ ((~e) & g)) + k + word) & mask
        t2 = ((r(a, b0[0]) ^ r(a, b0[1]) ^ r(a, b0[2]))
              + ((a & b) ^ (a & c) ^ (b & c))) & mask
        a, b, c, d, e, f, g, h = (
            (t1 + t2) & mask, a, b, c, (d + t1) & mask, e, f, g)
    return [(x + y) & mask for x, y in zip(chain, (a, b, c, d, e, f, g, h))]


def pack(words, bits):
    return b"".join(x.to_bytes(bits // 8, "big") for x in words)


def finish(chain, tail, count, bits):
    block = bits * 2
    length_bytes = bits // 4
    data = tail + b"\x80"
    data += bytes((-len(data) - length_bytes) % block)
    data += (count * 8).to_bytes(length_bytes, "big")
    for off in range(0, len(data), block):
        chain = compress(chain, data[off:off + block], bits)
    return pack(chain, bits)


def seeds(key):
    if len(key) > 64:
        key = hashlib.sha256(key).digest()
    key = key.ljust(64, b"\0")
    return (compress(iv(32), bytes(x ^ 0x36 for x in key), 32),
            compress(iv(32), bytes(x ^ 0x5c for x in key), 32))


def envelope(payload, alg):
    return payload | (0x52485633 << 2048) | (1 << 2080) | (alg << 2088)


def context(alg, prefix=b"", key=b"", count=None, chain=None, legacy=False,
            cached=False):
    bits = 64 if alg == 2 else 32
    block = bits * 2
    inner, outer = seeds(key) if alg == 1 or cached else ([0] * 8, [0] * 8)
    state = inner[:] if alg == 1 else iv(bits)
    for off in range(0, len(prefix) - len(prefix) % block, block):
        state = compress(state, prefix[off:off + block], bits)
    tail = prefix[len(prefix) - len(prefix) % block:]
    if chain is not None:
        state = chain
    count = len(prefix) if count is None else count
    assert len(tail) == count % block
    integer = lambda data: int.from_bytes(data, "big")
    if alg == 2:
        payload = (count | (len(tail) << 128)
                   | (integer(pack(state, bits)) << 136)
                   | (integer(tail.ljust(block, b"\0")) << 648))
    else:
        payload = (0x52485632 | (1 << 32) | ((alg == 1) << 40)
                   | ((alg == 1 or cached) << 41) | (count << 48)
                   | (len(tail) << 112) | (integer(pack(state, bits)) << 120)
                   | (integer(pack(inner, 32)) << 376)
                   | (integer(pack(outer, 32)) << 632)
                   | (integer(tail.ljust(block, b"\0")) << 888))
    return payload if legacy else envelope(payload, alg)


def synthetic_digest(alg, count, tail, chain, key=b""):
    bits = 64 if alg == 2 else 32
    digest = finish(chain, tail, count + (64 if alg == 1 else 0), bits)
    if alg == 1:
        _, outer = seeds(key)
        digest = finish(outer, digest, 96, 32)
    return digest


def digest(alg, data, key=b""):
    if alg == 1:
        return hmac.new(key, data, hashlib.sha256).digest()
    return (hashlib.sha512 if alg == 2 else hashlib.sha256)(data).digest()


def self_check():
    for bits in (32, 64):
        for data in (b"", b"abc", bytes(range(255)), b"a" * 1024):
            block = bits * 2
            chain = iv(bits)
            for off in range(0, len(data) - len(data) % block, block):
                chain = compress(chain, data[off:off + block], bits)
            tail = data[len(data) - len(data) % block:]
            assert finish(chain, tail, len(data), bits) == digest(
                2 if bits == 64 else 0, data)
    for key in (b"", b"k", b"x" * 131):
        for data in (b"", b"abc", b"x" * 129):
            inner, _ = seeds(key)
            chain = inner
            for off in range(0, len(data) - len(data) % 64, 64):
                chain = compress(chain, data[off:off + 64], 32)
            assert synthetic_digest(1, len(data), data[len(data) - len(data) % 64:],
                                    chain, key) == digest(1, data, key)
