# RIVET-H5 admitted implementation contract

## Scope and ownership

Top: `rivet_h5_top`, targeting Intel Arria 10 GX `10AX115N2F45E1SG`,
100 MHz or faster (clock period at most 10.0 ns). Preserve H1--H4 SHA-256,
HMAC-SHA-256, SHA-512, SHA3/SHAKE, context and authenticated Merkle replay
services; add canonical NTT/INTT, SHAKE polynomial sampling and pure contextual
FIPS 204 ML-DSA verification for ML-DSA-44, -65 and -87.

Designer owns `rtl/*.sv` and `design/*.md`. Independent Verifier owns `tests/*`,
numerical and cryptographic oracles, drivers, fixtures, mutations and all
functional/synthesis execution. Engineering acceptance and the independently
approved product PDF are subsequent shared-runtime responsibilities.
No implementation or historical parent result certifies the changed product.

## Cycle and degenerate-boundary table

All new stateful control uses `posedge clk` and asynchronous active-low `rst_n`.
RAM accesses use clock-only processes, with transaction-valid enables.

| Event/boundary | Required behavior |
|---|---|
| Accepted input at E0 | Pre-edge `valid && ready` decides acceptance; state and counters change post-edge. |
| Command followed by data | Receive readiness changes post-E0; no first data beat on E0. |
| New registered output | Cannot retire on the edge that first makes it valid. |
| Active reset | Immediately suppress all new ready/valid/status/authentication outputs and zero exposed payloads. |
| First edge after reset release | Idle readiness may be advertised; no uninitialized RAM may be consumed. |
| Output stall | Valid payload, index, last and status remain stable until retirement. |
| Output retirement | Valid clears post-edge; command acceptance still depends on pre-edge ready. |
| Cancel versus input/output | Cancel wins, flushes that service, emits no completion, leaves other services unchanged. |
| Key provision versus cancellation | Cancellation wins; only completed valid provisioning atomically locks the key. |
| RAM read/write | FSM separates reads from dependent writes; no reliance on read-during-write semantics. |
| `MAX_PAGE_BYTES=1` | Single-byte first/last page; minimum address width one; no nonexistent storage index. |
| Non-power-of-two page sizes | Explicit byte-count bounds and last detection, not power-of-two wrap masks. |
| Empty context/message | One transfer with keep=0000 and last=1. |
| Empty XOF input | One byte-interface transfer with keep=0 and last=1. |
| NTT singleton impulses | Fixed 256 coefficients, including impulses at indices 0, 1, 127 and 255. |

## Inherited compatibility

The immutable baseline is the 15 files in `rivet_h4_reference/rtl/`, indexed
by `design/GENERATIONAL_HANDOFF.md`. Copy these into `rtl/` without implementation
changes. Instantiate `rivet_h4_top` as `rivet_h5_top.u_parent`, propagating every
parent port unchanged and both parameters. `PARTIAL_BEATS` defaults to 0,
legal values 0 and 1. `MAX_PAGE_BYTES` defaults to 4096, legal values 1..4096.
Illegal values must explicitly reject with `PARAMETER ERROR`.

Preserve all four independently interleaved channels, output/context arbitration
and backpressure, H2/H3 context encodings and validation, key reuse, cancellation,
and algorithm-switch semantics. Parent cmd_op is 0 SHA_INIT, 1 KEY_LOAD,
2 HMAC_INIT, 3 SAVE, 4 RESTORE, 5 CANCEL, 6 SHA512_INIT, 7 invalid; m_alg is
0 SHA-256, 1 HMAC-SHA-256, 2 SHA-512. Sponge x_alg is 0 SHA3-256,
1 SHA3-512, 2 SHAKE128, 3 SHAKE256; x_cmd_op is 0 start, 1 cancel.
Merkle leaves hash SHA256(0x00 || page), nodes hash
SHA256(0x01 || left || right); leaf direction bits are consumed least-significant
first. Preserve root locking, proof validation, tamper reporting and replay
backpressure. Unauthenticated page bytes are never released.

## Arithmetic and transform

N=256, q=8380417, d=13, primitive 512th root psi=1753.
Public 23-bit coefficients are canonical unsigned values 0..q-1; signed values
use their representatives modulo q. Reject noncanonical raw NTT input.
R=2^32, R mod q=4193792, R^2 mod q=2365951,
-q^-1 mod R=4236238847. Montgomery multiplication is:
T=a*b; m=(T*4236238847) low 32 bits; u=(T+m*q) shifted right 32;
subtract q once if u>=q. Mont(a,b)=a*b*R^-1 modulo q.
An ordinary product uses Mont(Mont(a,b),2365951).
No synthesizable division or modulo operators are permitted.

