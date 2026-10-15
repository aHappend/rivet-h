"""Independent FIPS 180-4 state oracle; complete-message oracles use hashlib/hmac."""
import hashlib
import hmac
import random
import struct

IV = (0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
      0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19)
K = (
    0x428A2F98, 0x71374491, 0xB5C0FBCF, 0xE9B5DBA5,
    0x3956C25B, 0x59F111F1, 0x923F82A4, 0xAB1C5ED5,
    0xD807AA98, 0x12835B01, 0x243185BE, 0x550C7DC3,
    0x72BE5D74, 0x80DEB1FE, 0x9BDC06A7, 0xC19BF174,
    0xE49B69C1, 0xEFBE4786, 0x0FC19DC6, 0x240CA1CC,
    0x2DE92C6F, 0x4A7484AA, 0x5CB0A9DC, 0x76F988DA,
    0x983E5152, 0xA831C66D, 0xB00327C8, 0xBF597FC7,
    0xC6E00BF3, 0xD5A79147, 0x06CA6351, 0x14292967,
    0x27B70A85, 0x2E1B2138, 0x4D2C6DFC, 0x53380D13,
    0x650A7354, 0x766A0ABB, 0x81C2C92E, 0x92722C85,
    0xA2BFE8A1, 0xA81A664B, 0xC24B8B70, 0xC76C51A3,
    0xD192E819, 0xD6990624, 0xF40E3585, 0x106AA070,
    0x19A4C116, 0x1E376C08, 0x2748774C, 0x34B0BCB5,
    0x391C0CB3, 0x4ED8AA4A, 0x5B9CCA4F, 0x682E6FF3,
    0x748F82EE, 0x78A5636F, 0x84C87814, 0x8CC70208,
    0x90BEFFFA, 0xA4506CEB, 0xBEF9A3F7, 0xC67178F2)
MASK = (1 << 32) - 1
SHA_LIMIT = (1 << 61) - 1
HMAC_LIMIT = SHA_LIMIT - 64


def rotate(x, n):
    return ((x >> n) | (x << (32 - n))) & MASK


def compress(state, block):
    assert len(block) == 64
    w = list(struct.unpack(">16I", block))
    for t in range(16, 64):
        x, y = w[t - 15], w[t - 2]
        w.append((w[t - 16] + (rotate(x, 7) ^ rotate(x, 18) ^ (x >> 3))
                  + w[t - 7] + (rotate(y, 17) ^ rotate(y, 19) ^ (y >> 10))) & MASK)
    a, b, c, d, e, f, g, hh = state
    for t in range(64):
        t1 = (hh + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25))
              + ((e & f) ^ ((~e) & g)) + K[t] + w[t]) & MASK
        t2 = ((rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22))
              + ((a & b) ^ (a & c) ^ (b & c))) & MASK
        a, b, c, d, e, f, g, hh = (
            (t1 + t2) & MASK, a, b, c, (d + t1) & MASK, e, f, g)
    return tuple((x + y) & MASK for x, y in zip(state, (a, b, c, d, e, f, g, hh)))


def state_int(state):
    return int.from_bytes(struct.pack(">8I", *state), "big")


def int_state(value):
    return struct.unpack(">8I", value.to_bytes(32, "big"))


def finish(chain, tail, total):
    assert len(tail) == total % 64
    padded = tail + b"\x80"
    padded += b"\0" * ((56 - len(padded)) % 64)
    padded += (total * 8).to_bytes(8, "big")
    for i in range(0, len(padded), 64):
        chain = compress(chain, padded[i:i + 64])
    return state_int(chain).to_bytes(32, "big")


def seeds(key):
    norm = hashlib.sha256(key).digest() if len(key) > 64 else key
    norm = norm.ljust(64, b"\0")
    return (compress(IV, bytes(x ^ 0x36 for x in norm)),
            compress(IV, bytes(x ^ 0x5C for x in norm)))


def context(prefix=b"", key=None, count=None, chain=None, installed_key=None):
    mode = key is not None
    owned_key = key if mode else installed_key
    inner, outer = seeds(owned_key) if owned_key is not None else ((0,) * 8, (0,) * 8)
    current = inner if mode else IV
    for i in range(0, len(prefix) - len(prefix) % 64, 64):
        current = compress(current, prefix[i:i + 64])
    total = len(prefix) if count is None else count
    tail = prefix[-(len(prefix) % 64):] if len(prefix) % 64 else b""
    assert len(tail) == total % 64
    current = current if chain is None else chain
    return (0x52485632 | (1 << 32) | (int(mode) << 40) | (int(owned_key is not None) << 41)
            | (total << 48) | (len(tail) << 112) | (state_int(current) << 120)
            | (state_int(inner) << 376) | (state_int(outer) << 632)
            | (int.from_bytes(tail.ljust(64, b"\0"), "big") << 888))


def digest(message, key=None):
    return (hashlib.sha256(message).digest() if key is None
            else hmac.new(key, message, hashlib.sha256).digest())


def synthetic_digest(image, suffix):
    count = (image >> 48) & ((1 << 64) - 1)
    used = (image >> 112) & 255
    chain = int_state((image >> 120) & ((1 << 256) - 1))
    tail = ((image >> 888) & ((1 << 512) - 1)).to_bytes(64, "big")[:used] + suffix
    while len(tail) >= 64:
        chain = compress(chain, tail[:64])
        tail = tail[64:]
    mode = (image >> 40) & 1
    result = finish(chain, tail, count + len(suffix) + 64 * mode)
    if mode:
        outer = int_state((image >> 632) & ((1 << 256) - 1))
        result = finish(outer, result, 96)
    return result


def self_test():
    rng = random.Random(41021)
    lengths = list(range(32)) + [55, 56, 57, 63, 64, 65, 119, 120, 127, 128, 129, 1024]
    for n in lengths:
        msg = rng.randbytes(n)
        chain = IV
        for i in range(0, n - n % 64, 64):
            chain = compress(chain, msg[i:i + 64])
        tail = msg[n - n % 64:]
        assert finish(chain, tail, n) == hashlib.sha256(msg).digest()
        for key in (b"", b"key", rng.randbytes(131)):
            assert synthetic_digest(context(msg, key), b"") == digest(msg, key)
    return {"sha_complete_crosschecks": len(lengths), "hmac_state_crosschecks": 3 * len(lengths)}
