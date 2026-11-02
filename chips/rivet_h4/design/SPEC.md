# RIVET-H4 frozen design contract

## Authority and scope

Top: `rivet_h4_top`. Target: Intel Arria 10 GX `10AX115N2F45E1SG`,
100 MHz or faster, clock period at most 10.0 ns. This document implements the
independently admitted H4 work order; neither source intake nor static
elaboration constitutes acceptance. Native timing, physical-board gates and the
independently approved product PDF remain mandatory under shared-runtime
ownership, after independent functional verification.

The supplied eleven `rivet_h3_reference/rtl/*.sv` files are immutable provenance.
The delivered hierarchy is self-contained in `rtl/`. No linked intake source
index or `design/GENERATIONAL_HANDOFF.md` was supplied. Historical parent STA/PPA
is therefore unavailable; no parent timing comparison is asserted. Authorized
restoration of that handoff remains an integration input, not a fabricated result.

## Common rules and legal parameters

All signals are unsigned. One rising-edge `clk`, asynchronous active-low `rst_n`.
Every public output is zero during reset. Transfers use pre-edge valid and
ready; resulting register updates are post-edge. Producers hold valid/payload
until acceptance. Output valid/payload/tags/keep/last remain stable under
backpressure, except an accepted sponge CANCEL aborts its transaction.
Reset discards all pending work and requires root reprovisioning.

`PARTIAL_BEATS` defaults to 0 and is legal only at 0 or 1.
`MAX_PAGE_BYTES` defaults to 4096 and is legal at every integer 1 through 4096.
Illegal parameters cause an explicit diagnostic, not silent clamping.
RTL contains no division/remainder operators and no mixed blocking/nonblocking
state assignments in sequential blocks. Arithmetic is staged between registers;
only actual native Quartus STA can establish timing closure.

## Cycle and degenerate-boundary table

| Boundary/event | Pre-edge condition | Post-edge behavior |
| --- | --- | --- |
| Active reset | `rst_n=0` | All public outputs zero, work and trust flushed |
| First released edge | Idle ready may assert | Only pre-edge handshakes transfer |
| Command/start E0 | Valid and ready | Metadata latched; same-interface data suppressed at E0 |
| Data edge D | Valid and ready | Capture only pre-edge beat; no combinational digest/result |
| Stalled output | Valid and not ready | Identical valid, data, keep, last and tags after edge |
| Sponge CANCEL | Command accepted in any state | Wins over input/output; fault and pending work cleared |
| Keccak launch E0 | `start && !busy` | Capture state; busy asserted |
| Keccak round r | E(4r+1), +2, +3, +4 | Parity, theta/rho/pi, chi, iota respectively |
| Keccak E96 | Last iota | Final state registered, busy drops, done pulses one cycle |
| Merkle verdict V | Registered digest available | Latch result and exactly one status; no tile transfer at V |
| Successful replay | V+1 or later | Only authenticated bytes eligible; stable independent stalls |
| Final tile acceptance | Valid and ready | Retire tile once; start waits also for result consumption |
| Page capacity 1 | One byte with final | One atomic quarantined tile; same authentication rules |
| Page capacity 3 | Non-power-of-two limit | Explicit bounds; no power-of-two address wrapping |
| Depth 0 | Index 0; no siblings | Compare leaf hash directly to pinned root |
| Depth 32 | Any 32-bit index | Consume exactly 32 siblings, bits 0 through 31 |
| Simultaneous root/start | Root initially unlocked | Root can latch, but start is not ready until a later edge |
| Result and tile ready | Independent handshakes | Neither handshake alone retires the other obligation |
| Failure/new start | Failed result must first retire | Drop eligibility; next accepted descriptor clears old status |

## Legacy interface and compatibility

Preserve the exact `rivet_h3_top` ports on H4:
`s_valid/s_ready,s_channel[1:0],s_data[31:0],s_keep[3:0],s_last`;
`k_valid/k_ready,k_channel[1:0],k_data[31:0],k_keep[3:0],k_last`;
`cmd_valid/cmd_ready,cmd_channel[1:0],cmd_op[2:0],cmd_context[2303:0]`;
`m_valid/m_ready,m_channel[1:0],m_alg[1:0],m_digest[511:0]`;
`ctx_valid/ctx_ready,ctx_channel[1:0],ctx_data[2303:0]`; `error[3:0]`.
Directions are identical to the parent.

