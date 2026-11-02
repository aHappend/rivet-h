# RIVET-H4 implementation and integration

## Entry, target and source ownership

Compile every `rtl/*.sv` with top `rivet_h4_top`. Defaults are
`PARTIAL_BEATS=0, MAX_PAGE_BYTES=4096`; legal values are respectively {0,1}
and every integer 1..4096. Invalid values invoke parameter diagnostics.
The FPGA target is Intel Arria 10 GX `10AX115N2F45E1SG` with a clock
period at most 10.0 ns. Pipelining is a design intention, not a measured STA result.
`SPEC.md` freezes ports, ordering, numerical rules, boundary behavior and the
independently admitted acceptance matrix.

Designer-owned inputs: `rtl/*.sv`, `design/*.md`.
Verifier-owned inputs: flat `tests/*`; immutable comparison fixtures:
`rivet_h3_reference/rtl/*.sv`. No runtime directories are compilation inputs.
No initial generational handoff or linked source index was available.
`GENERATIONAL_HANDOFF.md` is now restored through authorized project input
restoration. Its supplied Quartus 17.1 results are post-map setup WNS +4.922 ns
at 10.0 ns and hold WNS -0.175 ns, not post-fit signoff or clean hold timing.
The historical `passed` label does not resolve the negative hold slack.
Parent post-fit timing, Fmax, area and physical HIL remain unavailable; no
measured parent/H4 timing or PPA improvement is claimed. Reference RTL and the
historical handoff are provenance, not evidence that H4 passes.

## Hierarchy and isolation

```
rivet_h4_top
  u_legacy : rivet_h3_top
    g_channel[0..3].u_channel : rivet_h3_channel
      u_h2 : rivet_h2_top
        u_stream, u_hmac, u_context, u_compress.u_schedule
      u_sha512 : rivet_h3_sha512
        u_compress.u_schedule
  u_sponge : rivet_h4_sponge
    u_keccak : rivet_h4_keccak
  u_merkle : rivet_h4_merkle
    u_hash : rivet_h2_top (PARTIAL_BEATS=1)
      u_stream, u_hmac, u_context, u_compress.u_schedule
```

Four legacy channels retain independent H2 and SHA512 engines, the original
command/key/context rules, RHV2/RHV3 serialization and registered locked
round-robin response arbitration. The delivered parent-derived copies differ
only in SHA compression/schedule arithmetic partitioning. Reference inputs remain
unchanged. No new algorithm tags or context fields are inserted into legacy ABI.

Sponge has independent data/control/output ports and no legacy context extension.
Merkle owns a fifth, dedicated H2 engine: there is no shared scheduler, lock or
consumer dependency linking authentication to the four legacy channels or sponge.
External backpressure can stall each branch but cannot consume another branch's
compute resource. Cancellation on legacy/sponge cannot modify the pinned root.

## Registered arithmetic and cycle tables

SHA round state is held for five edges. Schedule recurrence registers two
independent pair sums, then their sum. It settles before phase 2 samples the
schedule word; shift/update occurs only at phase 4 for expanded rounds.
Words 0..15 remain direct selections of the originally loaded block.

| SHA round edge | Registered operation |
| --- | --- |
| 5r+1 | Big sigmas, choose, majority, round constant |
| 5r+2 | h+sigma1; choose+constant; sigma0+majority |
| 5r+3 | Sum of first two pairs; capture settled schedule word |
| 5r+4 | Add captured schedule word to form T1 |
| 5r+5 | a=T1+T2, e=d+T1; rotate state and step schedule |
| After final round | Eight parallel feed-forward additions; pulse done |

Relative to accepted compressor launch E0, SHA256 completes at E321 and
SHA512 at E401, excluding parent block assembly, padding and wrapper observation.
Every arithmetic pipeline stage contains at most one carry-propagating addition
on its data path; choose/sigma logic is separated from the following additions.
The unchanged parent wrappers wait for done rather than relying on old latency.

Keccak uses packed lane order `64*(x+5*y)+:64`. Rotation and pi destinations are
constant generate wiring; wrapping is explicit constant subtraction, not
remainder hardware. Theta parities are five XORs per column, followed by
registered theta/rho/pi, registered chi and registered iota.

