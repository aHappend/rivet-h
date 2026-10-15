# RIVET-H2 integration specification

## Product and numerical rules

Top: `rivet_h2_top`. Synthesizable sources: `rtl/*.sv`. Immutable compatibility
reference: `rivet_h1_reference/rtl/*.sv`. Independent verification entry point:
`tests/verify.py` (owned by Verifier).

SHA-256 follows FIPS 180-4: eight 32-bit chaining words, modulo-2^32 additions,
standard constants/rotations, big-endian message words and 64-bit big-endian
bit-length padding. HMAC-SHA-256 follows RFC 2104 and RFC 4231, with
`K0 = zero_pad_to_64(key)` for keys <=64 bytes and
`K0 = SHA256(key) || 32 zero bytes` otherwise. Empty keys are legal. The
installed seeds are the compression results of `K0 xor 0x36` and `K0 xor 0x5c`
from the SHA IV. The full 256-bit digest is returned, including RFC case 5
(whose 128-bit prefix is an additional verification requirement).

Maximum SHA message/key size is `2^61-1` bytes. Maximum HMAC user message size
is `2^61-65` bytes, excluding the 64-byte ipad prefix. Reject a whole
overflowing accepted beat before consuming any of its bytes. Exact digest
comparison permits zero bit mismatches; numerical approximation is inapplicable.

## Public ports

All ports are unsigned. There is one clock domain.

| Direction | Ports |
| --- | --- |
| Input | `clk`, active-low asynchronous `rst_n` |
| Input | `s_valid,s_data[31:0],s_keep[3:0],s_last` |
| Output | `s_ready` |
| Output | `m_valid,m_digest[255:0],error` |
| Input | `m_ready` |
| Input | `k_valid,k_data[31:0],k_keep[3:0],k_last` |
| Output | `k_ready` |
| Input | `cmd_valid,cmd_op[2:0],cmd_context[1535:0]` |
| Output | `cmd_ready,ctx_valid,ctx_data[1535:0]` |
| Input | `ctx_ready` |

Only public parameter: integer `PARTIAL_BEATS=0`; legal values are 0 and 1.
Unsupported values issue an explicit parameter diagnostic and are not supported
hardware configurations.

### Reset and streaming

While reset is asserted every public output is zero, including data, readiness,
validity and error. Reset cancels outputs/work, clears keys, stages, buffers and
counters and selects empty SHA. Deassert reset before supplying valid traffic;
the first post-reset rising edge may accept a transfer. No physical secure
erasure claim follows from logical reset.

Sample handshakes immediately before each rising edge. Upstream holds valid
and payload stable until handshake. Bytes enter most-significant lane first:
`[31:24],[23:16],[15:8],[7:0]`. A captured beat is staged once, then drains at
most one byte per subsequent edge; readiness is low while staged. A full block
can interrupt draining without discarding the rest of the beat.

With `PARTIAL_BEATS=0`, non-final beats require `1111`; final beats permit
`1000,1100,1110,1111`. `0000` is legal only for an empty final message/key.
With `PARTIAL_BEATS=1`, non-final `1000,1100,1110` are additionally legal, and
final `0000` is legal at any byte count. Zero-byte non-final and non-contiguous
masks remain illegal in both configurations. Key stream rules are identical.
Only the selected stream can transfer; message/key streams never interleave.

Input gaps and output stalls are unrestricted. Digest and context validity and
payload hold during stalls except reset or accepted CANCEL. No input without a
handshake changes state. Digest retirement starts another empty message in the
same mode with the same key. No same-edge new message acceptance is possible.
Default-mode mask/error behavior retains H1 compatibility, not its latency.

## Commands, arbitration and faults

| Encoding | Operation |
| --- | --- |
| 0 SHA_INIT | Select empty SHA, retaining installed seeds. Requires zero current user bytes and quiescence. |
| 1 KEY_LOAD | Invalidate old key and enter exclusive streamed key ingestion. Requires zero user bytes and quiescence. Normalize complete key, derive both seeds, then return to empty SHA. |
| 2 HMAC_INIT | Select empty HMAC from installed inner seed. Requires key, zero user bytes and quiescence. |
| 3 SAVE | Non-destructive canonical snapshot at quiescence. |
| 4 RESTORE | Validate and atomically replace the entire context, including mode and key ownership. Can replace nonempty quiescent state. |
| 5 CANCEL | Ready whenever reset is high. Clear pending work, outputs, fault and installed keys; select empty SHA. |
| 6,7 | Illegal accepted command faults. |

Quiescence means no staged beat, no full uncompressed block, compressor idle,
no finalization/key processing and no pending output. Ordinary command readiness
exists only then, outside FAULT. Key/message count restrictions are legality
checks on accepted commands: a key change in a nonempty quiescent message
faults, rather than silently changing its ownership.

An eligible valid command suppresses stream readiness, so no simultaneous
command and stream transfer occurs. CANCEL wins over every update, including
done and output retirement, and remains ready during key loading, compression,
fault and stalled outputs. Unsupported commands while busy are unaccepted and
have no effect. SAVE/RESTORE while padding/compression/key processing or output
pending must wait. If held through digest retirement they operate on the new
empty context, not on the preceding in-flight message.

