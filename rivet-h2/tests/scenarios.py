"""Requirement-driven public-pin workloads. Each emitted check has an independent oracle."""
import random

from model import (IV, SHA_LIMIT, HMAC_LIMIT, context, digest, synthetic_digest)

MESSAGE_LENGTHS = (0, 1, 2, 3, 4, 55, 56, 57, 63, 64, 65, 119, 120,
                   127, 128, 129, 255, 256, 257, 1024)
KEY_LENGTHS = (0, 1, 3, 4, 31, 32, 63, 64, 65, 119, 120, 127, 128, 129, 131, 1024)
RFC = (
    (b"\x0b" * 20, b"Hi There",
     "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"),
    (b"Jefe", b"what do ya want for nothing?",
     "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"),
    (b"\xaa" * 20, b"\xdd" * 50,
     "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe"),
    (bytes(range(1, 26)), b"\xcd" * 50,
     "82558a389a443c0ea4cc819899f2083a85f0faa3e578f8077a2e3ff46729665b"),
    (b"\x0c" * 20, b"Test With Truncation", "a3b6167473100ee06e0c796c2955552b"),
    (b"\xaa" * 131, b"Test Using Larger Than Block-Size Key - Hash Key First",
     "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"),
    (b"\xaa" * 131,
     b"This is a test using a larger than block-size key and a larger than block-size data. "
     b"The key needs to be hashed before being used by the HMAC algorithm.",
     "9b09ffa71b942fcb27635fbcd5b0e944bfdc63644f0713938a7f51535c3a35e2"))


class Workload:
    def __init__(self, path, partial=0, seed=17, h1=False):
        self.file = path.open("w")
        self.partial = partial
        self.rng = random.Random(seed)
        self.h1 = h1
        self.counts = {"sha": 0, "hmac": 0, "snapshots": 0, "switches": 0,
                       "faults": 0, "resets": 0, "cancels": 0}
        self.coverage = {}
        self.identity = 0
        self.comparisons = []

    def emit(self, op, a=0, b=0, c=0, d=0):
        self.file.write(f"{op} {a:x} {b:x} {c:x} {d:x}\n")

    def mark(self, name):
        self.coverage[name] = self.coverage.get(name, 0) + 1

    def close(self):
        self.file.close()
        return {"expected": self.counts, "scenarios": self.coverage,
                "comparisons": self.comparisons}

    def reset(self):
        self.emit(7)
        self.counts["resets"] += 1

    def cancel(self):
        self.emit(8)
        self.counts["cancels"] += 1

    def fresh(self):
        self.reset() if self.h1 else self.cancel()

    def command(self, op, image=0):
        self.emit(3, op, d=image)

    def stream(self, data, final=True, key=False, gaps=False, arbitrary=False):
        if not data:
            if final:
                self.emit(1, 0, 0, 1 | (2 if key else 0))
            return
        i = 0
        while i < len(data):
            n = min(len(data) - i, self.rng.randint(1, 4) if arbitrary and self.partial else 4)
            piece = data[i:i + n]
            self.emit(1, int.from_bytes(piece.ljust(4, b"\0"), "big"),
                      (15 << (4 - n)) & 15,
                      int(final and i + n == len(data)) | (2 if key else 0))
            i += n
            if gaps and self.rng.randrange(4) == 0:
                self.emit(15, self.rng.randint(1, 6))

    def expect(self, data, key=None, stall=0, expected=None, resumed=False, expected_latency=0):
        self.identity += 1
        value = digest(data, key) if expected is None else expected
        self.emit(2, int(key is not None) | (expected_latency << 1), stall, self.identity,
                  int.from_bytes(value, "big"))
        self.counts["hmac" if key is not None else "sha"] += 1
        self.comparisons.append({
            "identity": self.identity, "mode": "hmac" if key is not None else "sha",
            "message_bytes": len(data), "key_bytes": None if key is None else len(key),
            "kind": "synthetic_count" if expected is not None else "context_resume" if resumed else "stream",
            "expected_digest": value.hex(),
            "expected_last_beat_latency_cycles": expected_latency or None,
        })

    def message(self, data, key=None, stall=0, gaps=False):
        self.stream(data, gaps=gaps, arbitrary=True)
        self.expect(data, key, stall)

    def key(self, key):
        self.command(1)
        self.stream(key, key=True, arbitrary=True)
        # An ordinary command waits through key hashing and both seed blocks.
        self.command(2)

    def save(self, image, slot=0, stall=0):
        self.emit(4, slot, stall, d=image)
        self.counts["snapshots"] += 1

    def restore(self, slot):
        self.emit(5, slot)
        self.counts["switches"] += 1

    def fault(self):
        self.emit(9)
        self.counts["faults"] += 1

    def held_context(self, message, image, key=None, restore=False):
        self.identity += 1
        self.emit(18, int(key is not None), int(restore), self.identity,
                  int.from_bytes(digest(message, key), "big"))
        self.file.write(f"{image:x}\n")
        self.counts["hmac" if key is not None else "sha"] += 1
        self.comparisons.append({
            "identity": self.identity, "mode": "hmac" if key is not None else "sha",
            "message_bytes": len(message), "key_bytes": None if key is None else len(key),
            "kind": "stream", "expected_digest": digest(message, key).hex(),
        })
        if not restore:
            self.counts["snapshots"] += 1

    def recovery(self, use_reset=False):
        self.reset() if use_reset or self.h1 else self.cancel()
        self.emit(16, 150)
        if not self.h1:
            self.save(context())
            self.command(2)
            self.fault()
            self.cancel()
        self.message(b"recovered")


