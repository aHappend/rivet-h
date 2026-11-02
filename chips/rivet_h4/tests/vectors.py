"""Requirement-derived transactions. Coverage closes only on checked COVER records."""

import random
from contextlib import contextmanager

from reference import context, digest, keccak, merkle_root

SEEDS = (11, 29, 47)
LEGACY_LENGTHS = (0, 1, 3, 4, 55, 56, 63, 64, 65, 111, 112, 127, 128, 129, 257)
KEY_LENGTHS = (0, 1, 63, 64, 65, 131)
CONTEXT_LENGTHS = (0, 1, 63, 64, 65, 127, 128, 129)
RATES = (136, 72, 168, 136)


def random_bytes(rng, length):
    return bytes(rng.randrange(256) for _ in range(length))


def flip(data, offset=0):
    value = bytearray(data)
    value[offset] ^= 1
    return bytes(value)


def beats(data, partial=False, rng=None, final=True):
    if not data:
        if final:
            yield 0, 0, 1
        return
    offset = 0
    while offset < len(data):
        n = min(len(data) - offset, rng.randint(1, 4) if partial and rng else 4)
        chunk = data[offset:offset + n]
        offset += n
        yield int.from_bytes(chunk.ljust(4, b"\0"), "big"), (15 << (4 - n)) & 15, int(final and offset == len(data))


class Vectors:
    def __init__(self, path, partial, capacity, seed=11):
        self.file = path.open("w")
        self.partial = partial
        self.capacity = capacity
        self.rng = random.Random(seed)
        self.rows = 0
        self.cases = []
        self.prefix = ""

    def emit(self, op, a=0, b=0, c=0, payload=0):
        # Integer fields use signed fscanf; indices are represented as signed 32-bit.
        if a >= 1 << 31:
            a -= 1 << 32
        self.file.write(f"{op} {a} {b} {c} {payload:x}\n")
        self.rows += 1

    @contextmanager
    def case(self, name, minimum=1):
        identifier = len(self.cases) + 1
        self.emit(27, identifier)
        start = self.rows
        yield
        self.emit(27, identifier, minimum, 1)
        self.cases.append({"id": identifier, "bin": self.prefix + name, "first_row": start,
                           "last_row": self.rows, "minimum_comparisons": minimum})

    def close(self):
        self.file.close()
        return {"rows": self.rows, "cases": self.cases, "partial": self.partial,
                "capacity": self.capacity}

    def reset(self):
        self.emit(0)

    def command(self, channel, op, value=0):
        self.emit(2, channel, op, payload=value)

    def stream(self, data, channel=0, key=False, final=True, packed=True):
        for word, keep, last in beats(data, self.partial and packed, self.rng, final):
            if self.rng.randrange(7) == 0:
                self.emit(1, self.rng.randint(1, 3))
            self.emit(4 if key else 3, channel, keep, last, word)

    def legacy(self, message, algorithm, channel, key=b"", cancel=True):
        if cancel:
            self.command(channel, 5)
        if algorithm == 1:
            self.command(channel, 1)
            self.stream(key, channel, key=True)
        self.command(channel, (0, 2, 6)[algorithm])
        self.emit(5, channel, algorithm, payload=int.from_bytes(digest(message, algorithm, key=key), "big"))
        self.stream(message, channel)
        self.emit(6, 7)

    def sponge_start(self, algorithm, n):
        self.emit(8, algorithm, payload=n)

    def sponge_stream(self, message, packed=True, final=True):
        for word, keep, last in beats(message, self.partial and packed, self.rng, final):
            if self.rng.randrange(9) == 0:
                self.emit(1, self.rng.randint(1, 3))
            self.emit(9, b=keep, c=last, payload=word)

    def sponge_output(self, expected, stall=True):
        for word, keep, last in beats(expected):
            self.emit(10, self.rng.randint(0, 4) if stall else 0, keep, last, word)

    def sponge(self, message, algorithm, n):
        self.sponge_start(algorithm, n)
        self.sponge_stream(message)
        self.sponge_output(digest(message, algorithm, n))

    def page(self, page):
        for word, keep, last in beats(page):
            if self.rng.randrange(8) == 0:
                self.emit(1, 2)
            self.emit(15, b=keep, c=last, payload=word)

    def provision(self, root):
        self.reset()
        self.emit(19, 6, 3, 0)
        self.emit(13, payload=int.from_bytes(root, "big"))

    def merkle(self, page, siblings, index, success=True, mutate=None,
               result_first=True, root=None, provision=True):
        if provision:
            self.provision(root or merkle_root(page, siblings, index))
        self.emit(23, 0, int(not success))
        self.emit(14, index, len(siblings), payload=len(page))
        self.emit(19, 8, 3, 0)
        self.page(flip(page) if mutate == "page" else page)
        for level, sibling in enumerate(siblings):
            if isinstance(mutate, int) and level == mutate:
                sibling = flip(sibling, level % 32)
            self.emit(16, c=int(level == len(siblings) - 1), payload=int.from_bytes(sibling, "big"))
        self.emit(17, 9, int(result_first or not success), int(success))
        if success:
            if result_first:
                self.emit(19, 6, 4, 0)
            for word, keep, last in beats(page):
                self.emit(18, self.rng.randint(1, 5), keep, last, word)
            if not result_first:
                self.emit(19, 6, 3, 0)
                self.emit(17, 5, 1, 1)
        else:
            self.emit(23, 0, 1)
            self.emit(19, 13, 12, 0)
            self.emit(23)
        self.emit(26, 6)


