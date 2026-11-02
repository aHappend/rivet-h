"""Independent FIPS 202 and SHA chaining references; final oracles use hashlib."""

import hashlib
import hmac

MASK64 = (1 << 64) - 1
RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)


def rol64(value, amount):
    return ((value << amount) | (value >> ((64 - amount) % 64))) & MASK64


def keccak(state):
    """Lane order A[x,y], from the normative five transformations."""
    a = [[(state >> (64 * (x + 5 * y))) & MASK64 for y in range(5)]
         for x in range(5)]
    for constant in RC:
        columns = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4]
                   for x in range(5)]
        delta = [columns[(x - 1) % 5] ^ rol64(columns[(x + 1) % 5], 1)
                 for x in range(5)]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = rol64(a[x][y] ^ delta[x], ROT[x][y])
        for x in range(5):
            for y in range(5):
                a[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y])
        a[0][0] ^= constant
    return sum(a[x][y] << (64 * (x + 5 * y)) for x in range(5) for y in range(5))


def sponge_reference(message, algorithm, output_bytes):
    """Cross-check the separately coded permutation against hashlib itself."""
    rate = (136, 72, 168, 136)[algorithm]
    padded = bytearray(message)
    padded.append(0x06 if algorithm < 2 else 0x1F)
    padded.extend(bytes((-len(padded)) % rate))
    padded[-1] ^= 0x80
    state = 0
    for offset in range(0, len(padded), rate):
        state = keccak(state ^ int.from_bytes(padded[offset:offset + rate], "little"))
    result = bytearray()
    while len(result) < output_bytes:
        result.extend(state.to_bytes(200, "little")[:rate])
        if len(result) < output_bytes:
            state = keccak(state)
    return bytes(result[:output_bytes])


def digest(message, algorithm, output_bytes=None, key=b""):
    functions = (hashlib.sha256, None, hashlib.sha512)
    if output_bytes is None:
        return hmac.new(key, message, hashlib.sha256).digest() if algorithm == 1 \
            else functions[algorithm](message).digest()
    functions = (hashlib.sha3_256, hashlib.sha3_512, hashlib.shake_128, hashlib.shake_256)
    value = functions[algorithm](message)
    return value.digest(output_bytes) if algorithm >= 2 else value.digest()


IV256 = (
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
)
IV512 = (
    0x6A09E667F3BCC908, 0xBB67AE8584CAA73B, 0x3C6EF372FE94F82B,
    0xA54FF53A5F1D36F1, 0x510E527FADE682D1, 0x9B05688C2B3E6C1F,
    0x1F83D9ABFB41BD6B, 0x5BE0CD19137E2179,
)

# FIPS 180-4 constants are generated from exact integer cube roots, not RTL.
def primes(count):
    found = []
    n = 2
    while len(found) < count:
        if all(n % p for p in found if p * p <= n):
            found.append(n)
        n += 1
    return found


