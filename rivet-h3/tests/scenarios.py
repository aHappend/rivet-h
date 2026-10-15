"""Executable requirement matrix and public transaction stimulus."""

import collections
import hashlib
import random

from reference import context, digest, iv, synthetic_digest

SHA512_LENGTHS = (0, 1, 3, 110, 111, 112, 113, 127, 128, 129,
                 239, 240, 255, 256, 257, 1024)
SHA256_LENGTHS = (0, 1, 3, 55, 56, 63, 64, 65, 119, 120, 127, 128, 129, 1024)
HMAC_LENGTHS = (0, 1, 55, 56, 63, 64, 65, 129)
KEY_LENGTHS = (0, 1, 63, 64, 65, 131)


class Program:
    def __init__(self, path, partial=0, seed=17, standalone=False):
        self.path = path
        self.file = path.open("w")
        self.partial = partial
        self.rng = random.Random(seed)
        self.standalone = standalone
        self.count = 0
        self.coverage = collections.Counter()
        self.messages = []
        self.instructions = 0
        self.check_ids = {}
        self.required_checks = collections.Counter()
        self.emit(17, value=seed)

    def emit(self, op, a=0, b=0, c=0, d=0, e=0, value=0):
        self.file.write(" ".join(f"{v:x}" for v in (op, a, b, c, d, e, value)) + "\n")
        self.instructions += 1

    def wait(self, cycles):
        self.emit(0, cycles)

    def cmd(self, ch, op, value=0):
        self.emit(1, ch, op, value=value)

    def reset(self):
        self.emit(6)

    def ready(self, mr=1, cr=1, randomize=0):
        self.emit(7, mr, cr, randomize)

    def drain(self):
        self.emit(5)

    def cover(self, name):
        if name not in self.check_ids:
            self.check_ids[name] = len(self.check_ids)
        self.required_checks[name] += 1
        self.emit(25, self.check_ids[name])

    def bytes(self, ch, data, key=False, final=True, bubbles=True):
        offset = 0
        if not data:
            if final:
                self.emit(3 if key else 2, ch, 0, 1)
            return
        while offset < len(data):
            n = min(4, len(data) - offset)
            if self.partial and self.rng.randrange(8) == 0:
                n = self.rng.randint(1, n)
            last = final and offset + n == len(data)
            self.emit(3 if key else 2, ch, (15 << (4 - n)) & 15, int(last),
                      value=int.from_bytes(data[offset:offset + n].ljust(4, b"\0"), "big"))
            offset += n
            if bubbles and self.rng.randrange(16) == 0:
                self.wait(self.rng.randint(1, 5))

    def expect(self, ch, alg, data, key=b"", expected=None, category="extra"):
        self.count += 1
        answer = digest(alg, data, key) if expected is None else expected
        self.emit(4, ch, alg, self.count, len(data), value=int.from_bytes(answer, "big"))
        self.messages.append(dict(id=self.count, channel=ch, algorithm=alg,
                                  length=len(data), key_length=len(key),
                                  category=category, sha256=hashlib.sha256(data).hexdigest(),
                                  expected=answer.hex()))
        self.coverage[category] += 1

    def setup(self, ch, alg, key=b""):
        self.cmd(ch, 5)
        if alg == 1:
            self.emit(14, 10000 + self.count)
            self.cmd(ch, 1)
            self.bytes(ch, key, key=True)
            self.cmd(ch, 2)
            self.emit(14, 20000 + self.count)
        else:
            self.cmd(ch, 6 if alg == 2 else 0)

    def message(self, ch, alg, data, key=b"", category="extra", setup=True):
        if setup:
            self.setup(ch, alg, key)
        self.expect(ch, alg, data, key, category=category)
        self.bytes(ch, data)
        self.drain()
        self.emit(10, 0, 1)

    def snapshot(self, ch, alg, prefix, key=b"", slot=0):
        expected = context(alg, prefix, key, legacy=self.standalone)
        self.emit(8, ch, slot, value=expected)
        self.cmd(ch, 3)

    def close(self):
        self.file.close()
        return dict(instructions=self.instructions, expected_messages=self.count,
                    coverage=dict(self.coverage), messages=self.messages,
                    check_ids=self.check_ids, required_checks=dict(self.required_checks))


def random_data(p, n):
    return p.rng.randbytes(n)