def smoke(path, partial=0, capacity=3, parent=False):
    v = Vectors(path, partial, capacity)
    with v.case("reset-and-legacy-empty-abc-all-channels", 12):
        for ch in range(4):
            for alg in range(3):
                v.legacy(b"" if ch == 0 else b"abc", alg, ch, b"key")
    with v.case("context-cross-channel", 2):
        msg = b"abcd"
        v.command(0, 5)
        v.command(0, 0)
        v.stream(msg, 0, final=False, packed=False)
        v.command(0, 3)
        v.emit(7, 0, 5, payload=context(msg, 0))
        v.command(1, 5)
        v.emit(25, 1)
        v.emit(5, 1, 0, payload=int.from_bytes(digest(msg + b"xyz", 0), "big"))
        v.stream(b"xyz", 1)
        v.emit(6, 4)
        v.command(0, 5)
    if not parent:
        for alg in range(4):
            with v.case(f"smoke-sponge-{alg}", 8):
                v.sponge(b"abc", alg, (32, 64, 173, 141)[alg])
        for index in (0, 1):
            page = b"abc"[:capacity]
            siblings = [bytes(range(32))]
            with v.case(f"smoke-merkle-order-{index}"):
                v.merkle(page, siblings, index, result_first=not index)
            with v.case(f"smoke-merkle-tamper-{index}"):
                v.merkle(page, siblings, index, success=False, mutate="page")
                v.merkle(page, siblings, index, provision=False)
    return v.close()


def sponge_matrix(path, partial):
    v = Vectors(path, partial, 4096)
    for seed in SEEDS:
        v.rng = random.Random(seed)
        for alg, rate in enumerate(RATES):
            lengths = sorted({0, 1, 2, 3, 4, rate - 1, rate, rate + 1,
                              2 * rate - 1, 2 * rate, 2 * rate + 1, 4096})
            outputs = (32,) if alg == 0 else (64,) if alg == 1 else \
                (1, 2, 3, 4, rate - 1, rate, rate + 1, 2 * rate + 17, 1024)
            for length in lengths:
                message = random_bytes(v.rng, length)
                for n in outputs:
                    with v.case(f"sponge/seed{seed}/alg{alg}/length{length}/out{n}"):
                        v.sponge(message, alg, n)
            for i in range(16):
                length = v.rng.randrange(4097)
                n = (32, 64, v.rng.randint(1, 1100), v.rng.randint(1, 1100))[alg]
                with v.case(f"sponge/seed{seed}/alg{alg}/random{i}"):
                    v.sponge(random_bytes(v.rng, length), alg, n)
            with v.case(f"sponge/seed{seed}/alg{alg}/known-abc"):
                v.sponge(b"abc", alg, outputs[-1])
    return v.close()


