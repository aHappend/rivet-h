# RIVET-H5 implementation architecture

## Integration and trust boundary

`rivet_h5_top` instantiates the unchanged inherited `rivet_h4_top` as `u_parent`.
Every legacy signal and parameter passes directly through, with no arbitration
or timing modification. The 15 production copies have the same implementation
as `rivet_h4_reference/rtl/`. Historical parent STA and connectivity-only PPA/HIL
provenance is in `GENERATIONAL_HANDOFF.md`; it is not current H5 signoff.

The three new top-level services are transaction-independent. `u_ntt` is a raw
canonical polynomial transform, `u_sampler` supplies polynomial distributions,
and `u_verify` authenticates manifests. They have separate storage, controllers
and arithmetic/XOF resources. The verifier contains its own `u_ntt`,
`u_sampler` and `u_hash`. Each NTT contains `u_butterfly.u_montgomery`; each
sampler contains `u_xof.u_keccak`. `u_hash` also uses inherited Keccak.
These are connected datapaths, not expected-answer or witness interfaces.

Provisioning a public key is a trusted integration action, analogous to pinning
the inherited Merkle root. It does not establish trust in an arbitrary host key.
The key locks only after receiving its exact bytes and computing tr; cancellation
before that point leaves it unprovisioned. Reset removes the lock. Verify/cancel
and overwrite errors preserve an already locked key. The signature service
reports authentication but adds no unauthenticated manifest-release mechanism.
Pure contextual ML-DSA is supported, not signing or HashML-DSA/prehash.
Side-channel resistance, fault tolerance and secure host provisioning are not
established by numerical functional verification.

## Boundary schedule

See the normative Cycle & Degenerate-Boundary Table in `SPEC.md`.
Transfers depend on pre-edge ready/valid; all controller updates and arithmetic
outputs occur after the edge. Commands never share their acceptance edge with
the first input beat. Results, coefficients and indices are held under stalls.
Exposed new payloads and statuses are zero when their valid is low.
Asynchronous reset suppresses handshakes immediately; synchronous cancellation
has priority over all transfers and clears pending state without completion.
Subordinate arithmetic without a clear input is flushed with a registered local
reset request following the cancellation edge. Its ownership is not reused
until the cancellation-cleared controller can issue a new operation.

## Montgomery and butterfly stages

The Montgomery leaf has one transaction slot and an 11-interval pipeline.
The output state remains occupied until `m_ready` retires the result.

| Edge from acceptance | Registered work |
|---|---|
| E0 | Capture canonical a,b. |
| E1 | Four low16/high7 partial products for T. |
| E2 | Two aligned pair sums, 48 bits. |
| E3 | Assemble the exact 46-bit T. |
| E4 | Three <=16x16 partial products for low32(T * 4236238847). |
| E5 | Register the 33-bit cross-term sum. |
| E6 | Assemble the low 32-bit reduction word. |
| E7 | Four <=16x16 partial products of reduction word and q. |
| E8 | Register 56-bit aligned pair sums. |
| E9 | Assemble reduction word * q. |
| E10 | Carry-preserving 57-bit sum with T. |
| E11 | Normalize upper word with one conditional q subtraction; set valid. |

This is the additive Montgomery convention, not a signed-subtractive shortcut.
For canonical inputs the upper word needs at most one subtraction.
No multiplication is wider than 16x16 operands. No division/modulo operator
implements reduction. Shift and concatenation widths preserve product/carry bits.

Butterfly E0 captures u,v,zeta/direction. E1 issues the Montgomery operation
and registers canonical u+v. Inverse multiplier input is canonical u-v;
forward input is v. The Montgomery result appears post-E12 and is consumed
by the butterfly at E13. Forward registers canonical u +/- result; inverse
registers parallel sum and product. Thus both directions have 13 intervals.
Arithmetic callers supply canonical coefficients and already-encoded twiddles.

## NTT RAM schedule and representation

The NTT owns one 256x23-bit polynomial RAM with synchronous paired reads and
paired writes. The receive controller rejects framing/noncanonical values
before any output; a complete legal polynomial is required before computation.
The fixed byte-aligned ROM stores 256 values
R * 1753^BitRev8(k) modulo q. Entry zero is not used by butterflies.

Forward starts length=128/index=1; inverse starts length=1/index=255.
Within a group j traverses its first half; the second operand is j+length.
Every group advances its twiddle once. Stage/group counters use explicit
256-element limits, not an implicit wrap assumption. Inverse negates each
reverse-order Montgomery twiddle. A final forward-form butterfly with u=0,
v=value, zeta=16382 implements normal-domain inverse normalization.