| Keccak edge from E0 launch | Registered operation |
| --- | --- |
| E0 | Capture state; busy=1 |
| E(4r+1) | Five column parities |
| E(4r+2) | Theta, fixed rho rotation and pi wiring |
| E(4r+3) | Chi |
| E(4r+4) | Iota, next round |
| E96 | Final iota/state_out; busy=0, done=1 |
| E97 | done=0; state_out holds |

Clear dominates launch and execution. Busy start pulses are ignored.
No combinational round cascade or algorithm-dependent permutation latency exists.

## Sponge dataflow and storage

| Mode | Rate bytes | Capacity bits | Suffix |
| --- | --- | --- | --- |
| SHA3-256 | 136 | 512 | 06 |
| SHA3-512 | 72 | 1024 | 06 |
| SHAKE128 | 168 | 256 | 1f |
| SHAKE256 | 136 | 512 | 1f |

START latches rate, suffix and requested output length and clears the 1600-bit
sponge state, 64-bit byte count and fixed beat registers. SHA3 requires exactly
32/64 bytes; SHAKE accepts 1..4294967295. Idle does not absorb without START.
Accepted input beats are checked for contiguous keeps/final legality and a
65-bit proposed count detects overflow before truncation.

Each byte uses PICK to register a selected 64-bit lane and ABSORB to XOR the
selected byte and write that lane. This separates the lane mux from byte
selection/XOR/write. A beat takes one capture edge and two edges per byte absent
rate-boundary work. A partially drained beat is retained over a rate permutation.
The first external byte (bits 31:24) enters lane-zero bits 7:0.

At final input, suffix read/write and final-rate-byte read/write are four
distinct edges. Their separation naturally combines 06/1f with 80 at a shared
last byte. An exact-full input rate first permutes, then pads a fresh rate block.
LAUNCH starts Keccak on the following edge. The wrapper samples done one edge
after E96 and latches its result; these wrapper edges do not change the fixed
core latency.

Squeeze likewise uses a lane-read edge and byte-formation edge, accumulating at
most four output bytes into a zero-initialized 32-bit word. Requested remaining
bytes is a 32-bit counter. A formed beat is held in OUT_SEND until handshake.
Only after that handshake can another beat or squeeze permutation begin.
All rates are multiples of four, so an ordinary full-rate squeeze boundary is
also a full-beat boundary. Additional blocks permute unchanged state; no padding
is reintroduced. SHAKE storage is constant regardless of requested output size.

CANCEL is ready in every nonreset state, has sequential priority over all
transfers, clears pending output and fault, and clears Keccak. Illegal START
or malformed accepted input enters FAULT, with data/output readiness/valid
suppressed until CANCEL/reset. The existing PARTIAL_BEATS=1 final-zero behavior
does not imply an absent final beat is a timeout.

## Merkle dataflow, memory and trust

The root is a reset-lifetime register with a one-way lock. Provision root through
`root_valid/root_ready`, then start no earlier than a later edge with root_locked
asserted. Root writes while locked are not accepted. The trusted boundary includes
provisioning and reset control; the RTL does not establish trust in a malicious
root, prevent hostile reset or provide side-channel/key-secrecy guarantees.

Start latches page length, depth and index. Legal depth is 0..32, with zero
high index bits above depth when depth<32. The descriptor validates before any
page/proof acceptance. LEAF_INIT issues SHA256_INIT to the private H2 engine;
LEAF_PREFIX sends one byte 00, then PAGE forwards only correctly framed accepted
page beats and simultaneously stores them. Its forced partial-beat mode permits
the one-byte nonfinal prefix without relaxing public page framing.

RAM is `ceil(MAX_PAGE_BYTES/4)` words of 32 bits (1024 words/4096 bytes by default),
with explicit synchronous write and registered read ports in a clock-only block,
no array reset and an M20K inference hint. Address width is at least one, including
capacities 1 and 3. Invalid configurations use diagnostic-only safe dimensions;
they still fail explicitly and are not usable clamped configurations.
Bounds use descriptor count, not address masking. Partial final words may store
untrusted low bits internally; replay explicitly zeros all unused output bytes.
The supplied parent handoff recommends byte-lane arrays for large byte-enable
memories. This page RAM instead writes complete 32-bit words; it has no byte-enable
write ports. Its M20K hint is not proof of hard-memory mapping, and the handoff's
<45-second inference expectation is not an H4 acceptance threshold. Actual
native Quartus mapping remains mandatory.