def sponge_protocol(path, partial):
    v = Vectors(path, partial, 4096)
    for alg in range(4):
        n = (32, 64, 1024, 1024)[alg]
        for phase in ("absorb", "permute", "squeeze"):
            with v.case(f"sponge/cancel/{alg}/{phase}"):
                v.sponge_start(alg, n)
                if phase == "absorb":
                    v.sponge_stream(b"abcd", final=False, packed=False)
                else:
                    v.sponge_stream(b"abc", packed=False)
                    if phase == "permute":
                        v.emit(1, 30)
                        v.emit(19, 11, 2, 0)
                    else:
                        v.emit(26, 11)
                        v.emit(19, 11, 3, 1)
                v.emit(11, 1 if phase == "absorb" else 2 if phase == "squeeze" else 0)
                v.emit(19, 11, 120, 0)
                v.sponge(b"recovery", alg, (32, 64, 19, 19)[alg])
        with v.case(f"sponge/reset/{alg}"):
            v.sponge_start(alg, n)
            v.sponge_stream(b"abc", packed=False)
            v.emit(1, 30)
            v.reset()
            v.emit(19, 11, 110, 0)
            v.sponge(b"recovery", alg, (32, 64, 19, 19)[alg])
        illegal_n = (31, 63, 0, 0)[alg]
        with v.case(f"sponge/illegal-start/{alg}"):
            v.emit(21, c=1)
            v.sponge_start(alg, illegal_n)
            v.emit(12)
            v.emit(19, 11, 10, 0)
            v.emit(11)
            v.sponge(b"", alg, (32, 64, 3, 3)[alg])
        for mask in (0, 1, 2, 3, 5, 6, 7, 9, 10, 11, 13):
            with v.case(f"sponge/illegal-mask/{alg}/{mask}"):
                v.sponge_start(alg, n)
                v.emit(21, c=1)
                v.emit(9, b=mask, c=int(mask != 0), payload=0x61626364)
                v.emit(12)
                v.emit(11)
                v.sponge(b"valid", alg, (32, 64, 4, 4)[alg])
        with v.case(f"sponge/partial-and-zero-final/{alg}"):
            v.sponge_start(alg, (32, 64, 33, 33)[alg])
            if partial:
                v.sponge_stream(b"abc", packed=True, final=False)
                v.sponge_stream(b"")
                v.sponge_output(digest(b"abc", alg, (32, 64, 33, 33)[alg]))
            else:
                v.emit(21, c=1)
                v.emit(9, b=8, c=0, payload=0x61000000)
                v.emit(12)
                v.emit(11)
                v.sponge(b"abc", alg, (32, 64, 33, 33)[alg])
        if not partial:
            with v.case(f"sponge/nonempty-zero-final/{alg}"):
                v.sponge_start(alg, n)
                v.sponge_stream(b"abcd", packed=False, final=False)
                v.emit(21, c=1)
                v.emit(9, b=0, c=1)
                v.emit(12)
                v.emit(11)
                v.sponge(b"abc", alg, (32, 64, 3, 3)[alg])
        if alg >= 2:
            with v.case(f"sponge/maximum-xof-descriptor/{alg}", 3):
                v.sponge_start(alg, (1 << 32) - 1)
                v.sponge_stream(b"")
                for word, keep, _ in beats(digest(b"", alg, 8)):
                    v.emit(10, 3, keep, 0, word)
                v.emit(11, 2)
                v.sponge(b"recovery", alg, 3)
    return v.close()


