# RIVET-H3 interface contract

## Scope and source boundary

`rivet_h3_top` implements four independent tagged SHA-256, HMAC-SHA-256
and SHA-512 channels. `rtl/rivet_h2_*.sv` are byte-for-byte copies of
`rivet_h2_reference/rtl/rivet_h2_*.sv`; the standalone H2 interface and
hierarchy remain unchanged. No HMAC-SHA-512 is implemented.

The sole parameter is integer `PARTIAL_BEATS`, default 0, legal values 0
and 1. Other values issue `PARAMETER ERROR` and terminate simulation with
nonzero status. Channel count is fixed at four.

## Cycle and degenerate-boundary table

| Event | Pre-edge condition and post-edge effect |
| --- | --- |
| Transfer | Only valid AND ready immediately before the rising edge transfers. |
| Reset | Asynchronous active-low reset aborts all work; every public ready, valid, payload, tag, algorithm and error is zero while asserted. Release alone produces no response. |
| First released edge | Empty channels can accept commands or input; no unsolicited response. |
| Staging | Capture at E0; first byte drains E1; four bytes finish E4. Replacement cannot occur on E4. |
| Full buffer | Compression releases the block before any remaining staged bytes resume draining. |
| Empty final beat | Zero bytes, final asserted: legal on an empty message, or at any prefix with PARTIAL_BEATS=1. |
| Partial nonfinal | Legal only with PARTIAL_BEATS=1; leading bytes only. |
| Final crossing block | Retain the stage until every byte drains; padding follows the last byte, not capture. |
| Compression | Start E0; SHA-256 rounds E1..E64, done E65; SHA-512 rounds E1..E80, done E81. Controller consumes registered done on a later edge. |
| Command and input | Accepted command suppresses same-channel key/message transfer. Other channels remain independent. |
| Cancel | May interrupt computation, but not a pending digest/context response. Reset may withdraw a stalled response. |
| Response selection | Pending after P can be selected P+1, first retired P+2. |
| Response retirement | Grant clears and pointer advances at R; select R+1, next possible retirement R+2. |
| Concurrent responses | Independent digest/context arbiters can retire together; each channel blocks further work until its response retires. |
| Fault | Sticky per channel; no digest for the faulty operation; only CANCEL/reset recovers. |
| Parameters | Both PARTIAL_BEATS settings use the same staging depth. No DEPTH/MAX_WORDS/channel-count parameter exists. |

## Ports, encoding and streaming

All ports are unsigned and synchronous to `clk`, except asynchronous `rst_n`.
The command input is `cmd_valid`, `cmd_ready`, `cmd_channel[1:0]`,
`cmd_op[2:0]`, `cmd_context[2303:0]`.
Message input is `s_valid`, `s_ready`, `s_channel[1:0]`, `s_data[31:0]`,
`s_keep[3:0]`, `s_last`; the key input has corresponding `k_` ports.
Only the selected channel determines each ready signal. Senders hold valid,
tag and payload until transfer.

Bytes are leading, big-endian: data[31:24] first; keep 1000/1100/1110/1111
represents one/two/three/four bytes. Sparse masks are illegal. Nonfinal
beats must be full with PARTIAL_BEATS=0. The same rules apply to keys.
Each channel owns one stage and one active block buffer. No next message
is admitted until the previous digest retires.

Digest output is `m_valid`, `m_ready`, `m_channel[1:0]`, `m_alg[1:0]`,
`m_digest[511:0]`. Algorithms are 0 SHA-256, 1 HMAC-SHA-256, 2 SHA-512;
3 is reserved. SHA-256/HMAC use the low 256 bits with zero high bits.
Context output is `ctx_valid`, `ctx_ready`, `ctx_channel[1:0]`,
`ctx_data[2303:0]`. `error[3:0]` contains sticky per-channel faults.
Digest bytes are in published big-endian order.

Commands: 0 SHA_INIT, 1 KEY_LOAD, 2 HMAC_INIT, 3 SAVE, 4 RESTORE,
5 CANCEL, 6 SHA512_INIT; 7 faults. Reset/CANCEL selects empty SHA-256
and clears cached keys. INIT/KEY_LOAD at a nonempty quiescent prefix
faults instead of discarding input. HMAC_INIT requires a valid cached key.
Key completion returns to empty SHA-256 without a digest. Same-domain
INIT preserves parent key-cache semantics. Entering SHA-512 clears the
SHA/HMAC cache; leaving SHA-512 starts fresh SHA/HMAC state. A subsequent
HMAC_INIT therefore needs a loaded/restored key. Digest retirement prepares
another empty message in the same algorithm.

SAVE/RESTORE require a nonfinal, non-key-loading, unstaged,
noncompressing prefix and no pending response. RESTORE can replace a
nonempty prefix. SAVE freezes the channel until context retirement.
The H3 CANCEL response-preservation restriction does not change standalone H2.

## Numerical rules

SHA-256 and HMAC-SHA-256 retain FIPS 180-4 and RFC 2104/RFC 4231 behavior.
SHA-256 byte limit is 2^61-1; HMAC message limit is 2^61-65.
SHA-512 uses 128-byte blocks, eight 64-bit words, 80 rounds, modulo-2^64
arithmetic and the FIPS 180-4 IV/constants. Schedule:
W[t]=sigma1(W[t-2])+W[t-7]+sigma0(W[t-15])+W[t-16],
sigma0=ROTR1 XOR ROTR8 XOR SHR7,
sigma1=ROTR19 XOR ROTR61 XOR SHR6.
Big sigmas use rotations 28/34/39 and 14/18/41.
Padding appends 80 hex, zeroes and the entire 128-bit big-endian bit length.
A residual of at least 112 bytes needs a second block. A 128-bit byte
counter rejects a prospective count above 2^125-1 before capture.
Zero digest-bit errors are tolerated.

