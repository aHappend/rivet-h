# RIVET-H3 architecture and integration

## Hierarchy and ownership

```
rivet_h3_top
  g_channel[0:3].u_channel : rivet_h3_channel
    u_h2 : rivet_h2_top
      u_stream : rivet_h2_stream
      u_hmac : rivet_h2_hmac
      u_context : rivet_h2_context
      u_compress : rivet_h2_compress
        u_schedule : rivet_h2_schedule
    u_sha512 : rivet_h3_sha512
      u_compress : rivet_h3_sha512_compress
        u_schedule : rivet_h3_sha512_schedule
```

Each channel replicates both compression paths. Only its selected algorithm
can accept stream data or expose a response. There is no compression
scheduler, interchannel state exchange or shared message memory. The sole
shared bottlenecks are the tagged 32-bit message/key input ports and the
single digest/context output ports. Replication trades generic resource
usage for isolation; improved aggregate throughput is not assumed.

The six copied H2 modules are unmodified, including their original local
hierarchy and standalone API. H3 command decoding, context envelopes,
response-preserving cancellation and arbitration are outside those modules.
No hierarchical references, benchmark ports or simulation-only arithmetic
are used by the new datapaths.

## Storage and dependency contracts

| Resource | Producer / consumer | Capacity and release |
| --- | --- | --- |
| Per-algorithm beat stage | Selected message/key input / byte drain | One 32-bit beat; no same-edge replacement when last byte drains. |
| H2 block | Byte drain / H2 compressor | 64 bytes; release after registered data-block completion. |
| SHA-512 block | Byte drain / SHA-512 compressor | 128 bytes; a crossing staged beat pauses until release. |
| Compression schedule | Block launch / iterative round unit | Sixteen words, 32 or 64 bits; sliding expansion after round 15. |
| SHA-512 chain/count | Compression completion and capture / padding/context | 512-bit chain and full 128-bit byte count. |
| HMAC key cache | Parent key normalization / parent message controller | Inner/outer SHA-256 seeds, never shared between channels. |
| Channel digest | Final compression / output arbiter | One response, held until its selected handshake. |
| Channel context | SAVE / context arbiter | One frozen response; hashing resumes only after handshake. |
| Output grants | Round-robin search / consumer | One locked grant per independent port. |

Input capture depends on a free stage, collection state and buffer space.
The compressor depends on a complete prepared block and registered chaining
state. A saved context depends on no staged bytes, incomplete block
compression, finalization or key loading. Each arbiter depends only on
registered pending responses; channel controllers never depend on which
other channel is granted. This prevents a stalled consumer from preventing
other channels from reaching their own response storage.

## Channel control and key lifetime

The wrapper records the selected algorithm, a sticky local protocol fault,
whether the H2 message prefix is nonempty, and an inactive-H2 cleanup bit.
Native H2/SHA-512 errors are combined only from the active algorithm.
Accepted commands suppress both same-channel streams. Parent command
readiness provides the H2 quiescent boundary without reaching into parent
state or changing its ports.

When switching from H2 to SHA-512, the wrapper probes parent SAVE readiness
but does not issue SAVE. It initializes/restores SHA-512 and schedules a
parent CANCEL on the next edge, clearing cached keys and inactive state.
Non-CANCEL commands are backpressured for that single cleanup edge;
SHA-512 input can already stage a beat on it. The inactive H2 engine cannot
receive user data or emit a public response. Subsequent commands cannot
observe the old key. Leaving SHA-512 forwards the requested fresh H2 command
or validated parent restore after cleanup. A new HMAC_INIT without a new
or restored valid key therefore faults. Same-domain parent key retention
and automatic same-mode message restart are preserved.

CANCEL clears both engines and wrapper state but is not ready while the
channel owns any pending response, including one not yet globally granted.
Thus neither CANCEL nor an unselected channel can invalidate a locked grant.
Only asynchronous reset may withdraw an exposed response under stall.

## SHA-512 datapath

`rivet_h3_sha512` handles collection, full-block preparation, padding,
compressor launch/wait, digest retirement, context snapshots and faults.
Byte count increments at accepted capture, not byte drain. The stage
retains its final flag until the last byte (or zero-byte terminator) drains.
An exactly full final block is compressed as data before a fresh pad block.

The sixteen-word schedule preserves the initial words during rounds 0..15.
For rounds 16..79 it computes the next expanded word from positions
0,1,9,14 and shifts once per round. All intermediates are unsigned
64-bit values with modular addition. The compressor loads eight working
words on launch, performs one round per edge, and feeds forward in a
separate edge. It emits a registered one-cycle done pulse.

Padding uses the retained 128-bit count shifted left by three, with no
64-bit truncation. Residual lengths 0..111 finish in one pad block;
112..127 use two. A prospective 129-bit count calculation rejects overflow
above 2^125-1 before stage capture. Context validation checks this same
limit, used/count congruence, zero tail/reserved fields and initial chain.