def legacy_matrix(path, partial):
    v = Vectors(path, partial, 4096)
    for channel in range(4):
        for alg in range(3):
            for length in LEGACY_LENGTHS:
                keys = KEY_LENGTHS if alg == 1 else (0,)
                for key_length in keys:
                    with v.case(f"legacy/ch{channel}/alg{alg}/length{length}/key{key_length}"):
                        v.legacy(random_bytes(v.rng, length), alg, channel,
                                 random_bytes(v.rng, key_length))
    for alg in range(3):
        for count in CONTEXT_LENGTHS:
            with v.case(f"context/alg{alg}/count{count}/cross-channel", 3):
                msg = random_bytes(v.rng, count)
                key = b"cached-key" if alg == 1 else None
                canonical = context(msg, alg, key)
                v.command(0, 5)
                if partial or count % 4 == 0:
                    if alg == 1:
                        v.command(0, 1)
                        v.stream(key, 0, key=True)
                    v.command(0, (0, 2, 6)[alg])
                    v.stream(msg, 0, final=False, packed=bool(partial))
                else:
                    # Legal public restore reaches counts not producible by nonfinal PB=0 beats.
                    v.command(0, 4, canonical)
                v.command(0, 3)
                v.emit(7, 0, 6, payload=canonical)
                v.command(1, 5)
                v.emit(25, 1)
                suffix = b"continuation"
                v.emit(5, 1, alg, payload=int.from_bytes(digest(msg + suffix, alg, key=key or b""), "big"))
                v.stream(suffix, 1)
                v.emit(6, 8)
                if alg == 1:
                    # Cached seeds must survive digest retirement and HMAC_INIT.
                    v.command(1, 2)
                    v.emit(5, 1, 1, payload=int.from_bytes(digest(b"again", 1, key=key), "big"))
                    v.stream(b"again", 1)
                    v.emit(6, 5)
                else:
                    v.command(1, 5)
                    v.command(1, 4, canonical)
                    v.command(1, 3)
                    v.emit(7, 1, 3, payload=canonical)
                v.command(0, 5)
                v.command(1, 5)
        if alg < 2:
            with v.case(f"context/RHV2/alg{alg}", 2):
                msg = b"old-layout"
                key = b"cache" if alg else None
                canonical = context(msg, alg, key, rhv2=True)
                v.command(2, 5)
                v.command(2, 4, canonical)
                v.command(2, 3)
                v.emit(7, 2, 3, payload=context(msg, alg, key))
                v.emit(5, 2, alg, payload=int.from_bytes(digest(msg + b"x", alg, key=key or b""), "big"))
                v.stream(b"x", 2)
                v.emit(6, 5)
    for alg in range(3):
        good = context(b"", alg, b"key" if alg == 1 else None)
        corruptions = {"envelope-reserved": 1 << 2200, "magic": 1 << 2048,
                       "version": 1 << 2080, "algorithm": (3 ^ alg) << 2088}
        if alg == 2:
            corruptions.update({"reserved": 1 << 1900, "count-used": 1,
                                "used": 128 << 128, "buffer": 1 << 648,
                                "chain": 1 << 136, "limit": 1 << 125})
        else:
            corruptions.update({"payload-magic": 1, "payload-version": 1 << 32,
                                "reserved": 1 << 42, "count-used": 1 << 48,
                                "used": 64 << 112, "buffer": 1 << 888,
                                "chain": 1 << 120, "limit": 1 << 109})
            if alg == 1:
                corruptions["missing-key"] = 1 << 41
            else:
                corruptions["uncached-seed"] = 1 << 376
        for name, mask in corruptions.items():
            with v.case(f"context/malformed/alg{alg}/{name}", 2):
                v.command(3, 5)
                v.emit(21, 3, 1)
                v.command(3, 4, good ^ mask)
                v.emit(20, 3)
                v.command(3, 5)
                v.emit(21, 3)
                v.legacy(b"recovery", alg, 3, b"key")
        with v.case(f"context/overflow/alg{alg}", 2):
            limit = (1 << (125 if alg == 2 else 61)) - 1 - (64 if alg == 1 else 0)
            used = limit % (128 if alg == 2 else 64)
            large = context(bytes(used), alg, b"key" if alg == 1 else None, count_override=limit)
            v.command(3, 5)
            v.command(3, 4, large)
            v.emit(21, 3, 1)
            v.stream(b"x", 3)
            v.emit(20, 3)
            v.command(3, 5)
            v.emit(21, 3)
            v.legacy(b"recovery", alg, 3, b"key")
    with v.case("legacy/interleaved-continuously-ready-and-stalled-grants", 4):
        messages = [bytes([ch]) * (65 + 4 * ch) for ch in range(4)]
        for ch in range(4):
            v.command(ch, 5)
            v.command(ch, 0 if ch < 2 else 6)
            alg = 0 if ch < 2 else 2
            v.emit(5, ch, alg, payload=int.from_bytes(digest(messages[ch], alg), "big"))
        lists = [list(beats(msg)) for msg in messages]
        for i in range(max(map(len, lists))):
            for ch, stream in enumerate(lists):
                if i < len(stream):
                    word, keep, last = stream[i]
                    v.emit(3, ch, keep, last, word)
        v.emit(6, 20)
    with v.case("legacy/interleaved-continuously-ready", 4):
        for ch in range(4):
            v.command(ch, 5)
            v.command(ch, 0)
            v.emit(5, ch, 0, payload=int.from_bytes(digest(bytes([ch]) * 65, 0), "big"))
        v.emit(30, 1)
        lists = [list(beats(bytes([ch]) * 65)) for ch in range(4)]
        for i in range(len(lists[0])):
            for ch in range(4):
                word, keep, last = lists[ch][i]
                v.emit(3, ch, keep, last, word)
        v.emit(6)
    with v.case("legacy/simultaneous-command-key-data", 2):
        v.command(0, 5)
        v.emit(24, 0, 0, payload=0x61626364)
        v.emit(5, 0, 0, payload=int.from_bytes(digest(b"abc", 0), "big"))
        v.stream(b"abc", 0)
        v.emit(6, 4)
    with v.case("legacy/independent-simultaneous-command-key-data", 3):
        for ch in range(3):
            v.command(ch, 5)
        v.command(0, 0)
        v.command(1, 1)
        v.emit(5, 0, 0, payload=int.from_bytes(digest(b"abc", 0), "big"))
        v.emit(28)
        v.command(1, 2)
        v.emit(5, 1, 1, payload=int.from_bytes(digest(b"abc", 1, key=b"key"), "big"))
        v.stream(b"abc", 1)
        v.emit(6, 7)
    for alg in range(3):
        for phase in ("receive", "compression", "digest", "context"):
            with v.case(f"legacy/reset/alg{alg}/{phase}", 2):
                v.reset()
                if alg == 1:
                    v.command(0, 1)
                    v.stream(b"key", 0, key=True)
                v.command(0, (0, 2, 6)[alg])
                if phase == "context":
                    v.stream(b"abcd", 0, final=False, packed=False)
                    v.command(0, 3)
                    v.emit(26, 10)
                    v.emit(19, 10, 5, 1)
                elif phase != "receive":
                    message = bytes(range(129))
                    if phase == "digest":
                        v.emit(5, 0, alg, payload=int.from_bytes(digest(message, alg, key=b"key"), "big"))
                    v.stream(message, 0)
                    if phase == "compression":
                        v.emit(1, 20)
                        v.emit(19, 9, 2, 0)
                    else:
                        v.emit(26, 9)
                        v.emit(19, 9, 5, 1)
                v.reset()
                v.emit(19, 9, 120, 0)
                v.emit(19, 10, 5, 0)
                v.legacy(b"reset-recovery", alg, 0, b"key")
    with v.case("legacy/context-arbitration-all-channels", 4):
        for ch in range(4):
            v.command(ch, 5)
            v.command(ch, 0)
            v.command(ch, 3)
        for ch in range(4):
            v.emit(7, ch, 7, payload=context(b"", 0))
    for ch in range(4):
        with v.case(f"legacy/fault-isolation/{ch}", 2):
            v.command(ch, 5)
            v.emit(21, ch, 1)
            v.command(ch, 7)
            v.emit(20, ch)
            other = (ch + 1) % 4
            v.legacy(b"isolated", 0, other)
            v.command(ch, 5)
            v.emit(21, ch)
            v.legacy(b"recovered", 0, ch)
    return v.close()


