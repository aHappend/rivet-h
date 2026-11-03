"""Independent legacy expectations; no inherited verification code."""

from collections import Counter
import hashlib
import hmac
import random


def beats(data, partial=False, terminate=True):
    if not data:
        return [(0, 0, int(terminate))]
    result = []
    offset = 0
    while offset < len(data):
        size = min((1, 3, 2, 4)[len(result) % 4] if partial else 4, len(data) - offset)
        chunk = data[offset:offset + size]
        offset += size
        result.append((int.from_bytes(chunk.ljust(4, b"\0"), "big"),
                       {1:8, 2:12, 3:14, 4:15}[size], int(terminate and offset == len(data))))
    return result


def generate(path, partial, page, compact=False, seeds=(17, 29, 43), storage_boundary=False):
    counts = Counter()
    with path.open("x", encoding="ascii") as f:
        def record(op, *args):
            f.write(str(op) + " " + " ".join(map(str, args)) + "\n")
            counts["operations"] += 1

        def command(ch, op):
            record(1, ch, op, "0")

        def stream(ch, data, key=False, final=True):
            for data, keep, last in beats(data, partial=bool(partial), terminate=final):
                record(2, ch, int(key), f"{data:08x}", keep, last)

        def expected(ch, alg, message, key=None, queued=False):
            value = (hmac.digest(key, message, "sha256") if alg == 1 else
                     (hashlib.sha512 if alg == 2 else hashlib.sha256)(message).digest())
            record(18 if queued else 3, ch, alg, value.hex())
            counts["digests"] += 1

        for seed in seeds[:1] if compact else seeds:
            rng = random.Random(seed)
            record(0)
            if not compact:
                record(20); counts["concurrency_runs"] += 1
                # Legacy inputs transfer while all three new services own work.
                messages = [rng.randbytes(65) for _ in range(4)]
                for ch in range(4):
                    command(ch, 6 if ch&1 else 0)
                    expected(ch, 2 if ch&1 else 0, messages[ch], queued=True)
                streams = [beats(msg, bool(partial)) for msg in messages]
                for index in range(max(map(len,streams))):
                    for ch, words in enumerate(streams):
                        if index<len(words):
                            data,keep,last = words[index]
                            record(2,ch,0,f"{data:08x}",keep,last)
                record(19)
                # Sponge and page authentication coexist with full signature work.
                msg = rng.randbytes(137)
                output = hashlib.shake_256(msg).digest(409)
                record(4,3,len(output))
                for data,keep,last in beats(msg,bool(partial)): record(5,f"{data:08x}",keep,last)
                for data,keep,last in beats(output): record(6,f"{data:08x}",keep,last)
                counts["sponge_bytes"] += len(output)
                msg = rng.randbytes(min(page,5)); root = hashlib.sha256(b"\0"+msg).digest()
                record(7,root.hex()); record(8,len(msg),0,"0")
                for data,keep,last in beats(msg): record(9,f"{data:08x}",keep,last)
                record(11,1,0); counts["merkle_results"] += 1
                for data,keep,last in beats(msg): record(12,f"{data:08x}",keep,last)
                counts["replay_bytes"] += len(msg)
                record(21)
            lengths = (0, 1, 65) if compact else (
                0, 1, 3, 4, 55, 56, 63, 64, 65, 111, 112, 127, 128, 129, 257, 4096)
            # Four channels have live transactions together and interleaved data.
            for length in lengths:
                messages = [rng.randbytes(length) for _ in range(4)]
                algorithms = (0, 1, 2, 1)
                keys = [None,rng.randbytes(65),None,rng.randbytes(1)]
                for ch in range(4):
                    if algorithms[ch] == 1:
                        command(ch,5); command(ch,1); stream(ch,keys[ch],key=True); command(ch,2)
                    else:
                        command(ch, 6 if algorithms[ch] == 2 else 0)
                    expected(ch, algorithms[ch], messages[ch], keys[ch], queued=True)
                streams = [beats(msg, partial=bool(partial)) for msg in messages]
                for index in range(max(map(len, streams))):
                    for ch, words in enumerate(streams):
                        if index < len(words):
                            data, keep, last = words[index]
                            record(2, ch, 0, f"{data:08x}", keep, last)
                record(19)
                counts[f"four_channel_length_{length}_seed_{seed}"] += 1
            for keylen in (0, 65) if compact else (0, 1, 63, 64, 65, 128):
                key = rng.randbytes(keylen)
                command(0, 5)
                command(0, 1)
                stream(0, key, key=True)
                # Provisioning finishes with no output; HMAC_INIT readiness waits for it.
                for length in (0, 65) if compact else lengths:
                    message = rng.randbytes(length)
                    command(0, 2)
                    stream(0, message)
                    expected(0, 1, message, key)
                counts[f"hmac_key_{keylen}_seed_{seed}"] += 1
            if not compact:
                for alg in (0, 1, 2):
                    for prefix_size in ((1, 64, 65) if partial else (4, 64, 68)):
                        prefix = rng.randbytes(prefix_size)
                        suffix = rng.randbytes(257)
                        command(0, 5)
                        if alg == 1:
                            key = rng.randbytes(65)
                            command(0, 1); stream(0, key, key=True); command(0, 2)
                        else:
                            command(0, 6 if alg == 2 else 0)
                        stream(0, prefix, final=False)
                        command(0, 3); record(15, 0, 0); counts["contexts"] += 1
                        # Resume from both H3 envelope and legacy H2 payload when applicable.
                        for legacy in ((0,) if alg == 2 else (0, 1)):
                            command(0, 5); record(16, 0, 0, legacy)
                            stream(0, suffix)
                            expected(0, alg, prefix + suffix, key if alg == 1 else None)
                        command(0, 5); record(16, 0, 0, 2)
                        record(14, 1); counts["errors"] += 1; command(0, 5)
                command(0, 0); stream(0, rng.randbytes(4), final=False)
                command(0, 5); command(0, 6); stream(0, b"reset-switch")
                expected(0, 2, b"reset-switch")
                command(0, 7); record(14, 1); counts["errors"] += 1; command(0, 5)
                command(0, 0); record(2, 0, 0, "12345678", 5, 1)
                record(14, 1); counts["errors"] += 1; command(0, 5)
                if not partial:
                    command(0, 0); record(2, 0, 0, "01000000", 8, 0)
                    record(14, 1); counts["errors"] += 1; command(0, 5)
            for alg, rate in ((0, 136), (1, 72), (2, 168), (3, 136)):
                for size in (0, rate+1) if compact else (0, 1, rate-1, rate, rate+1, 3*rate+7):
                    message = rng.randbytes(size)
                    for outlen in ((32,) if alg == 0 else (64,) if alg == 1 else
                                   (3*rate+1,) if compact else (1, 3, 4, rate-1, rate, rate+1, 3*rate+7)):
                        if alg == 0:
                            output = hashlib.sha3_256(message).digest()
                        elif alg == 1:
                            output = hashlib.sha3_512(message).digest()
                        else:
                            output = (hashlib.shake_128 if alg == 2 else hashlib.shake_256)(message).digest(outlen)
                        record(4, alg, outlen)
                        for data, keep, last in beats(message, bool(partial)):
                            record(5, f"{data:08x}", keep, last)
                        for data, keep, last in beats(output):
                            record(6, f"{data:08x}", keep, last)
                        counts["sponge_bytes"] += len(output)
                if not compact:
                    record(4, alg, 32 if alg == 0 else 64 if alg == 1 else 17)
                    record(5, "01020304", 15, 0); record(22)
                    record(4, alg, 32 if alg == 0 else 64 if alg == 1 else 17)
                    record(5, "01020304", 5, 1); record(23); counts["errors"] += 1
                    record(22)
            for depth in (0, 1) if compact else (0, 1, 2, 31, 32):
                message = rng.randbytes(page if storage_boundary or not compact else min(page,3))
                siblings = [rng.randbytes(32) for _ in range(depth)]
                index = rng.getrandbits(depth)
                root = hashlib.sha256(b"\0" + message).digest()
                for level, sibling in enumerate(siblings):
                    root = hashlib.sha256(b"\1" + (sibling + root if index >> level & 1
                                                  else root + sibling)).digest()
                record(0); record(7, root.hex()); record(17)
                for corruption in ("none", "page", "proof") if depth else ("none", "page"):
                    actual = message if corruption != "page" else bytes([message[0]^1])+message[1:]
                    record(8, len(actual), depth, f"{index:x}")
                    for data, keep, last in beats(actual):
                        record(9, f"{data:08x}", keep, last)
                    for level, sibling in enumerate(siblings):
                        if corruption == "proof" and level == 0:
                            sibling = bytes([sibling[0]^1]) + sibling[1:]
                        record(10, sibling.hex(), int(level == depth-1))
                    record(11, int(corruption == "none"), int(corruption != "none"))
                    counts["merkle_results"] += 1
                    if corruption == "none":
                        for data, keep, last in beats(message):
                            record(12, f"{data:08x}", keep, last)
                        counts["replay_bytes"] += len(message)
                if not compact:
                    if depth != 32:
                        record(8, len(message), depth, f"{1 << depth:x}")
                        record(11, 0, 1); counts["merkle_results"] += 1
                    for length, baddepth in ((0, depth), (page+1, depth), (1, 33)):
                        record(8, length, baddepth, "0")
                        record(11, 0, 1); counts["merkle_results"] += 1
                    for framing in ("mask", "early_or_late", "late_complete"):
                        record(8,len(message),depth,f"{index:x}")
                        if framing == "mask":
                            record(9,"01020304",5,1)
                        elif framing == "early_or_late":
                            record(9,"01000000",8,int(len(message)>1))
                        else:
                            words = beats(message)
                            for data,keep,last in words:
                                record(9,f"{data:08x}",keep,0)
                        record(11,0,1); counts["merkle_results"] += 1
                    if depth:
                        for framing in ("late", "early") if depth>1 else ("late",):
                            record(8,len(message),depth,f"{index:x}")
                            for data,keep,last in beats(message): record(9,f"{data:08x}",keep,last)
                            for level,sibling in enumerate(siblings):
                                last = (level==0) if framing=="early" else False
                                record(10,sibling.hex(),int(last))
                                if last: break
                            record(11,0,1); counts["merkle_results"] += 1
        record(0)
    counts["storage_boundary"] = int(storage_boundary)
    return dict(counts)