## Context boundary

The wrapper validates the envelope before enabling either restore path.
The unchanged parent validates all H2 payload fields before installing them;
SHA-512 validates its own payload. A malformed command faults without
partially installing state or allowing a message result. Legacy zero-extended
H2 snapshots are imported; every new SAVE emits the H3 envelope.
Snapshots exclude the channel tag and may migrate between channels.
Restoring a SHA-512 snapshot also clears inactive SHA/HMAC key state.
See `design/SPEC.md` for the exact bit layout.

## Arbitration and timing

Digest and context arbiters independently scan four pending bits in cyclic
order from their next-search pointers. Selection is registered, not a
combinational ready/valid bypass. The selected channel already owns stable
payload storage, so grants need not duplicate 512/2304-bit response registers.
Pointer advancement occurs only at retirement, not selection. No selection
occurs on the retirement edge: ready consumers therefore see an intentional
one-cycle selection bubble between responses.

`design/SPEC.md` defines the pre-edge/post-edge cycle table. In particular,
compression latency is not message latency. Byte staging, block preparation,
registered completion consumption and arbitration all contribute to the
measured result. There is no stated physical frequency or latency in seconds.

## Integration and source-only reproduction

Compile all `rtl/*.sv`, selecting `rivet_h3_top`; select `rivet_h2_top` for
the standalone compatibility interface. Drive reset low before sending any
valid transfer, release it, then obey each ready/valid handshake. Reset
selects empty SHA-256. Use SHA512_INIT for SHA-512, or KEY_LOAD, key stream
completion, then HMAC_INIT for HMAC. A valid non-CANCEL command held during
key loading backpressures until key setup completes. Keep data, masks,
last and tags stable while valid is stalled. Maintain independent software
transaction order per channel rather than assuming global completion order.

A fast static elaboration command, which does not execute behavior, is:

```
iverilog -g2012 -t null -s rivet_h3_top -s rivet_h2_top rtl/*.sv
```

Functional and synthesis reproduction commands are in `design/SPEC.md`.
Required executables are Python 3, `iverilog`, `vvp` and `yosys`.
Actual versions, source hashes, argv, working directory, seeds, configurations,
timestamps, exit/timeout status, raw logs and metrics must be retained by the
independent verification entry point in its fresh project-relative outputs.
No tool version is certified merely by this integration description.
No installation, private account directory or runtime metadata is a
reproduction dependency.

Source inputs are `rtl/*.sv`, `design/SPEC.md`, `design/ARCHITECTURE.md`,
Verifier-owned `tests/*.py` and `rivet_h2_reference/rtl/*.sv` for compatibility.
Evidence directories, generated testbenches/netlists/executables and the
post-acceptance PDF are outputs, not source inputs. Portable reproduction
copies only the declared sources, not existing generated evidence.

## Claim-to-result map and limitations

| Claim | Independent result location / required observation |
| --- | --- |
| Cryptographic exactness | `evidence/behavior/`: hashlib/hmac, published vectors, context/limit checks; zero digest mismatches. |
| Parent compatibility | `evidence/compatibility/`: parent byte equality and standalone H2 behavior in both legal settings. |
| Oracle sensitivity | `evidence/defects/`: four compiling disposable functional mutants, each rejected by a specific oracle/assertion. |
| Generic synthesizability | `evidence/synthesis/`: both settings, real state/output logic, connected hierarchy, no latches/unresolved modules/conflicting drivers/loops. |
| Portable reproduction | `evidence/portable/`: source-only copy exercising the shipped entry point without private state. |
| Cycle performance | `evidence/behavior/`: actual handshake timestamps and explicitly defined intervals, not arithmetic-unit latency estimates. |
| Source/resource size | `evidence/synthesis/`: source bytes/lines/modules, elaborated instances and Yosys generic cell/state/memory counts. |

These paths identify required results, not a claim of existing passing evidence.
For benchmarks use identical deterministic single-active-channel and
four-active-channel workloads: 16 messages per active channel per algorithm
at lengths 0,112,128,1024; additionally a mixed four-channel 64-message batch
containing all three algorithms. Report first-beat to digest-valid and
retirement, last-beat to digest-valid, separate key setup/reset costs,
total elapsed cycles, messages/payload bytes, cycles/message, cycles/byte
and aggregate payload bytes/cycle. Label steady-state endpoints and channel
distribution, exclude reset/key setup from the labeled steady-state interval,
and report measured ratios even if replication is slower. Zero-byte workloads
must not produce a misleading finite cycles/byte result by dividing by zero.

No physical area, timing closure, silicon security certification, FPGA
measurement, authentication of contexts or side-channel resistance is claimed.
Independent Verifier and Reviewer acceptance and the final runtime-produced
product PDF remain subsequent workflow stages.