Forward stage lengths are 128,64,...,1, with group twiddle indices starting
at 1. zeta[k]=R*psi^BitRev8(k) modulo q. Public forward output:
y[i]=sum_j a[j]*psi^((2*BitRev8(i)+1)*j) modulo q.
Inverse lengths are 1,2,...,128 using negated twiddles in reverse group order.
Normalize by Mont(value,16382), giving INTT(NTT(a))=a, not R*a.
41978 belongs to invntt_tomont and is not the public normalization.
Polynomial multiplication is negacyclic modulo X^256+1.

Montgomery ports: clk/rst_n; a_valid/a_ready; a,b[22:0];
m_valid/m_ready; m[22:0]. One outstanding operation, unstalled latency
exactly 11 intervals. E0 captures operands; E1 computes <=16x16 T partial
products; E2 aligned pair sums; E3 T assembly; E4 reduction-multiplier
partial products; E5 cross-term sum; E6 low-word m assembly; E7 m*q
partial products; E8 pair sums; E9 m*q assembly; E10 carry-preserving
T+m*q; E11 upper-word normalization/output.

Butterfly ports: clk/rst_n; b_valid/b_ready; b_inverse;
b_u,b_v,b_zeta[22:0]; b_m_valid/b_m_ready; b_a,b_b[22:0].
One outstanding operation, exactly 13 unstalled intervals.
E0 captures; E1 dispatches Montgomery operands and registers parallel sum;
Montgomery output post-E12; butterfly output post-E13.
Forward returns u+Mont(v,zeta), u-Mont(v,zeta).
Inverse returns u+v, Mont(u-v,zeta). All results canonical.
Inverse caller supplies the already-negated Montgomery twiddle.

NTT ports: n_cancel; n_cmd_valid/n_cmd_ready; n_inverse;
n_s_valid/n_s_ready; n_s_coeff[22:0]; n_s_last;
n_m_valid/n_m_ready; n_m_coeff[22:0]; n_m_index[7:0]; n_m_last;
n_done_valid/n_done_ready; n_error[1:0], plus clk/rst_n.
Command then exactly 256 natural-index inputs, last only at 255.
Buffer and validate all input before producing any output. Exactly 256 outputs,
index 0..255, last at 255, then one held completion. Error 0 success,
1 framing, 2 noncanonical; invalid input produces no polynomial output.
Cancellation produces no completion. Completion after all required input,
without external stalls, must take at most 65536 clocks.

## XOF and sampling

`rivet_h5_xof` ports: clk/rst_n; clear; cmd_valid/cmd_ready; alg
(0 SHAKE128, 1 SHAKE256); s_valid/s_ready; s_data[7:0]; s_keep; s_last;
m_valid/m_ready; m_data[7:0]. Rates are 168/136 bytes. Padding uses 0x1f
and the final 0x80 bit. Keep=0 is legal only as last on empty input.
Supply a continuing stream across arbitrary rate boundaries until clear;
no finite guessed rejection budget.

Sampler ports: sam_cancel; sam_cmd_valid/sam_cmd_ready;
sam_op[2:0]; sam_level[1:0]; sam_seed[511:0]; sam_nonce[15:0];
sam_m_valid/sam_m_ready; sam_m_coeff[22:0]; sam_m_index[7:0];
sam_m_last; sam_done_valid/sam_done_ready; sam_error[1:0], plus clk/rst_n.
Levels 0/1/2 select ML-DSA-44/65/87; 3 is invalid. Seed byte zero
is bits 7:0. Op 5..7 is invalid. All successful modes emit exactly
256 natural-index canonical coefficients then a held completion;
error 0 success, 1 invalid descriptor; cancel flushes without completion.
Without external stalls completion is within 65536 clocks.

| op | Definition |
|---|---|
| 0 | ExpandA: SHAKE128(first 32 seed bytes || nonce_LE16); A[row][col] uses nonce=(row<<8)|col. |
| 1 | Uniform SHAKE256: all 64 seed bytes || nonce_LE16. |
| 2 | ExpandS: SHAKE256(64 seed bytes || nonce_LE16), low nibble first; eta=2 accepts t<15 and returns 2-(t mod 5); eta=4 accepts t<9 and returns 4-t. |
| 3 | ExpandMask: SHAKE256(64 seed bytes || nonce_LE16), contiguous little-endian 18/20-bit fields, gamma1-field modulo q. |
| 4 | SampleInBall: SHAKE256(c_tilde), no nonce, 32/48/64 seed bytes; first eight bytes are little-endian signs; exact FIPS bounded-index rejection/swap for tau nonzeros. |