Each ordinary butterfly uses READ_PAIR, READ_WAIT, BF_SEND, BF_WAIT and
NEXT_PAIR. Synchronous operand reads precede dispatch; BF_WAIT writes both
results only on the accepted butterfly output. One butterfly schedule occupies
18 unstalled clocks; there are 8*128=1024 butterflies. Inverse normalization
uses READ, WAIT, SEND and RESULT with 17 unstalled clocks per coefficient.
Output uses READ, WAIT, SEND, three clocks per coefficient without stalls.
From final input acceptance to pending completion, the FSM accounts for
19200 clocks forward and 23552 inverse when no service stalls intervene.
The normative independent progress limit is 65536 clocks, not a claimed
single-cycle transform or subprocess wall-clock timeout.

All public transform values are normal-domain, canonical representatives.
Montgomery twiddles make each butterfly's root multiplication normal-domain.
`Mont(value,16382)` gives the public inverse factor 1/256. The verifier's
point products first apply Mont(a,b), then Mont(intermediate,2365951), yielding
normal a*b. Accumulation, transformed z/c/t1 and inverse inputs consequently
all share the same normal representation. ExpandA already supplies the
prescribed NTT-domain matrix coefficients and is not transformed again.

## Continuing SHAKE and sampler

The XOF stores a 1600-bit state, rate and byte cursor. Absorb XORs bytes into
increasing byte positions. A full absorption block dispatches the inherited
24-round permutation and resumes absorption at cursor zero. A final byte on a
rate boundary first permutes that full block, then pads an additional block.
Suffix and final-bit insertion are separate clock stages, correctly combining
0x1f and 0x80 when they occupy the same byte. Empty input pads a zero state.
After final permutation, squeeze exposes one held byte; rate exhaustion
dispatches another permutation of the full state without re-padding.

Inherited Keccak uses four registered phases per round: parity, theta/rho/pi,
chi and iota; 96 phase clocks plus dispatch/capture handshake overhead per
permutation. XOF clear abandons absorption/permutation/squeeze. An illegal
keep=0 nonempty or nonfinal transfer enters an explicit fault state until
clear; the sampler/verifier never issue such transfers.

The sampler buffers its complete 256 coefficients before output. The seed
serializer emits first-byte-at-low-bus-bit order and nonce low byte then high
byte. ExpandA selects SHAKE128/32-byte seed; SHAKE256 uniform/ExpandS/Mask
select 64-byte seed; SampleInBall uses level-dependent challenge length and no
nonce. SHAKE blocks continue on actual byte demand, never a guessed attempt cap.

Uniform parser consumes three bytes and one candidate-check clock. Rejected
23-bit candidates do not advance the coefficient index. ExpandS consumes a byte,
then checks low and high nibbles in separate clocks; the eta=2 residue is a small
bounded lookup. ExpandMask has a 40-bit little-endian reservoir and explicit
18/20-bit field consumption. In SampleInBall, ZERO initializes 256 RAM entries,
SIGN_GET captures eight sign bytes, and BALL_GET rejects indices larger than
the current construction index. READ/WAIT/COPY/SIGN performs the exact in-place
swap; separate writes also handle a self-swap correctly. One sign bit is consumed
per accepted construction step, least-significant first.

Every mode uses three-clock synchronous RAM output scheduling per coefficient,
then a held completion. Rejection and rate-boundary permutations determine
overall latency, so it is data-dependent; the independent 65536-clock progress
assertion remains required. Input/output stalls add their actual accepted gaps.

## Signature controller and bounded memory

| Storage | Capacity/layout | Lifetime |
|---|---|---|
| Trusted key | Four unpacked byte lanes x 648 words, 2592 bytes | Provisioning through reset |
| Signature | Four unpacked byte lanes x 1157 words, 4628 allocated bytes | One verify transaction |
| Transformed z | 1792 x 23 bits, polynomial/index addressing | Decode through all matrix rows |
| Scratch polynomial | 256 x 23 bits | z/c/A/t1/inverse-row staging |
| Transformed c | 256 x 23 bits | All verification rows |
| Transformed t1 | 256 x 23 bits | Current row |
| Accumulator | 256 x 23 bits | Current matrix row |
| Hint bitmap | 2048 x 1 bit | Current signature, zeroed sequentially for k rows |
| Prefix/packing registers | rho32, tr64, mu64, c64 bytes; small bit reservoirs | Key or transaction |
| Stream beat buffer | Four bytes | One context/message beat |

All large memories have clock-only registered reads/writes, validity-gated
accesses and no asynchronous content reset. Byte writes use explicit lane arrays
for Quartus 17.1 inference. Small endpoint registers are initialized by reading
every required endpoint before access, not by clearing large memories.
No complete matrix, manifest or w1 vector is retained. Matrix expansion,
point products, accumulation, inverse, decomposition and hashing are serialized.

