"""Independent FIPS 180-4, sections 4--6, unsigned SHA-256 reference."""
import hashlib
import struct

MASK = (1 << 32) - 1
IV = (
    0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
    0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19,
)
K = tuple(int(x, 16) for x in """
428a2f98 71374491 b5c0fbcf e9b5dba5 3956c25b 59f111f1 923f82a4 ab1c5ed5
d807aa98 12835b01 243185be 550c7dc3 72be5d74 80deb1fe 9bdc06a7 c19bf174
e49b69c1 efbe4786 0fc19dc6 240ca1cc 2de92c6f 4a7484aa 5cb0a9dc 76f988da
983e5152 a831c66d b00327c8 bf597fc7 c6e00bf3 d5a79147 06ca6351 14292967
27b70a85 2e1b2138 4d2c6dfc 53380d13 650a7354 766a0abb 81c2c92e 92722c85
a2bfe8a1 a81a664b c24b8b70 c76c51a3 d192e819 d6990624 f40e3585 106aa070
19a4c116 1e376c08 2748774c 34b0bcb5 391c0cb3 4ed8aa4a 5b9cca4f 682e6ff3
748f82ee 78a5636f 84c87814 8cc70208 90befffa a4506ceb bef9a3f7 c67178f2
""".split())

# Published vectors: FIPS 180-4 and NIST's SHA examples / SHAVS:
# https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program/secure-hashing
# https://www.di-mgt.com.au/sha_testvectors.html (readable vector transcription)
PUBLISHED = (
    (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    (b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
     "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
    (b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmn"
     b"hijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu",
     "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1"),
    (b"a" * 1_000_000,
     "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"),
)


def ror(x, n):
    return ((x >> n) | (x << (32 - n))) & MASK


def padded(data):
    assert len(data) <= (1 << 61) - 1
    return data + b"\x80" + bytes((55 - len(data)) % 64) + struct.pack(">Q", len(data) * 8)


def expand(block):
    w = list(struct.unpack(">16I", block))
    for t in range(16, 64):
        x, y = w[t - 15], w[t - 2]
        s0 = ror(x, 7) ^ ror(x, 18) ^ (x >> 3)
        s1 = ror(y, 17) ^ ror(y, 19) ^ (y >> 10)
        w.append((w[t - 16] + s0 + w[t - 7] + s1) & MASK)
    return w


def compress(state, w):
    a, b, c, d, e, f, g, h = state
    for t in range(64):
        s1 = ror(e, 6) ^ ror(e, 11) ^ ror(e, 25)
        ch = (e & f) ^ ((~e) & g)
        t1 = (h + s1 + ch + K[t] + w[t]) & MASK
        s0 = ror(a, 2) ^ ror(a, 13) ^ ror(a, 22)
        maj = (a & b) ^ (a & c) ^ (b & c)
        t2 = (s0 + maj) & MASK
        a, b, c, d, e, f, g, h = (
            (t1 + t2) & MASK, a, b, c, (d + t1) & MASK, e, f, g,
        )
    return tuple((x + y) & MASK for x, y in zip(state, (a, b, c, d, e, f, g, h)))


def reference(data, detail=False):
    state = IV
    trace = []
    raw = padded(data)
    for offset in range(0, len(raw), 64):
        block = raw[offset:offset + 64]
        w = expand(block)
        incoming = state
        state = compress(state, w)
        if detail:
            trace.append({
                "block": block.hex(), "incoming": state_hex(incoming),
                "schedule": w, "outgoing": state_hex(state),
            })
    digest = state_hex(state)
    assert digest == hashlib.sha256(data).hexdigest(), "independent reference/hashlib disagreement"
    return digest, trace


def state_hex(state):
    return "".join(f"{word:08x}" for word in state)