def vectors(w):
    w.fresh()
    for msg in (b"", b"abc", b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"):
        w.message(msg, stall=101, gaps=True)
    w.mark("standard_sha")
    for case, (key, msg, expected) in enumerate(RFC, 1):
        assert digest(msg, key).hex().startswith(expected)
        w.fresh()
        w.key(key)
        if case == 5:
            w.stream(msg, gaps=True, arbitrary=True)
            w.emit(13, 0)
            w.emit(20, d=int(expected, 16))
            w.expect(msg, key, stall=101)
        else:
            w.message(msg, key, stall=101, gaps=True)
    w.mark("rfc4231_all_seven_full_digests_and_case5_prefix")


def residues(w, small=False):
    residues_to_use = (0, 1, 55, 56, 63) if small else range(64)
    for key in (None, b"context-key"):
        for r in residues_to_use:
            for base in ((0,) if small else (0, 64)):
                n = base + r
                prefix = bytes((i * 37 + r) % 256 for i in range(n))
                suffix = b"finish:" + bytes([r]) * 11
                w.fresh()
                if key is not None:
                    w.key(key)
                image = context(prefix, key)
                if w.partial or n % 4 == 0:
                    w.stream(prefix, final=False, arbitrary=True)
                    w.save(image, 0, 101 if r == 55 else 0)
                    w.save(image, 0)
                    w.mark(f"actual_save_{'hmac' if key is not None else 'sha'}_residue_{r}")
                else:
                    w.command(4, image)
                    w.save(image, 0)
                    w.mark(f"import_{'hmac' if key is not None else 'sha'}_residue_{r}")
                # Replace unrelated nonempty state and key ownership, then restore.
                w.cancel()
                w.key(b"unrelated-owner")
                w.message(b"unrelated", b"unrelated-owner")
                w.stream(b"junk", final=False)
                w.restore(0)
                w.stream(suffix)
                w.expect(prefix + suffix, key, resumed=True)
    w.mark("partial_block_roundtrip")


def interleave(w, switches=104):
    keys = (None, b"A" * 16, b"B" * 16, b"L" * 131)
    prefixes = [b""] * 4
    for slot, key in enumerate(keys):
        w.fresh()
        if key is not None:
            w.key(key)
        w.save(context(b"", key), slot)
    for step in range(switches):
        slot = step % 4
        w.restore(slot)
        # Equal-length distinct streams plus unequal stream lengths.
        n = 4 if slot < 3 else 8
        chunk = bytes([slot * 51 + step % 17]) * n
        w.stream(chunk, final=False, arbitrary=True)
        prefixes[slot] += chunk
        w.save(context(prefixes[slot], keys[slot]), slot, 101 if step == 51 else 0)
    for slot, key in enumerate(keys):
        w.restore(slot)
        tail = bytes([slot]) * (55 + slot)
        w.stream(tail)
        w.expect(prefixes[slot] + tail, key, 101, resumed=True)
    w.mark("four_independent_contexts")


def malformed(w):
    base = context()
    keybase = context(b"", b"key")
    invalid = {
        "magic": base ^ 1, "version": base ^ (3 << 32),
        "reserved_low": base | (1 << 42), "reserved_high": base | (1 << 1400),
        "used_range": base | (64 << 112), "used_count": base | (1 << 48),
        "unused_buffer": base | (1 << 888), "initial_chain": base ^ (1 << 120),
        "missing_key_inner": base | (1 << 376), "missing_key_outer": base | (1 << 632),
        "hmac_without_key": base | (1 << 40),
        "hmac_initial_chain": keybase ^ (1 << 120),
        "sha_length": context(b"", count=1 << 61, chain=IV),
        "hmac_length": context(b"", b"key", count=(1 << 61) - 64, chain=IV)}
    for name, image in invalid.items():
        w.fresh()
        w.stream(b"live", final=False)
        w.command(4, image)
        w.fault()
        w.recovery()
        w.mark("reject_context_" + name)
    for op in (0, 1, 2, 6, 7):
        w.fresh()
        if op in (0, 1, 2):
            w.stream(b"live", final=False)
        w.command(op)
        w.fault()
        w.recovery()
        w.mark(f"illegal_command_{op}")
    w.fresh()
    w.command(2)
    w.fault()
    w.recovery()


def mask_errors(w, keys=True):
    for key_stream in ((False, True) if keys else (False,)):
        for last in (False, True):
            for mask in range(16):
                legal = mask == 15 or (mask in (8, 12, 14) and (last or w.partial))
                legal |= mask == 0 and last
                if legal:
                    continue
                w.fresh()
                if key_stream:
                    w.command(1)
                w.emit(1, 0xDEADBEEF, mask, int(last) | (2 if key_stream else 0))
                w.fault()
                w.recovery(use_reset=mask % 2 == 0)
                w.mark(f"illegal_mask_{int(key_stream)}_{int(last)}_{mask}")
        if not w.partial:
            w.fresh()
            if key_stream:
                w.command(1)
            w.stream(b"four", final=False, key=key_stream)
            w.emit(1, 0, 0, 1 | (2 if key_stream else 0))
            w.fault()
            w.recovery()
            w.mark("default_zero_final_nonempty")
        else:
            w.fresh()
            if key_stream:
                w.command(1)
            w.stream(b"xy", final=False, key=key_stream)
            w.stream(b"", key=key_stream)
            if key_stream:
                w.command(2)
                w.message(b"final-zero", b"xy")
            else:
                w.expect(b"xy")
            w.mark("extended_zero_final_nonempty")


def near_limit(w):
    for key, limit in ((None, SHA_LIMIT), (b"near-limit-key", HMAC_LIMIT)):
        for remaining in (0, 1, 4, 8, 63, 64, 65):
            # With a strict stream, leave at least one byte for a legal final beat.
            suffix = b"Z" * max(1, remaining)
            count = limit - len(suffix)
            partial = bytes((j * 19) % 256 for j in range(count % 64))
            image = context(partial, key, count=count, chain=IV)
            w.fresh()
            w.command(4, image)
            w.save(image)
            w.stream(suffix)
            w.expect(b"", key, expected=synthetic_digest(image, suffix))
            w.mark("near_limit_legal_padding")
        for remaining in (0, 1, 2, 3):
            count = limit - remaining
            partial = b"P" * (count % 64)
            image = context(partial, key, count=count, chain=IV)
            w.fresh()
            w.command(4, image)
            w.emit(1, 0x01020304, 15, 1)
            w.fault()
            w.recovery()
            w.mark("whole_beat_overflow")
    # Key count cannot be imported; max key length shares the SHA counter guard.


def cancellation(w):
    # Offsets count from the public final-beat acceptance. They select the
    # stated byte-stage / fixed 64-round intervals, never DUT internal signals.
    cases = (
        ("staged_input", b"abcd", False, None, 0),
        ("message_compression", b"x" * 64, False, None, 20),
        ("padding_one", b"abcd", True, None, 20),
        ("padding_first_of_two", b"x" * 56, True, None, 20),
        ("padding_second_of_two", b"x" * 56, True, None, 90),
        ("hmac_inner_padding", b"abcd", True, b"key", 20),
        ("hmac_inner_to_outer", b"abcd", True, b"key", 71),
        ("hmac_outer", b"abcd", True, b"key", 95),
    )
    for name, msg, final, key, delay in cases:
        for reset in (False, True):
            w.fresh()
            if key is not None:
                w.key(key)
            w.stream(msg, final=final)
            w.emit(6, delay)
            w.emit(11, 3, 1)
            w.recovery(use_reset=reset)
            w.mark(("reset_" if reset else "cancel_") + name)
    for name, key, final, delay in (
        ("key_ingestion", b"abcd", False, 0),
        ("long_key_hash", b"k" * 131, True, 20),
        ("ipad_generation", b"", True, 80),
        ("opad_generation", b"", True, 150),
    ):
        for reset in (False, True):
            w.fresh()
            w.command(1)
            w.stream(key, final=final, key=True)
            w.emit(6, delay)
            # During key ingestion k_ready may be high; other commands still
            # must be backpressured. Test readiness separately from busy datapath.
            if final:
                w.emit(11, 4, 1)
            w.recovery(use_reset=reset)
            w.mark(("reset_" if reset else "cancel_") + name)
    for output in ("digest", "context"):
        for reset in (False, True):
            w.fresh()
            if output == "digest":
                w.stream(b"discarded")
                w.emit(13, 101)
            else:
                w.emit(14, 101)
            w.emit(11, 3, 2)
            if not reset:
                w.emit(25)
            w.recovery(use_reset=reset)
            w.mark(("reset_" if reset else "cancel_") + "stalled_" + output)


def arbitration(w):
    w.fresh()
    w.emit(12, 0)
    w.message(b"")
    w.mark("command_stream_coincident")
    for n in ((1, 2, 3, 4) if w.partial else (4,)):
        w.fresh()
        piece = bytes(range(1, n + 1))
        w.emit(19, int.from_bytes(piece.ljust(4, b"\0"), "big"), (15 << (4 - n)) & 15, n)
        w.save(context(piece))
        w.stream(b"timing")
        w.expect(piece + b"timing")
        w.mark(f"registered_stage_{n}_bytes")
    # Backpressured offers must not be sampled, even with deliberately hostile
    # changes to unaccepted payload. This is not a compliant-upstream claim.
    for op in (0, 1, 2, 3, 4, 6, 7):
        w.fresh()
        w.stream(b"busy-unaccepted-data")
        w.emit(6, 12)
        w.emit(11, op, 5)
        w.expect(b"busy-unaccepted-data")
        w.mark(f"unaccepted_busy_command_{op}")
    w.fresh()
    w.emit(22, d=context())
    w.counts["snapshots"] += 1
    w.emit(23)
    w.message(b"ready-before-valid")
    w.mark("ready_high_before_output_creation")
    # Hold SAVE through compression and digest retirement: it owns the newly
    # empty message, not a transient padding snapshot.
    w.fresh()
    w.stream(b"held-save")
    w.held_context(b"held-save", context())
    w.mark("save_after_finalization")
    w.fresh()
    w.stream(b"held-restore")
    imported = context(b"imported", b"held-key")
    w.held_context(b"held-restore", imported, restore=True)
    w.stream(b"suffix")
    w.expect(b"importedsuffix", b"held-key", resumed=True)
    w.mark("restore_after_finalization")
    # Snapshot immediately before final byte/padding; all padding boundaries.
    for n in (52, 56, 60, 64, 116, 120, 124, 128):
        w.fresh()
        prefix = bytes(range(n))
        w.stream(prefix, final=False)
        w.save(context(prefix))
        w.stream(b"end")
        w.expect(prefix + b"end")
    # SHA_INIT retains installed key; automatic same-mode restarts retain seeds.
    w.fresh()
    w.key(b"retained")
    w.command(0)
    w.save(context(installed_key=b"retained"))
    w.message(b"sha-with-installed-key")
    w.command(2)
    w.message(b"first", b"retained")
    w.message(b"second", b"retained")
    for replacement in (b"long-replacement" * 10, b"", b"R" * 64, b"S"):
        w.key(replacement)
        w.save(context(b"", replacement))
        for msg in (b"", b"same-message", b"same-message"):
            w.message(msg, replacement)
    w.mark("key_replacement_without_cancel")
    w.fresh()
    w.command(1)
    w.emit(10, 0, 1, 0)
    w.emit(21, 7, 1)
    w.emit(21, 7, 3)
    w.stream(b"exclusive", key=True)
    w.command(2)
    w.message(b"exclusive-message", b"exclusive")
    w.mark("key_ingestion_exclusive")
    for key in (None, b"cycle-table-key"):
        for length in (0, 1, 2, 3, 4, 55, 56, 63, 64, 65, 119, 120, 127, 128):
            w.fresh()
            if key is not None:
                w.key(key)
            message = bytes([length % 256]) * length
            w.stream(message)
            final_bytes = (length % 4 or 4) if length else 0
            # One registered beat plus byte drain, registered padding launch,
            # 64 rounds, feed-forward, and following-edge controller consume.
            latency = max(1, final_bytes) + 69
            latency += 67 if length % 64 >= 56 else 0
            latency += 69 if length and length % 64 == 0 else 0
            latency += 67 if key is not None else 0
            w.expect(message, key, expected_latency=latency)
    w.mark("public_cycle_table")


def main_workload(w, full=True):
    vectors(w)
    w.fresh()
    for n in MESSAGE_LENGTHS:
        w.message(w.rng.randbytes(n), stall=101 if n in (0, 56, 64) else 0, gaps=True)
        w.mark(f"sha_message_length_{n}")
    for n in KEY_LENGTHS:
        key = w.rng.randbytes(n)
        w.fresh()
        w.key(key)
        for length in MESSAGE_LENGTHS if full else (0, 55, 56, 63, 64, 65):
            w.message(w.rng.randbytes(length), key, gaps=True)
            w.mark(f"hmac_message_length_{length}")
        w.mark(f"key_length_{n}")
    if full:
        w.fresh()
        for _ in range(110):
            w.message(w.rng.randbytes(w.rng.randrange(300)), gaps=True)
        residues(w)
        interleave(w)
        malformed(w)
        mask_errors(w)
        near_limit(w)
        cancellation(w)
        arbitration(w)
    else:
        residues(w, small=True)
        interleave(w, switches=8)
        w.fresh()
        w.stream(b"cancel-me")
        w.emit(6, 20)
        w.recovery()
    return w.close()


def portable_workload(w):
    w.fresh()
    w.message(b"portable-sha", stall=101)
    for key in (b"", b"long-portable-key" * 10):
        w.fresh()
        w.key(key)
        w.message(b"portable-hmac", key)
    w.fresh()
    prefix = b"arbitrary-prefix"
    w.stream(prefix, final=False, arbitrary=True)
    w.save(context(prefix), stall=101)
    w.cancel()
    w.restore(0)
    w.stream(b"suffix")
    w.expect(prefix + b"suffix", resumed=True)
    w.fresh()
    w.stream(b"cancel-pending")
    w.emit(6, 20)
    w.recovery()
    w.mark("bounded_portable_subset")
    return w.close()


def compatibility_workload(w, full=True):
    w.reset()
    messages = [b"", b"abc", b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"]
    messages += [w.rng.randbytes(n) for n in MESSAGE_LENGTHS]
    messages += [w.rng.randbytes(w.rng.randrange(400)) for _ in range(110 if full else 3)]
    for msg in messages:
        w.message(msg, stall=101, gaps=True)
    if full:
        mask_errors(w, keys=False)
    for n, delay in ((4, 0), (64, 15), (56, 90)):
        w.reset()
        w.stream(b"x" * n)
        w.emit(6, delay)
        w.reset()
        w.emit(16, 150)
        w.message(b"after-reset", stall=101)
    w.reset()
    w.stream(b"stalled")
    w.emit(13, 101)
    w.reset()
    w.emit(16, 150)
    w.message(b"after-stall-reset")
    w.mark("h1_masks_reset_stall")
    return w.close()


def mutation_workload(w, kind):
    w.fresh()
    if kind == "sha_arithmetic":
        w.message(b"abc")
    elif kind == "ipad_opad":
        w.key(b"key")
        w.message(b"ipad witness", b"key")
    elif kind == "long_key":
        key = b"L" * 131
        w.key(key)
        w.message(b"long key witness", key)
    elif kind in ("restore_buffer", "restore_length"):
        prefix = b"saved-prefix!"
        image = context(prefix)
        w.command(4, image)
        # Compare digest, not a regex on mutation source or compilation.
        w.stream(b"resume")
        w.expect(prefix + b"resume", resumed=True)
    elif kind == "restore_outer":
        # Same-length distinct owners, actual public SAVE and restored image.
        a, b = b"A" * 16, b"B" * 16
        w.key(a)
        w.stream(b"owner-A-prefix12", final=False)
        image = context(b"owner-A-prefix12", a)
        w.save(image)
        w.cancel()
        w.key(b)
        w.message(b"unrelated-B", b)
        w.restore(0)
        w.stream(b"tail")
        w.expect(b"owner-A-prefix12tail", a, resumed=True)
    else:
        raise ValueError(kind)
    return w.close()