Commands 0..6 are SHA256_INIT, KEY_LOAD, HMAC_INIT, SAVE, RESTORE,
CANCEL, SHA512_INIT; 7 faults. Tags 0,1,2 identify SHA256,HMAC-SHA256,SHA512.
SHA256/HMAC use low 256 digest bits and zero upper bits. Retain four channels,
RHV2/RHV3 layouts and validation, count limits, key normalization/cache lifetime,
fault recovery, command priority and locked round-robin output arbitration.
Cryptographic/protocol compatibility is required, not identical compression latency.

Input bytes are MSB first. Contiguous keeps are 1000,1100,1110,1111.
With PARTIAL_BEATS=0 partial beats are final only and zero keep is legal only
for an empty final message; value 1 preserves broader partial/final-zero support.

Literal hierarchy: H4 instantiates `rivet_h3_top u_legacy`,
`rivet_h4_sponge u_sponge`, `rivet_h4_merkle u_merkle`.
Legacy retains four `g_channel` instances of `rivet_h3_channel u_channel`,
each with `rivet_h2_top u_h2`, `rivet_h3_sha512 u_sha512` and their stream,
context, HMAC, schedule and compressor submodules.

## Sponge interface and numerics

Inputs: `x_cmd_valid,x_cmd_op,x_alg[1:0],x_out_bytes[31:0]`,
`x_s_valid,x_s_data[31:0],x_s_keep[3:0],x_s_last,x_m_ready`.
Outputs: `x_cmd_ready,x_s_ready,x_m_valid,x_m_data[31:0],x_m_keep[3:0]`,
`x_m_last,x_error`. `x_cmd_op` is one bit: START=0, CANCEL=1.
One transaction, independent of legacy and Merkle. START only idle/unfaulted;
CANCEL always ready outside reset and dominates all other work.
No implicit transaction after reset. Illegal accepted START or malformed accepted
data enters sticky fault without successful output, until CANCEL/reset.

| x_alg | Function | Rate bytes | Capacity bits | Suffix | Output bytes |
| --- | --- | --- | --- | --- | --- |
| 0 | SHA3-256 | 136 | 512 | 06 | Exactly 32 |
| 1 | SHA3-512 | 72 | 1024 | 06 | Exactly 64 |
| 2 | SHAKE128 | 168 | 256 | 1f | 1..4294967295 |
| 3 | SHAKE256 | 136 | 512 | 1f | 1..4294967295 |

FIPS 202 Keccak-f[1600] uses 24 normative theta/rho/pi/chi/iota rounds.
Lane A[x,y] is bits `64*(x+5*y)+:64`; earliest byte is lane-zero low byte.
Boundary conversion preserves external MSB-first bytes and internal little-endian
lanes. Padding XORs the suffix at the next byte and 80 at the final rate byte,
combining both in one byte when necessary. Exact-rate input gets a new pad block.
Squeezing permutes the existing state without reabsorbing padding.
The 64-bit input count faults on overflow. Output storage is constant size,
not proportional to XOF length. First output byte is bits 31:24, unused low bytes
zero, high-contiguous keep, last on the final beat only.

`u_sponge.u_keccak` ports are `clk,rst_n,clear,start,state_in[1599:0]`
and `busy,done,state_out[1599:0]`. Clear dominates launch. Launch only idle.
Fixed 96-cycle latency as in the table; state_out holds until completion/clear/reset.

## Merkle trust, interface and quarantine

Dedicated `u_merkle.u_hash` is `rivet_h2_top` with partial-beat support.
Leaf: SHA256(00 || exact page bytes).
Parent: SHA256(01 || left digest || right digest).
Digest concatenation uses conventional hashlib byte order.
Sibling i arrives leaf-to-root: index bit i=0 places current hash left,
bit i=1 places current hash right. No implicit odd-node duplication.

`root_valid/root_ready,root_digest[255:0],root_locked` provisions one pinned root
per reset. Ordinary commands cannot replace/unlock it. Provisioning is trusted;
hostile reset, malicious provisioning, side channels and key secrecy are not solved.