RX validates expected section kind, keep, 33-bit proposed byte count and exact
last before writing or hashing a beat. Nonfinal beats include exactly four
MSB-first bytes. Signature/raw-key storage uses the aligned word index; byte
decoders translate this stream into little-endian packed coefficient fields.

Provisioning hashes every stored key byte to tr, captures rho and only then
locks the key. Verification first captures the exact signature, decodes c and
each z polynomial, checks every infinity norm and transforms z into its resident
NTT bank. The decoder parses all cumulative hint endpoints, enforces their
monotonicity/omega bound, then enforces strictly increasing indices per row and
zero unused index storage. Errors produce held exact status, never authentication.

The mu hash consumes tr || 00 || context length, then context and message.
RX_DRAIN serializes each accepted nonempty beat. Empty section marker beats
do not insert hash bytes. Since lengths are known, the final included byte is
marked last even when it belongs to context or prefix before an empty message;
the required empty marker beats still must be received/validated. Arbitrarily
long messages only occupy the four-byte beat buffer.

The challenge sampler constructs c, then NTT computes c_hat. The challenge-check
XOF starts with mu and remains suspended in absorption while rows are computed.
Each row clears its accumulator sequentially. For every column, ExpandA fills
scratch with A_hat[row][col], and PROD_READ/WAIT plus two registered Montgomery
transactions computes each ordinary point product. ACC_WRITE adds canonically.
The key decoder then unpacks that row's 10-bit t1 fields, shifts by d=13,
transforms them and uses the same two-pass product schedule to subtract c_hat*t1_hat.
The canonical row accumulator passes through normal-domain INTT into scratch.

`u_usehint` implements mathematical Decompose by a 23-step restoring divider
with one registered shift/subtract per clock, followed by a separate
round/wrap/UseHint output stage. Alpha and gamma2 select the exact level-dependent
constants. A rounded quotient of 44/16 wraps to zero with negative low part,
covering q-1 and the exceptional top interval. Positive low parts increment
the high part with wrap on hint=1; zero/negative low parts decrement with wrap.
This preserves both centered-remainder boundaries without combinational division.

W_READ/WAIT/SEND supplies synchronous row/hint values. Each accepted high part
is packed into a 16-bit little-endian reservoir, using six or four bits.
W_DRAIN hashes complete bytes under SHAKE backpressure. Rows are byte aligned.
The final packed byte terminates the hash; CC_OUT compares every reconstructed
challenge byte, accumulating mismatch including the last byte before deciding.
`reconstructed_challenge` is an internal register for test-only hierarchical
observation, not a production port or supplied witness.

The two-pass point-product schedule occupies 30 unstalled clocks per coefficient.
There are 256*k*(l+1) products (at most 16384), plus l+k+1 forward transforms and
k inverse transforms. Decompose has 23 iterations per row coefficient.
Matrix sampling, decoding, byte hashing and synchronous RAM staging add their
FSM costs. These are architectural cycle accounts, not measured simulation
latency. Independent verification must assert completion within 16000000
clocks after all input is accepted without external stalls.

## Dependencies, reproduction and claim-to-evidence mapping

Deliverable sources are `rtl/*.sv`, `design/*.md` and Verifier-owned flat
`tests/*` sources/fixtures; the immutable parent is a comparison input.
Use existing Python 3, Icarus/vvp, Verilator, make, g++ and Yosys. Exact dependency
versions and source hashes belong to fresh execution receipts, not presumed
host versions. From this root:

```
python3 tests/verify.py --suite behavior
python3 tests/verify.py --suite defects
python3 tests/verify.py --suite synthesis
python3 tests/verify.py --suite portable
```

| Claim | Required independent evidence |
|---|---|
| Arithmetic/scaling, SHAKE/sampling, actual ML-DSA authentication | `evidence/behavior-*`, public KAT provenance and coefficient/byte comparisons |
| Oracle sensitivity | `evidence/defects-*`, compiled/executed disposable mutations with discriminating failures |
| Synthesizability, no latches/div/mod, substantive hierarchy | `evidence/synthesis-*`, complete retained machine-readable netlists |
| Clean-root portable reproduction | `evidence/portable-*`, fresh compact behavior and leaf synthesis |
| <=10.0 ns physical timing | Native timing lint and Quartus 17.1 post-fit STA |
| Physical H5 functionality | Three consecutive deterministic native hardware functional passes |
| Product acceptance/PDF | Independent Reviewer and subsequent shared-runtime approved report |

The verification entrypoint and evidence are produced independently after this
Designer handoff. These paths are evidence selectors, not statements that checks
have passed. Native L1.5/L2/L3 gates remain mandatory and are not duplicated or
invented in portable L1. No PDF is required before engineering acceptance.
Exclude runtime metadata, account paths, credentials, transcripts and old evidence
from portable source selection. No installation, publish or deployment is part
of this Designer operation.