## Context format

SAVE always emits a 2304-bit H3 envelope:
payload [2047:0], magic [2079:2048]=52485633 hex,
version [2087:2080]=1, algorithm [2089:2088], reserved [2303:2090]=0.
The tag is outside the context, allowing migration.

For SHA/HMAC payload[1535:0] is exactly the H2 context; upper payload is
zero and the header algorithm agrees with parent mode bit 40. The H2
payload is magic [31:0]=52485632, version [39:32]=1, mode [40],
key-valid [41], reserved [47:42]=0, count [111:48], used [119:112],
chain [375:120], inner seed [631:376], outer seed [887:632],
buffer [1399:888], reserved [1535:1400]=0. Used is 0..63 and count
modulo 64; unused buffer bytes are zero. HMAC needs key-valid, invalid
key state has zero seeds, and an initial-block chain equals IV or inner seed.

SHA-512 payload: count [127:0], used [135:128], chain [647:136],
buffer [1671:648] (earliest byte most significant), reserved [2047:1672]=0.
Used is 0..127 and count modulo 128; unused bytes are zero. Count is
within its numerical limit. If count<128, chain equals SHA-512 IV.
Every header/reserved/length/consistency field is validated before install.
Zero-extended H2 contexts with [2303:1536]=0 are also accepted.
Invalid restore faults atomically; SHA-512 restore clears unused key state.
Contexts are functional state, not authenticated or confidential objects.

## Arbitration

Each output has an independent round-robin pointer initially zero. At an
unlocked edge, select the first pending channel starting at the pointer
and lock its response. Hold all fields until handshake, regardless of
arrivals. Retirement advances to winner+1 modulo four; there is one
selection bubble. Continuously pending channels wait at most three other
retirements/four selections; cycle bounds require consumer readiness.
There is strict per-channel order, not global submission order.

## Independent acceptance and reproduction

The independent Verifier owns `tests/*.py` and supplies `tests/verify.py`.
From the delivered project root, with Python 3, Icarus (`iverilog`, `vvp`)
and Yosys available, execute:

```
python3 tests/verify.py --check behavior --out evidence/behavior
python3 tests/verify.py --check compatibility --out evidence/compatibility
python3 tests/verify.py --check defects --out evidence/defects
python3 tests/verify.py --check synthesis --out evidence/synthesis
python3 tests/verify.py --check portable --out evidence/portable
```

No arguments runs all checks into a fresh directory. These are reproduction
interfaces, not claims that checks have already passed. Tool versions and
source-bound results belong in the generated evidence directories.
The mandatory behavior floor is seeds 17,89,2026 in both parameter settings;
each run includes every channel's SHA-512 lengths
0,1,3,110,111,112,113,127,128,129,239,240,255,256,257,1024;
SHA-256 lengths 0,1,3,55,56,63,64,65,119,120,127,128,129,1024;
HMAC messages 0,1,55,56,63,64,65,129 for keys 0,1,63,64,65,131.
Each run additionally requires 24 random messages per algorithm at
lengths 0..8192 and one 65536-byte message per algorithm.
This floor does not replace published vectors, context, reset, cancellation,
mask, fault-isolation, limit, arbitration and stall coverage in the admitted plan.
Direct nonfinal partial prefixes are legal only in partial mode; otherwise
validated RESTORE supplies partial-byte context setups.

Verification must compare complete messages with independent hashlib/hmac,
exercise four compiling functional mutants, and perform real Yosys
state/connectivity/no-latch checks in both settings. Portable reproduction
uses only declared deliverable sources and the parent reference.
The final independently approved product PDF is produced by the shared
runtime after engineering acceptance, not used as a verification prerequisite.

Additional mandatory acceptance includes literal published SHA empty/abc/
multiblock vectors and at least six RFC 4231 HMAC cases including long keys.
Every run must cover concurrent mixed algorithms, reallocation, key reuse/
replacement, all four digests pending during a consumer stall of at least
64 cycles, source bubbles, randomized output stalls, exact locked round-robin
sequence and late arrival, simultaneous digest/context readiness/retirement,
and a context stall of at least 64 cycles. Missing, extra or duplicate
responses, active-output X/Z, timeout, missing prerequisites, unexpected
subprocess exit or incomplete mandatory coverage must fail.

Context/migration prefixes for each algorithm are 0,1,block_size-1,
block_size,block_size+1, including HMAC seeds and continuation with and
without restore. Malformed headers, reserved bits, count/used/tail, algorithm
and key-valid fields must be rejected. Test every one of the 16 keep masks
with both finalities, command misuse/opcode 7, isolated faults, cancellation
during gather/key loading/compression, reset during gather/compression/
stalled digest/stalled context and recovery. Exercise high-count validated
contexts for all length limits and SHA-512's nonzero high bit-length half;
synthetic compression references do not replace ordinary hashlib comparisons.
Import original H2 contexts into H3 and restore H3 SHA/HMAC payloads through
standalone H2.

Disposable isolated functional defects must corrupt SHA-512 arithmetic,
change padding threshold 112 to 113, corrupt digest channel association,
and break locked-output stability. Each must compile and fail through a
real assertion/oracle, not infrastructure or an unconditional test failure.
Retain each mutant delta, command, execution log and detected assertion.
Generic synthesis must read the declared RTL, check hierarchy, lower
processes/memories, optimize, check assertions, synthesize and emit
statistics/netlists under both parameters; retain connected preflatten
channel/compression/schedule hierarchy and reject latches or missing logic.
Portable mode must execute SHA-256, SHA-512, HMAC, context migration, output
stall, illegal-parameter rejection and default H3 synthesis from copied
sources alone. Preserve failed execution records and link subsequent repairs.