Ops 0/1 consume three little-endian bytes, mask bit 23, reject >=q,
retain <q, and continue squeezing until 256 accepted values.
Eta maps contain no RTL division/modulo.

## Signature verification

Pure ML-DSA over actual manifest bytes and FIPS context domain separation.
No prehash/signing interface or externally provided mu, matrix, challenge
polynomial, transformed z, decoded hints, w1 or expected answer.

| level | k | l | eta | tau | beta | gamma1 | gamma2 | omega | c bytes | pk bytes | sig bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 4 | 4 | 2 | 39 | 78 | 131072 | 95232 | 80 | 32 | 1312 | 2420 |
| 1 | 6 | 5 | 4 | 49 | 196 | 524288 | 261888 | 55 | 48 | 1952 | 3309 |
| 2 | 8 | 7 | 2 | 60 | 120 | 524288 | 261888 | 75 | 64 | 2592 | 4627 |

Ports: pq_cmd_valid/pq_cmd_ready; pq_cmd_op[1:0]; pq_level[1:0];
pq_ctx_bytes[7:0]; pq_message_bytes[31:0]; pq_s_valid/pq_s_ready;
pq_s_kind[1:0]; pq_s_data[31:0]; pq_s_keep[3:0]; pq_s_last;
pq_result_valid/pq_result_ready; pq_auth_ok; pq_status[3:0];
pq_key_locked; clk/rst_n. Op 0 provisions, 1 verifies, 2 cancels,
3 invalid. Kind 0 pk, 1 signature, 2 context, 3 message.
Bytes are MSB first. Keep 1111/1110/1100/1000 denotes 4/3/2/1
consecutive MSB bytes; nonfinal beats require 1111.
Zero-length context/message requires keep=0000,last=1. Reject wrong kind,
invalid keep, overflow and early/late last at exact section lengths.

Provision exactly one trusted pk section, atomically pin until reset, return
status 0/auth=0. Reject overwrites without changing the key. Verification
requires matching pinned level and sections signature, context, message in
that order. Context length 0..255; message length 0..2^32-1, hashed while
streaming without whole-message storage. Cancel remains ready while active
or holding a result, discards work/result, preserves key and emits no result.
Other commands require idle/no result. Each noncancel command emits one
held result; exposed result fields are zero outside valid.

Decode pk=(rho,t1), signature=(c_tilde,z,h), with little-endian packed fields,
gamma1-offset z, strictly increasing per-polynomial hint indices,
nondecreasing cumulative endpoints, total <=omega and zero unused hint bytes.
Reject ||z|| infinity >=gamma1-beta.
Compute tr=SHAKE256(pk,64);
mu=SHAKE256(tr || 0x00 || len(ctx) || ctx || message,64).
Compute c=SampleInBall(c_tilde), ExpandA in standard NTT representation,
NTT(z), NTT(c), NTT(t1*8192), then each row
A_hat*z_hat-c_hat*NTT(t1*8192), using documented normal/Montgomery scale.
INTT and canonical reduction precede UseHint and w1 packing.
Hash c_check=SHAKE256(mu || w1Encode(w1),c_bytes) and compare every byte.
w1 uses contiguous little-endian 6-bit fields for level 0, 4-bit otherwise,
in row/index order. Serialize rows, do not retain the expanded matrix.

Decompose: alpha=2*gamma2; choose a0 from a mod alpha, subtracting alpha
if remainder>gamma2. If a-a0=q-1, a1=0 and decrement a0; otherwise
a1=(a-a0)/alpha. These mathematical definitions do not authorize RTL
division/modulo. UseHint(a,0)=a1; hint 1 increments with wrap if a0>0,
otherwise decrements with wrap. High ranges 0..43/0..15; handle q-1 and
both decomposition boundaries exactly.

Status: 0 success; 1 invalid command/level or missing/mismatched key;
2 framing/length; 3 malformed signature; 4 z norm; 5 challenge mismatch;
6 key overwrite. Auth=1 only for successful VERIFY. There is no manifest
release bypass or software-only authentication. Progress after all input,
without stalls, must be within 16000000 clocks.

## Hierarchy, timing and storage

Top has substantive u_parent, u_ntt, u_sampler, u_verify. Each NTT has
u_butterfly with u_montgomery. Sampler has u_xof with inherited u_keccak.
Verifier has its own u_ntt, u_sampler, u_hash. New transactions never
commandeer parent channel or sponge engines.
Use pipelined <=16x16 multiplier partial products and registered
accumulation/reduction. No mixed blocking/nonblocking sequential state,
latches, combinational division/modulo, asynchronous large-memory resets
or combinational large-memory reads. Byte-write memories >=2 KB use
explicit unpacked byte lanes for Quartus M20K inference. RAM validity and
ownership prevent stale/uninitialized reads. Actual timing requires native
post-fit STA; no waiver is admitted.