Descriptor inputs: `merkle_start_valid,merkle_page_bytes[31:0]`,
`merkle_depth[5:0],merkle_leaf_index[31:0]`; output `merkle_start_ready`.
Page: `merkle_s_valid/merkle_s_ready,merkle_s_data[31:0]`,
`merkle_s_keep[3:0],merkle_s_last`.
Proof: `proof_valid/proof_ready,proof_digest[255:0],proof_last`.
Result: `merkle_result_valid/merkle_result_ready,merkle_auth_ok,err_merkle_tamper`.
Replay: `tile_valid/tile_ready,tile_data[31:0],tile_keep[3:0],tile_last`.

Latch metadata at start. Length 1..MAX_PAGE_BYTES; depth 0..32.
For depth below 32 require index less than 2^depth; depth zero requires index zero.
Invalid descriptors are accepted while ready and fail without consuming data.
Receive the complete page before siblings; proof_ready remains low until leaf
hashing completes. Exactly depth siblings; proof_last iff level=depth-1.
Page keeps are nonzero high-contiguous, partial only final, regardless of
PARTIAL_BEATS. Require exact byte count and final at the declared length.
Malformed masks, too-short/long/missing final, malformed proof framing, invalid
metadata or unequal root fail. An absent future beat is a stall, not a timeout.
Failure drops content eligibility, stops input acceptance and returns failed result;
restart requires a new descriptor, not replay of the abandoned stream.

At verdict V register result_valid and exactly one auth/tamper status. Status
holds until next accepted start/reset; result_valid holds until accepted.
No tile_valid or nonzero tile payload before authentication. Successful replay
starts no earlier than V+1, in original order with exact keep/last and stalls.
Failure never releases a byte. Page is one atomic tile. Clear read eligibility on
start/failure/reset; stale RAM is not eligible. New start requires result retirement
and completed successful replay, or retired failed result. Reset suppresses
outputs immediately and requires a new root. Other interfaces cannot cancel Merkle.

## Independent acceptance and delivery

Designer owns `rtl/*.sv` and `design/*.md`, at most static elaboration.
Verifier independently authors flat `tests/*`, including portable `tests/verify.py`,
models, transactors, synthesis and disposable mutation checks. Generated artifacts
are not source inputs. Public reproduction:

```
python3 tests/verify.py --suite all --output-root evidence/l1
```

The admitted complete L1 matrix remains mandatory: hashlib/hmac parity on every
legacy algorithm/channel and all specified block/padding/key/context boundaries;
both PARTIAL_BEATS settings, RHV2/RHV3 cross-channel context validation,
overflow and malformed contexts; compact parent protocol comparisons.
Sponge includes empty/abc, every admitted rate boundary through 4096 bytes,
the complete SHAKE message/output Cartesian matrix, and 16 random cases per
mode per seed 11,29,47. Independently compare ten or more permutation states
(zero, all-one, eight seeded), exact 96-cycle latency, all stalls/cancel/fault/reset.

Merkle covers capacities 1,3,4096, all legal admitted page boundaries, depths
0,1,2,5,32, both sibling orders at each reachable level and mixed/extreme indices,
seeds 11,29,47, exact replay, no premature bytes, independent result/replay stalls,
concurrency, root overwrite and reset during receive/hash/proof/replay.
Reject page, every sibling-level, index/order/root mutations and malformed framing;
demonstrate successful recovery after each recoverable failure.
Coverage must be observed, with zero mismatches/unauthorized bytes.

Disposable compiled mutants separately alter Keccak RC, suffix, cross-rate squeeze,
sibling order, root equality and release gating. Each must compile and fail the
independent checker for its intended mismatch, not timeout or compile error.
Run real compact Icarus behavior (at most 500000 cycles, designed below 60 seconds
per vvp), compiled Verilator full matrices, full-live-top Yosys synthesis across
both partial modes and page variants, no latches/black boxes/undriven live outputs/
divider/remainder cells, substantive connected state in all branches, retained RAM
inference, illegal-parameter diagnostics and clean-directory smoke reproduction.
Retain unique source-bound receipts, failed runs, raw logs and repair links.
Missing subordinate artifacts must trigger their generators.

The shared runtime executes L1.5 timing lint, L2 Quartus 17.1 actual-H4 STA
(at most 10.0 ns constraint, nonnegative setup slack and clean hold/constraints)
and L3 Arria 10 GX PCIe Gen3x8 hardware bridge with three consecutive deterministic
physical passes. Portable tests do not embed local cables/BDFs or replace native
gates. Missing tools/hardware are incomplete gates, not waivers. The runtime
authors/reviews/renders the product PDF only after engineering acceptance.