def merkle_matrix(path, partial, capacity):
    v = Vectors(path, partial, capacity)
    lengths = sorted({n for n in (1, 2, 3, 4, 55, 56, 63, 64, 65, capacity)
                      if n <= capacity})
    for seed in SEEDS:
        v.rng = random.Random(seed)
        for depth in (0, 1, 2, 5, 32):
            maximum = (1 << depth) - 1
            indices = sorted({0, maximum, 0xA5A5A5A5 & maximum, 0x5A5A5A5A & maximum})
            siblings = [random_bytes(v.rng, 32) for _ in range(depth)]
            for index in indices:
                for length in lengths:
                    page = random_bytes(v.rng, length)
                    name = f"merkle/seed{seed}/depth{depth}/index{index}/length{length}"
                    with v.case(name):
                        v.merkle(page, siblings, index, result_first=bool(length % 2))
                page = random_bytes(v.rng, min(capacity, 3))
                for mutation in ("page",):
                    with v.case(f"merkle/seed{seed}/depth{depth}/index{index}/tamper-{mutation}", 2):
                        v.merkle(page, siblings, index, success=False, mutate=mutation)
                        v.merkle(page, siblings, index, provision=False)
                if depth:
                    with v.case(f"merkle/seed{seed}/depth{depth}/index{index}/tamper-order", 2):
                        root = merkle_root(page, siblings, index)
                        v.merkle(page, siblings, index ^ 1, root=root, success=False)
                        v.merkle(page, siblings, index, provision=False)
            index = 0xA5A5A5A5 & maximum
            page = random_bytes(v.rng, min(capacity, 3))
            for level in range(depth):
                with v.case(f"merkle/seed{seed}/depth{depth}/tamper-sibling-level{level}", 2):
                    v.merkle(page, siblings, index, success=False, mutate=level)
                    v.merkle(page, siblings, index, provision=False)
            with v.case(f"merkle/seed{seed}/depth{depth}/root-mismatch", 2):
                page = random_bytes(v.rng, min(capacity, 3))
                good = merkle_root(page, siblings, 0)
                # The pinned root matches the original page; the first page is different.
                v.merkle(flip(page), siblings, 0, root=good, success=False)
                v.merkle(page, siblings, 0, provision=False)
    return v.close()