Accepted illegal masks, overflowing lengths, malformed contexts, invalid
commands or HMAC_INIT without a key enter sticky FAULT with `error=1`. In FAULT
all readiness/validity except CANCEL readiness are zero. Only reset or CANCEL
recovers; no digest or context is emitted for the rejected transaction.

## Context format version 1

Both context buses have exactly 1536 bits. State word H0 is most significant;
the earliest partial byte occupies buffer bits `[511:504]`.

| Bits | Meaning |
| --- | --- |
| `[31:0]` | Magic `32'h52485632` |
| `[39:32]` | Version `8'd1` |
| `[40]` | Mode: 0 SHA, 1 HMAC |
| `[41]` | Installed key valid |
| `[47:42]` | Zero |
| `[111:48]` | Unsigned 64-bit user message bytes, excluding ipad |
| `[119:112]` | Used partial bytes, 0..63 |
| `[375:120]` | Current 256-bit chaining state |
| `[631:376]` | 256-bit inner seed |
| `[887:632]` | 256-bit outer seed |
| `[1399:888]` | 512-bit partial block, earliest byte most significant |
| `[1535:1400]` | Zero |

Validation checks magic/version/reserved bits; mode-specific count limit;
used <=63 and equal to count modulo 64; every unused buffer byte zero; HMAC
requires a key; missing key requires both seeds zero. If count <64, chain must
equal SHA IV in SHA mode or inner seed in HMAC mode. Later chaining states and
installed seeds are opaque, not authenticated/recomputed.

SAVE emits only canonical quiescent images. At a completed block boundary used
is zero and chain includes the block. RESTORE validates the entire image before
any field is installed; malformed images fault atomically. Padding uses count
for SHA and count+64 for HMAC. No raw normalized key, compressor working state,
schedule or transient padding/key hash state is exported or required.

Images contain sensitive key-derived state, are not encrypted or authenticated,
and require trusted software. Structural validation is not a security boundary.
No external key identity is consulted after restore. Software can interleave
any number of images; restoring replaces all active ownership.

## Timing, reproduction and independent acceptance

`ARCHITECTURE.md` freezes internal boundaries, the complete control-state
timing and Cycle & Degenerate-Boundary Table. Compressor launch L executes
rounds at L+1..L+64, registers feed-forward/done at L+65 and is consumed at
L+66. SAVE accepted at E registers validity/image after E; RESTORE commits or
rejects after E; neither admits same-edge resumed traffic or retirement of a
new output.

Required executables are Python 3 with standard `hashlib`/`hmac`, Icarus
(`iverilog`, `vvp`), Verilator with `make`/`g++`, and Yosys. Their actual versions
and measurements belong in source-bound independent results, not invented here.
Run from the delivered project root, using fresh output directories (never
overwrite failed results):

```sh
python3 tests/verify.py --check behavior --output evidence/behavior
python3 tests/verify.py --check compatibility --output evidence/compatibility
python3 tests/verify.py --check defects --output evidence/defects
python3 tests/verify.py --check synthesis --output evidence/synthesis
python3 tests/verify.py --check portable --output evidence/portable
```

Behavior acceptance requires real Icarus seeds 17, 89 and 2027 in both legal
configurations, each cell with >=100 independent SHA and >=100 independent
HMAC completions and >=100 switches across four software contexts. Required
directed coverage includes all seven RFC 4231 cases, standard SHA vectors and
million-a, specified key/message boundaries, every partial residue, structural
context rejection, synthetic near-limit padding/overflow, reset/cancellation,
100-cycle output stalls, arbitration and active X/Z checks. Intermediate-state
expectations require an independent compression model cross-checked against
hashlib on >=32 distinct complete messages. Verilator must independently
compare >=25 SHA and >=25 HMAC completions per legal parameter.

Compatibility independently re-executes the immutable H1 and H2 default against
the reference expectations for >=100 paired legal messages and all directed
mask/error/reset/stall cases, without requiring equal timing. Six compiling,
executed disposable mutations must fail identified functional assertions:
SHA arithmetic/schedule, ipad/opad, long-key normalization, restored partial
buffer, length/padding and restored outer-seed/key ownership, including a SHA
compatibility witness and an interleaved-context witness.

Yosys must synthesize both legal configurations with checked hierarchy, actual
storage/arithmetic, driven outputs, no black boxes, no latches and no reported
combinational loops. Retain raw execution, source hashes, seeds, actual counts,
cycle measurements, module/source sizes, generic cell/state counts and exact
commands. Tool child timeouts are at least 3600 seconds with explicit workload
cycle watchdogs; elapsed wall time is not numerical acceptance.

Portable reproduction copies only declared RTL, reference RTL, tests and
documentation into a fresh project-local clean directory, rejecting private
paths and runtime dependencies. It executes a bounded subset (SHA, empty/long
key HMAC, partial context round trip, stalled output and cancellation) and
default Yosys; this is not the full matrix. Evidence is retained for review,
not embedded wholesale in deliverables. Runtime metadata is not an input.

No functional, mutation, compatibility or synthesis pass is claimed by this
design specification. Independent Verifier and Reviewer follow implementation.
The independently approved product PDF is authored/rendered by the shared
runtime after engineering acceptance, not a prerequisite for those checks.
No physical area, timing closure, FPGA measurement or silicon-security claim
is part of this functional RTL delivery.