## Independent acceptance and reproduction

From the delivered root, with existing Python 3, Icarus/vvp, Verilator,
make, g++ and Yosys, execute:

```
python3 tests/verify.py --suite behavior
python3 tests/verify.py --suite defects
python3 tests/verify.py --suite synthesis
python3 tests/verify.py --suite portable
```

Default `python3 tests/verify.py` runs all L1 suites. Verifier supplies these
self-contained commands; no prior receipt/cache, network, private state or
future PDF may be required. No package installation is authorized.
Use fresh exclusive `evidence/<suite>-<UTC_timestamp>-<hash_or_nonce>/`
directories, with exact commands, sources, versions, times, exit/timeout,
settled children, raw logs, comparison counts, observed coverage and failures.
Preserve failures and repairs. Descendant per-run directories have hash/time
suffixes. Retain complete synthesis netlists, optionally losslessly compressed
with verified decompressed hashes and sizes.

Independent expectations use Python arbitrary-precision arithmetic, direct
root-evaluation transforms, schoolbook negacyclic products and hashlib/HMAC.
Signature oracle must first cross-check public independently sourced FIPS
204 KATs for all three levels with shipped provenance.
Compiled behavioral seeds are 17,29,43. Per seed: >=4096 Montgomery random
pairs plus cross-product of {0,1,2,4190208,4190209,q-3,q-2,q-1};
>=1024 random butterflies per direction plus boundaries; >=16 random
and eight directed polynomials for both transform directions, all coefficients
and both round trips; >=8 negacyclic products. Assert canonical outputs
and exact 11/13-cycle leaf latencies.
Per seed/level: >=4 seeds/nonces per sampler op, off-diagonal ExpandA,
observed rejection/continuation, nibble/sign/swap and candidate boundaries.
XOF tests empty, rate-1/rate/rate+1/multiple-rate input and at least three
output blocks. Per seed/level: >=4 valid distinct-message/context signatures,
empty sections, 255-byte context and multiblock manifests; oracle-confirmed
message/context/challenge/z/hint forgeries and wrong pinned keys. Cover exact
norm boundaries, omega/omega+1, malformed hint ordering/endpoints/unused
bytes, framing/masks/descriptors, overwrite, cancel/recovery, nonzero hints,
both UseHint wraps and all reconstructed challenge bytes via test-only
instrumentation absent from production ports.

Legacy independent hashes plus immutable-parent side-by-side comparisons:
all four concurrent channels; lengths 0,1,3,4,55,56,63,64,65,111,112,127,
128,129,257,4096 as applicable; HMAC keys 0,1,63,64,65,128; key reuse,
switch/cancel, malformed and both context formats, arbitration/stalls;
all sponge padding/rate/output boundaries. Merkle valid/tampered pages/proofs,
locked roots, depths 0,1,2,31,32, index legality, stalls/no unauthenticated
replay. Elaborate all 8192 legal parameter pairs; functional page sizes
1,3,4,5,4095,4096 in both partial modes and all four illegal parameters.
All new interfaces require gaps, multicycle stalls, reset/cancel in every
phase, restart and concurrent legacy activity. Reject active X/Z.

Real Icarus checks are compact <=500000 clocks, normally <60 seconds;
compiled Verilator runs complete signatures, matrices/concurrency/mutations.
Execute disposable defects in Montgomery, NTT, sampler, norm, UseHint and
challenge comparison plus a legacy digest/authentication defect; compilation
failure is not sensitivity. Original RTL remains unchanged.
Genuine Yosys coarse full-top synthesis in both partial modes and page sizes
1,3,4096, all new leaves and mapped arithmetic leaves must retain complete
netlists and show zero latches/div/mod, substantive hierarchy/state/memory,
no unresolved modules or multiple drivers. Portable suite copies only declared
sources/fixtures into a clean directory excluding runtime metadata and evidence,
then freshly runs compact behavior and leaf synthesis.

Native L1.5 timing lint, L2 Quartus 17.1 post-fit <=10.0 ns with setup WNS>=0
and no unresolved timing violations, and L3 three consecutive deterministic
Arria 10 PCIe Gen3x8 functional hardware passes remain mandatory. L1 must not
invent hardware receipts or hardcode JTAG cables/PCIe BDFs. Reviewer approval
precedes runtime production/review/rendering of the product PDF.