def merkle_protocol(path, partial, capacity, seed=11):
    v = Vectors(path, partial, capacity, seed)
    v.prefix = f"seed{seed}/"
    page = b"abc"[:capacity]
    sibling = bytes(range(32))
    siblings = [sibling]
    root = merkle_root(page, siblings, 0)
    with v.case("merkle/simultaneous-root-and-start", 2):
        v.reset()
        v.emit(29, payload=int.from_bytes(root, "big"))
        v.merkle(page, siblings, 0, provision=False)
    with v.case("merkle/root-overwrite-back-to-back", 2):
        v.provision(root)
        v.emit(22, payload=int.from_bytes(flip(root), "big"))
        v.merkle(page, siblings, 0, provision=False)
        v.merkle(page, siblings, 0, provision=False, result_first=False)
    descriptors = ((0, 0, 0), (capacity + 1, 0, 0), (1, 33, 0),
                   (1, 0, 1), (1, 1, 2), (1, 31, 1 << 31))
    for length, depth, index in descriptors:
        with v.case(f"merkle/invalid-descriptor/{length}-{depth}-{index}", 2):
            v.provision(root)
            v.emit(14, index, depth, payload=length)
            v.emit(17, 5, 1, 0)
            v.emit(19, 7, 4, 0)
            v.merkle(page, siblings, 0, provision=False)
    malformed = [(keep, 1, 0x61000000) for keep in (0, 1, 5, 10)]
    malformed += [(8, 0, 0x61000000), (15, 0, 0x61626364), (15, 1, 0x61626364)]
    if capacity > 1:
        malformed += [(8, 1, 0x61000000)]
    for i, (keep, last, word) in enumerate(malformed):
        with v.case(f"merkle/page-framing/{i}", 2):
            v.provision(root)
            v.emit(14, 0, 1, payload=len(page))
            v.emit(15, b=keep, c=last, payload=word)
            v.emit(17, 5, 1, 0)
            v.merkle(page, siblings, 0, provision=False)
    for depth in (1, 2, 5, 32):
        proof = [sibling] * depth
        for level in sorted({0, depth // 2, depth - 1}):
            with v.case(f"merkle/proof-framing/depth{depth}/level{level}", 2):
                v.provision(merkle_root(page, proof, 0))
                v.emit(14, 0, depth, payload=len(page))
                v.page(page)
                for i in range(level + 1):
                    last = int(i == depth - 1)
                    if i == level:
                        last ^= 1
                    v.emit(16, c=last, payload=int.from_bytes(sibling, "big"))
                v.emit(17, 6, 1, 0)
                v.merkle(page, proof, 0, provision=False)
    for phase in ("receive", "hash", "proof", "replay"):
        with v.case(f"merkle/reset/{phase}", 2):
            v.provision(root)
            v.emit(14, 0, 1, payload=len(page))
            if phase == "receive":
                v.emit(26, 7)
                v.emit(19, 8, 5, 0)
            else:
                v.page(page)
                if phase == "hash":
                    v.emit(1, 30)
                    v.emit(19, 8, 2, 0)
                else:
                    v.emit(26, 8)
                    if phase == "replay":
                        v.emit(16, c=1, payload=int.from_bytes(sibling, "big"))
                        v.emit(17, 3, 0, 1)
                        v.emit(26, 13)
                        v.emit(19, 13, 5, 1)
            v.reset()
            v.emit(19, 6, 5, 0)
            v.emit(19, 13, 110, 0)
            v.emit(13, payload=int.from_bytes(root, "big"))
            v.merkle(page, siblings, 0, provision=False)
    with v.case("merkle/input-absence-is-stall", 2):
        v.provision(root)
        v.emit(14, 0, 1, payload=len(page))
        v.emit(26, 7)
        v.emit(19, 12, 150, 0)
        v.page(page)
        v.emit(26, 8)
        v.emit(19, 12, 150, 0)
        v.emit(16, c=1, payload=int.from_bytes(sibling, "big"))
        v.emit(17, 5, 1, 1)
        for word, keep, last in beats(page):
            v.emit(18, 4, keep, last, word)
        v.emit(26, 6)
    with v.case("concurrent-legacy-sponge-merkle-and-cancel-isolation", 6):
        v.provision(root)
        v.emit(14, 0, 1, payload=len(page))
        v.command(0, 0)
        v.sponge_start(2, 177)
        v.emit(5, 0, 0, payload=int.from_bytes(digest(b"parallel", 0), "big"))
        v.page(page)
        v.stream(b"parallel", 0)
        v.sponge_stream(b"parallel")
        v.emit(16, c=1, payload=int.from_bytes(sibling, "big"))
        v.emit(22, payload=int.from_bytes(flip(root), "big"))
        v.command(1, 5)
        v.emit(6, 8)
        v.sponge_output(digest(b"parallel", 2, 177))
        v.emit(11)
        v.emit(17, 8, 1, 1)
        for word, keep, last in beats(page):
            v.emit(18, 5, keep, last, word)
        v.emit(26, 6)
    return v.close()


def mutation_vectors(path, name):
    v = Vectors(path, 0, 3)
    with v.case(f"mutation/{name}"):
        if name == "round-constant":
            v.sponge(b"abc", 0, 32)
        elif name == "suffix":
            v.sponge(b"abc", 0, 32)
            v.sponge(b"abc", 2, 19)
        elif name == "squeeze":
            v.sponge(b"abc", 2, 337)
        else:
            page, siblings, index = b"abc", [bytes(range(32))], 1
            v.merkle(page, siblings, index, success=name != "root-decision",
                     mutate="page" if name == "root-decision" else None)
    return v.close()


def permutation_vectors(path):
    rng = random.Random(11)
    states = [0, (1 << 1600) - 1] + [rng.getrandbits(1600) for _ in range(8)]
    with path.open("w") as f:
        for state in states:
            f.write(f"{state:0400x} {keccak(state):0400x}\n")
    return len(states)