def icbrt(n):
    lo, hi = 0, 1 << ((n.bit_length() + 2) // 3)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if mid ** 3 <= n:
            lo = mid
        else:
            hi = mid
    return lo


K256 = tuple(icbrt(p << 96) & ((1 << 32) - 1) for p in primes(64))
K512 = tuple(icbrt(p << 192) & MASK64 for p in primes(80))


def sha_compress(block, chain, width):
    mask = (1 << width) - 1
    word_bytes = width // 8
    w = [int.from_bytes(block[i:i + word_bytes], "big")
         for i in range(0, len(block), word_bytes)]
    constants = K256 if width == 32 else K512

    def ror(v, n):
        return ((v >> n) | (v << (width - n))) & mask

    for i in range(16, len(constants)):
        x, y = w[i - 15], w[i - 2]
        if width == 32:
            s0, s1 = ror(x, 7) ^ ror(x, 18) ^ (x >> 3), ror(y, 17) ^ ror(y, 19) ^ (y >> 10)
        else:
            s0, s1 = ror(x, 1) ^ ror(x, 8) ^ (x >> 7), ror(y, 19) ^ ror(y, 61) ^ (y >> 6)
        w.append((w[i - 16] + s0 + w[i - 7] + s1) & mask)
    a, b, c, d, e, f, g, h = chain
    for word, constant in zip(w, constants):
        if width == 32:
            s0, s1 = ror(a, 2) ^ ror(a, 13) ^ ror(a, 22), ror(e, 6) ^ ror(e, 11) ^ ror(e, 25)
        else:
            s0, s1 = ror(a, 28) ^ ror(a, 34) ^ ror(a, 39), ror(e, 14) ^ ror(e, 18) ^ ror(e, 41)
        t1 = (h + s1 + ((e & f) ^ (~e & g)) + constant + word) & mask
        t2 = (s0 + ((a & b) ^ (a & c) ^ (b & c))) & mask
        a, b, c, d, e, f, g, h = (t1 + t2) & mask, a, b, c, (d + t1) & mask, e, f, g
    return tuple((old + new) & mask for old, new in zip(chain, (a, b, c, d, e, f, g, h)))


def chain_bytes(message, width, initial=None):
    block_bytes = width * 2
    state = initial if initial is not None else (IV256 if width == 32 else IV512)
    for offset in range(0, len(message) - len(message) % block_bytes, block_bytes):
        state = sha_compress(message[offset:offset + block_bytes], state, width)
    return b"".join(v.to_bytes(width // 8, "big") for v in state)


def context(message, algorithm, key=None, count_override=None, rhv2=False):
    """Canonical public context encoding, independent of DUT save output."""
    count = len(message) if count_override is None else count_override
    envelope = 0 if rhv2 else (0x52485633 << 2048) | (1 << 2080) | (algorithm << 2088)
    if algorithm == 2:
        chain = chain_bytes(message, 64)
        used = count % 128
        buffer = message[-used:] if used else b""
        return envelope | count | (used << 128) | (int.from_bytes(chain, "big") << 136) | \
            (int.from_bytes(buffer.ljust(128, b"\0"), "big") << 648)
    inner = outer = bytes(32)
    initial = IV256
    if key is not None:
        normalized = hashlib.sha256(key).digest() if len(key) > 64 else key
        normalized = normalized.ljust(64, b"\0")
        inner = chain_bytes(bytes(v ^ 0x36 for v in normalized), 32)
        outer = chain_bytes(bytes(v ^ 0x5C for v in normalized), 32)
        if algorithm == 1:
            initial = tuple(int.from_bytes(inner[i:i + 4], "big") for i in range(0, 32, 4))
    chain = chain_bytes(message, 32, initial)
    used = count % 64
    buffer = message[-used:] if used else b""
    return envelope | 0x52485632 | (1 << 32) | ((algorithm == 1) << 40) | \
        ((key is not None) << 41) | (count << 48) | (used << 112) | \
        (int.from_bytes(chain, "big") << 120) | (int.from_bytes(inner, "big") << 376) | \
        (int.from_bytes(outer, "big") << 632) | \
        (int.from_bytes(buffer.ljust(64, b"\0"), "big") << 888)


def merkle_root(page, siblings, index):
    node = hashlib.sha256(b"\0" + page).digest()
    for level, sibling in enumerate(siblings):
        pair = sibling + node if index & (1 << level) else node + sibling
        node = hashlib.sha256(b"\1" + pair).digest()
    return node


def self_check():
    assert digest(b"", 0).hex() == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert digest(b"abc", 0).hex() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert digest(b"", 0, 32).hex() == "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a"
    assert digest(b"abc", 0, 32).hex() == "3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532"
    assert digest(b"", 1, 64).hex() == (
        "a69f73cca23a9ac5c8b567dc185a756e97c982164fe25859e0d1dcc1475c80a615"
        "b2123af1f5f94c11e3e9402c3ac558f500199d95b6d3e301758586281dcd26")
    assert digest(b"abc", 1, 64).hex() == (
        "b751850b1a57168a5693cd924b6b096e08f621827444f70d884f5d0240d2712e10"
        "e116e9192af3c91a7ec57647e3934057340b4cf408d5a56592f8274eec53f0")
    assert digest(b"", 2, 16).hex() == "7f9c2ba4e88f827d616045507605853e"
    assert digest(b"abc", 2, 16).hex() == "5881092dd818bf5cf8a3ddb793fbcba7"
    assert digest(b"", 3, 32).hex() == "46b9dd2b0ba88d13233b3feb743eeb243fcd52ea62b81b82b50c27646ed5762f"
    assert digest(b"abc", 3, 32).hex() == "483366601360a8771c6863080cc4114d8db44530f8f1e1ee4f94ea37e78b5739"
    for width, function in ((32, hashlib.sha256), (64, hashlib.sha512)):
        for message in (b"", b"abc", bytes(range(256))):
            block = width * 2
            length_bytes = width // 4
            padded = message + b"\x80"
            padded += bytes((block - length_bytes - len(padded)) % block)
            padded += (len(message) * 8).to_bytes(length_bytes, "big")
            assert chain_bytes(padded, width) == function(message).digest()
    for algorithm in range(4):
        for message in (b"", b"abc", bytes(range(256))):
            n = (32, 64, 400, 400)[algorithm]
            assert sponge_reference(message, algorithm, n) == digest(message, algorithm, n)