After leaf digest acceptance, depth zero proceeds directly to comparison.
Otherwise PROOF accepts a sibling only after page hashing is complete.
Index bit zero concatenates `{current,sibling}`, bit one `{sibling,current}`;
the index shifts right once per accepted well-framed sibling. A 512-bit pair
register feeds 16 full words after the one-byte 01 prefix. Exactly depth siblings
are accepted; proof_last must match the final level. The H2 engine retires each
digest before the next SHA256_INIT.

Eight 32-bit equality registers compare the computed digest to the pinned root,
followed by a separate reduction/verdict edge V. Successful authentication sets
release eligibility and begins synchronous RAM read, beat formation and SEND;
the first tile transfer is strictly later than V. Reads are disabled before
eligibility. Failed metadata/framing or root comparison never enables replay.
Malformed streams abort via an actual private-hash CANCEL, discarding partial
hash state rather than leaving it eligible for another descriptor.

| Merkle state/event | Ownership/transition |
| --- | --- |
| IDLE + accepted descriptor | Clear all old read eligibility and status |
| PAGE + legal beat | Private hash and quarantine RAM accept the same beat |
| PAGE/proof framing failure | Latch failed result, stop readiness, cancel private hash |
| WAIT_LEAF/WAIT_NODE | Accept only registered hash digest, then proof/compare |
| COMPARE_WORDS | Register eight equality bits |
| COMPARE_DECIDE V | Register result and mutually exclusive auth/tamper status |
| REPLAY_READ | Synchronous authenticated RAM read |
| REPLAY_FORM | Register masked data/keep/last from RAM read result |
| REPLAY_SEND stalled | Hold exact beat; no further reads or address changes |
| Last tile handshake | Clear eligibility and enter RETIRE |
| RETIRE | Wait for independently consumed result before returning IDLE |

Result valid holds until consumed; status remains until next accepted start/reset.
Tile replay need not wait for result ready. Result consumption does not permit
start while replay is outstanding, and completed replay does not discard an
unconsumed result. Reset immediately suppresses outputs, clears eligibility and
lock, but intentionally does not erase RAM: stale contents remain ineligible.
No internal timeout converts an ordinary input stall into a failure.

## Integration and reproduction

Drive reset low, release it, then use pre-edge valid/ready sampling. Initialize
legacy channels with their existing commands; independently START the sponge
before its data. Provision the root before Merkle START, send the complete page,
then siblings leaf-to-root. Hold every producer payload until accepted. Consumers
may stall independently. On Merkle failure consume the failed result and begin
a fresh descriptor; on sponge fault CANCEL or reset.

A fast static syntax/elaboration command is:

```
iverilog -g2012 -t null -s rivet_h4_top rtl/*.sv
```

The independent Verifier supplies and executes the public L1 entrypoint:

```
python3 tests/verify.py --suite all --output-root evidence/l1
```

Run from the delivered project root. Requirements are Python 3, Icarus/vvp,
compiled Verilator and Yosys; the actually observed static elaborator here is
Icarus Verilog 12.0. No other dependency version or result is inferred.
The admitted command must generate fresh source-bound output, preserve failed
receipts, run the complete independent model/protocol/defect/synthesis matrix
and reproduce compact legacy/sponge/Merkle checks in a clean temporary copy.
It must not require original build products, private paths or runtime transcripts.

Designer runs no behavior/synthesis harness. Static parse success is not a
cryptographic, protocol, memory-inference or timing verdict. Existing independent
Icarus/Verilator preparation comparisons, six intended mutant rejections and two
zero-latch Yosys configurations are advisory only; complete L1 and clean-copy
reproduction remain pending against fresh, stable source bindings.
The Coordinator reports current-source native timing lint passed; no actual-H4
Quartus STA or board-HIL receipt is available at this handoff. Native runtime gates
are L1.5 timing lint, L2 Quartus 17.1 STA and L3 Arria 10 GX PCIe Gen3x8 hardware
bridge, including three deterministic consecutive board passes. STA, memory
mapping and physical-board acceptance remain pending until actually executed;
portable L1 neither hardcodes hardware locations
nor substitutes generic synthesis for STA/HIL. Product PDF generation/review
follows engineering acceptance and is not an input prerequisite.