def published(p):
    sha_vectors = [
        (0, b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        (0, b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
        (0, b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
         "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
        (2, b"", "cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce"
         "47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e"),
        (2, b"abc", "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
         "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f"),
        (2, b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmno"
         b"ijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu",
         "8e959b75dae313da8cf4f72814fc143f8f7779c6eb9f7fa17299aeadb6889018"
         "501d289e4900f7e4331b99dec4b5433ac7d329eeb6dd26545e96e55b874be909")]
    hmac_vectors = [
        (b"\x0b" * 20, b"Hi There",
         "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"),
        (b"Jefe", b"what do ya want for nothing?",
         "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"),
        (b"\xaa" * 20, b"\xdd" * 50,
         "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe"),
        (bytes(range(1, 26)), b"\xcd" * 50,
         "82558a389a443c0ea4cc819899f2083a85f0faa3e578f8077a2e3ff46729665b"),
        (b"\xaa" * 131, b"Test Using Larger Than Block-Size Key - Hash Key First",
         "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"),
        (b"\xaa" * 131,
         b"This is a test using a larger than block-size key and a larger than "
         b"block-size data. The key needs to be hashed before being used by the HMAC algorithm.",
         "9b09ffa71b942fcb27635fbcd5b0e944bfdc63644f0713938a7f51535c3a35e2")]
    for alg, data, answer in sha_vectors:
        if p.standalone and alg == 2:
            continue
        assert digest(alg, data).hex() == answer
        p.setup(0, alg)
        p.expect(0, alg, data, expected=bytes.fromhex(answer), category="published_sha")
        p.bytes(0, data)
        p.drain()
    for key, data, answer in hmac_vectors:
        assert digest(1, data, key).hex() == answer
        p.setup(0, 1, key)
        p.expect(0, 1, data, key, bytes.fromhex(answer), "published_hmac")
        p.bytes(0, data)
        p.drain()


def matrix(p):
    for ch in range(4):
        for alg, lengths in ((0, SHA256_LENGTHS), (2, SHA512_LENGTHS)):
            for n in lengths:
                p.message(ch, alg, random_data(p, n), category="directed")
        for kn in KEY_LENGTHS:
            key = random_data(p, kn)
            p.setup(ch, 1, key)
            for n in HMAC_LENGTHS:
                p.message(ch, 1, random_data(p, n), key, "directed", setup=False)
    for alg in range(3):
        for j in range(24):
            n = p.rng.randint(0, 8192)
            p.message(j % 4, alg, random_data(p, n), random_data(p, 65),
                      category="random")
        p.message(alg, alg, random_data(p, 65536), b"long-key" * 17, "long")


def contexts(p):
    algorithms = (0, 1) if p.standalone else (0, 1, 2)
    for alg in algorithms:
        block = 128 if alg == 2 else 64
        for n in (0, 1, block - 1, block, block + 1):
            prefix = random_data(p, n)
            suffix = random_data(p, 149)
            key = b"snapshot key" * 7
            p.setup(0, alg, key)
            if p.partial or n % 4 == 0:
                p.bytes(0, prefix, final=False)
            else:
                p.cmd(0, 4, context(alg, prefix, key, legacy=p.standalone))
            p.snapshot(0, alg, prefix, key)
            p.drain()
            p.cover(f"context_save_a{alg}_n{n}")
            p.expect(0, alg, suffix, key, digest(alg, prefix + suffix, key),
                     "context_continue")
            p.bytes(0, suffix)
            p.drain()
            p.cover(f"context_continue_a{alg}_n{n}")
            target = 0 if p.standalone else 3
            p.cmd(target, 5)
            p.bytes(target, b"drop", final=False)
            p.emit(9, target, 0, 0)
            p.expect(target, alg, suffix, key, digest(alg, prefix + suffix, key),
                     "context_migration")
            p.bytes(target, suffix)
            p.drain()
            p.cover(f"context_migrate_a{alg}_n{n}")
            p.emit(10, 0, 1)
            p.cmd(target, 5)
            if alg != 2 and not p.standalone:
                p.cmd(2, 4, context(alg, prefix, key, legacy=True))
                p.expect(2, alg, suffix, key, digest(alg, prefix + suffix, key),
                         "legacy_import")
                p.bytes(2, suffix)
                p.drain()
    p.cmd(0, 5)


def limits(p):
    for alg in ((0, 1) if p.standalone else (0, 1, 2)):
        block = 128 if alg == 2 else 64
        maximum = (1 << (125 if alg == 2 else 61)) - (65 if alg == 1 else 1)
        key = b"limit seed"
        counts = [maximum - 3, maximum - 64]
        if p.partial:
            counts.append(maximum)
        if alg == 2:
            counts.append((1 << 65) + 111)
        for count in counts:
            used = count % block
            tail = random_data(p, used)
            state = [x ^ 0x12345678 for x in iv(64 if alg == 2 else 32)]
            value = context(alg, tail, key, count=count, chain=state,
                            legacy=p.standalone)
            p.cmd(0, 5)
            p.cmd(0, 4, value)
            suffix = b"" if p.partial else b"x"
            p.expect(0, alg, suffix, key,
                     synthetic_digest(alg, count + len(suffix), tail + suffix,
                                      state, key), "high_count")
            p.bytes(0, suffix)
            p.drain()
            p.cover(f"high_count_a{alg}_count{count}")
            p.cmd(0, 5)
        value = context(alg, random_data(p, maximum % block), key,
                        count=maximum, chain=iv(64 if alg == 2 else 32),
                        legacy=p.standalone)
        p.cmd(0, 4, value)
        p.bytes(0, b"x")
        p.emit(10, 1, 4)
        p.cover(f"length_overflow_a{alg}")
        p.cmd(0, 5)
        p.emit(10, 0, 1)


def mask_errors(p):
    for alg in ((0, 1) if p.standalone else (0, 1, 2)):
        for keyport in ((False, True) if alg == 1 else (False,)):
            for last in (0, 1):
                for keep in range(16):
                    p.setup(0, alg, b"masks")
                    if keyport:
                        p.cmd(0, 0)
                        p.cmd(0, 1)
                    legal = keep in (8, 12, 14, 15) and (
                        last or p.partial or keep == 15)
                    legal |= keep == 0 and bool(last)
                    n = {8: 1, 12: 2, 14: 3, 15: 4}.get(keep, 0)
                    if legal and last and not keyport:
                        p.expect(0, alg, b"abcd"[:n], b"masks",
                                 category="legal_mask")
                    p.emit(3 if keyport else 2, 0, keep, last,
                           value=0x61626364)
                    if legal and last and not keyport:
                        p.drain()
                    if legal and last and keyport:
                        p.cmd(0, 2)
                        p.expect(0, 1, b"key check", b"abcd"[:n],
                                 category="legal_key_mask")
                        p.bytes(0, b"key check")
                        p.drain()
                    p.emit(10, 0 if legal else 1, 12)
                    p.cmd(0, 5)
                    p.emit(10, 0, 1)
                    p.cover(f"mask_a{alg}_key{int(keyport)}_last{last}_keep{keep}")
            p.setup(0, alg, b"masks")
            if keyport:
                p.cmd(0, 0)
                p.cmd(0, 1)
            p.bytes(0, b"abcd", key=keyport, final=False)
            if p.partial and not keyport:
                p.expect(0, alg, b"", b"masks", digest(alg, b"abcd", b"masks"),
                         "zero_terminator")
            p.bytes(0, b"", key=keyport)
            if p.partial and not keyport:
                p.drain()
            p.emit(10, 0 if p.partial else 1, 12)
            p.cover(f"terminator_a{alg}_key{int(keyport)}")
            p.cmd(0, 5)


def faults(p):
    for alg in ((0, 1) if p.standalone else (0, 1, 2)):
        key = b"malformed"
        valid = context(alg, b"x", key, legacy=p.standalone)
        mutations = [0, 32, 42, 1400, 112, 119, 48, 888, 120, 109, 376, 40]
        if alg == 2:
            mutations = [2048, 2080, 2090, 1672, 128, 135, 0, 648, 136, 125, 2088]
        elif not p.standalone:
            mutations += [2048, 2080, 2090, 1536, 2088]
        for bit in mutations:
            p.cmd(0, 5)
            p.cmd(0, 4, valid ^ (1 << bit))
            p.emit(10, 1, 4)
            p.emit(16, 0, 0, 0, 0)
            if not p.standalone:
                p.setup(1, 2)
                p.expect(1, 2, b"fault isolation", category="fault_isolation")
                p.bytes(1, b"fault isolation")
                p.drain()
                p.emit(10, 1, 1)
            p.cover(f"malformed_a{alg}_bit{bit}")
            p.cmd(0, 5)
        if alg == 1:
            p.cmd(0, 5)
            p.cmd(0, 4, valid & ~(1 << 41))
            p.emit(10, 1, 4)
            p.cover("hmac_invalid_key_context")
            p.cmd(0, 5)
    for alg in ((0, 1) if p.standalone else (0, 1, 2)):
        for opcode in ((0, 1, 2) if p.standalone else (0, 1, 2, 6)):
            p.setup(0, alg, b"misuse")
            p.bytes(0, b"abcd", final=False)
            p.cmd(0, opcode)
            p.emit(10, 1, 4)
            p.cover(f"nonempty_init_a{alg}_op{opcode}")
            p.cmd(0, 5)
    for opcode in (2, 7):
        p.cmd(0, opcode)
        p.emit(10, 1, 4)
        p.cover(f"invalid_command_{opcode}")
        p.cmd(0, 5)
    p.emit(10, 0, 1)


def stalls(p):
    p.reset()
    p.emit(18)
    p.ready(0, 0)
    # The first response locks channel 2. All later arrivals must preserve it.
    p.setup(2, 2)
    p.expect(2, 2, b"late lock", category="stall")
    p.bytes(2, b"late lock")
    p.wait(400)
    p.emit(19, 1, 0)
    for ch, alg in ((3, 1), (0, 0), (1, 2)):
        key = b"concurrent key"
        p.setup(ch, alg, key)
        p.expect(ch, alg, b"four pending", key, category="stall")
        p.bytes(ch, b"four pending")
    p.wait(512)
    p.emit(19, 1, 0)
    # Pending response cannot be canceled, even before it wins the port.
    for ch in range(4):
        p.emit(13, ch, 5)
        p.emit(16, ch, 0, 0, 0)
    p.ready()
    p.drain()
    for j, ch in enumerate((2, 3, 0, 1)):
        p.emit(11, ch, j, 2 if j else 0)
    p.cover("digest_round_robin_four_pending_late_arrival")
    p.reset()
    p.emit(18)
    p.ready(1, 0)
    for ch in (1, 3, 0, 2):
        p.setup(ch, 0)
        p.snapshot(ch, 0, b"", slot=ch)
        p.wait(80)
    p.ready()
    p.drain()
    for j, ch in enumerate((1, 2, 3, 0)):
        p.emit(20, ch, j, 2 if j else 0)
    p.cover("context_round_robin_four_pending")
    p.reset()
    p.ready(1, 0)
    p.setup(0, 0)
    p.snapshot(0, 0, b"", slot=0)
    p.wait(80)
    p.emit(13, 0, 5)
    p.emit(13, 0, 0)
    p.emit(16, 0, 0, 0, 0)
    p.setup(1, 2)
    p.ready(0, 0)
    p.expect(1, 2, b"simultaneous", category="stall")
    p.bytes(1, b"simultaneous")
    p.wait(400)
    p.ready()
    p.drain()
    p.emit(12, 64, 64, 1)
    p.cover("stalls_64_and_simultaneous_retirement")
    p.ready(randomize=1)
    for ch, alg in enumerate((0, 1, 2, 0)):
        p.setup(ch, alg, b"mix")
        p.expect(ch, alg, bytes(range(129)), b"mix", category="mixed")
    # Interleaved beats overlap all three engines without violating source holds.
    data = bytes(range(129))
    for off in range(0, len(data), 4):
        for ch in range(4):
            chunk = data[off:off + 4]
            p.emit(2, ch, (15 << (4 - len(chunk))) & 15,
                   int(off + len(chunk) == len(data)),
                   value=int.from_bytes(chunk.ljust(4, b"\0"), "big"))
    p.drain()
    p.ready()


def interruptions(p):
    for alg in ((0, 1) if p.standalone else (0, 1, 2)):
        for cycles in (0, 1, 4, 6, 7, 8, 70, 86):
            p.setup(0, alg, b"cancel")
            p.bytes(0, b"x" * (128 if alg == 2 else 64), final=False)
            p.wait(cycles)
            p.cmd(0, 5)
            p.message(0, 0, b"after cancel", category="cancel_recovery")
            p.cover(f"cancel_a{alg}_phase{cycles}")
            p.setup(0, alg, b"reset")
            p.bytes(0, b"x" * (128 if alg == 2 else 64), final=False)
            p.wait(cycles)
            p.reset()
            p.message(0, 0, b"after reset", category="reset_recovery")
            p.cover(f"reset_a{alg}_phase{cycles}")
        p.setup(0, alg, b"abort")
        p.ready(0, 1)
        p.expect(0, alg, b"x", b"abort", category="reset_aborted_digest")
        p.bytes(0, b"x")
        p.wait(500)
        p.emit(19, 1, 0)
        p.reset()
        p.ready()
        p.cover(f"reset_stalled_digest_a{alg}")
        p.setup(0, alg, b"abort context")
        p.ready(1, 0)
        p.snapshot(0, alg, b"", b"abort context")
        p.wait(100)
        p.emit(19, 0, 1)
        p.reset()
        p.ready()
        p.cover(f"reset_stalled_context_a{alg}")
    p.cmd(0, 1)
    p.bytes(0, b"k" * 12, key=True, final=False)
    p.cmd(0, 5)
    p.message(0, 0, b"key cancel", category="cancel_recovery")
    p.cover("cancel_key_loading")


def modes(p):
    key = b"cached key A" * 9
    p.setup(0, 1, key)
    p.message(0, 1, b"first", key, "key_reuse", setup=False)
    p.cmd(0, 0)
    p.message(0, 0, b"sha retains cache", category="key_cache_sha", setup=False)
    p.emit(8, 0, 0, value=context(0, key=key, legacy=p.standalone, cached=True))
    p.cmd(0, 3)
    p.drain()
    p.cmd(0, 5)
    p.emit(9, 0, 0, 0)
    p.cmd(0, 2)
    p.message(0, 1, b"second", key, "key_reuse", setup=False)
    replacement = b"replacement"
    p.cmd(0, 1)
    p.emit(16, 0, 0, 1, 0)
    p.emit(13, 0, 2)
    p.bytes(0, replacement, key=True)
    p.cmd(0, 2)
    p.message(0, 1, b"new key", replacement, "key_replace", setup=False)
    p.reset()
    p.cmd(0, 2)
    p.emit(10, 1, 3)
    p.cmd(0, 5)
    p.cmd(0, 1)
    p.emit(15, 0, 5)
    p.emit(10, 0, 1)
    p.cover("key_command_priority")
    for alg in ((0, 1) if p.standalone else (0, 1, 2)):
        p.setup(0, alg, key)
        p.emit(22, 0)
        p.expect(0, alg, b"x", key, digest(alg, b"abcdx", key), "stage_timing")
        p.bytes(0, b"x")
        p.drain()
        p.cover(f"staging_a{alg}")
    if not p.standalone:
        p.setup(0, 1, key)
        p.cmd(0, 6)
        p.cmd(0, 2)
        p.emit(10, 1, 3)
        p.cmd(0, 5)
        p.setup(0, 0)
        p.cmd(1, 5)
        p.cmd(1, 1)
        p.cmd(2, 5)
        p.expect(0, 0, b"one!", category="simultaneous_ports")
        p.emit(21)
        p.cmd(1, 2)
        p.expect(1, 1, b"follow", b"key!", category="simultaneous_ports")
        p.bytes(1, b"follow")
        p.expect(2, 2, b"changed", category="simultaneous_ports")
        p.bytes(2, b"changed")
        p.drain()
        p.cover("independent_simultaneous_inputs")
        p.cmd(3, 5)
        p.emit(15, 3, 0)
        p.message(3, 0, b"no phantom bytes", category="command_priority", setup=False)
        p.cover("stream_command_priority")
    p.emit(24)
    p.message(0, 0, b"reset wins", category="reset_priority")
    p.cover("reset_priority_with_valid_inputs")


def smoke(p):
    published(p)
    contexts(p)
    if not p.standalone:
        stalls(p)


def behavior(p):
    published(p)
    p.ready(randomize=1)
    matrix(p)
    p.emit(23, 1, 1)
    p.cover("random_stalls_and_source_bubbles")
    p.ready()
    contexts(p)
    stalls(p)
    mask_errors(p)
    faults(p)
    limits(p)
    interruptions(p)
    modes(p)


def benchmark(p, alg, length, channels, mixed=False):
    key = b"deterministic benchmark key"
    algs = [ch % 3 if mixed else alg for ch in range(channels)]
    for ch in range(channels):
        p.setup(ch, algs[ch], key)
    p.emit(14, 1)
    for j in range(16):
        for ch in range(channels):
            data = bytes(((i + j * 17) & 255) for i in range(length))
            p.expect(ch, algs[ch], data, key, category="benchmark")
        for off in range(0, max(length, 1), 4):
            for ch in range(channels):
                data = bytes(((i + j * 17) & 255)
                             for i in range(off, min(off + 4, length)))
                p.emit(2, ch, (15 << (4 - len(data))) & 15 if data else 0,
                       int(off + len(data) == length),
                       value=int.from_bytes(data.ljust(4, b"\0"), "big"))
        p.drain()
    p.emit(14, 2)
