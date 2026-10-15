# RIVET-H2 architecture

## Frozen implementation boundaries

One active hardware context shares one iterative SHA-256 compressor across SHA
messages, key hashing, ipad/opad seed generation and both HMAC phases. Software
owns exported images and schedules interleaving; there are no hardware context
slots or external key IDs. All signals are in the `clk` domain.

The following interfaces and instance names are frozen before implementation.
All widths below are bits; all ports and arithmetic are unsigned.

| Instance / module | Interface and ownership |
| --- | --- |
| `rivet_h2_top` | Public protocol, command arbitration, 64-bit accepted-byte count, active chain/mode, registered digest/context outputs, compression work registers and FSM. Only public parameter: integer `PARTIAL_BEATS`, 0 or 1. |
| `u_stream` / `rivet_h2_stream` | Inputs `clk,rst_n,clear,load,release_block,capture,drain`, `load_buffer[511:0],load_used[6:0],beat_data[31:0],beat_bytes[2:0],beat_last`. Outputs `block_data[511:0],used_bytes[6:0],staged,byte_fire,byte_data[7:0],beat_end,last_pending`. Owns one registered beat, byte-at-a-time block assembly, canonical zero tail. `last_pending` is the staged beat's last flag, not a message-finalization register. |
| `u_hmac` / `rivet_h2_hmac` | Inputs `clk,rst_n,clear,begin_key,restore,restore_key_valid,restore_inner[255:0],restore_outer[255:0],key_byte_valid,key_byte[7:0],normalize,long_key,hash_digest[255:0],write_inner,write_outer,seed_result[255:0]`. Outputs `key_valid,inner_seed[255:0],outer_seed[255:0],ipad_block[511:0],opad_block[511:0]`. Owns first-64-key-byte retention, normalization and installed seeds. `write_outer` completes key installation. |
| `u_context` / `rivet_h2_context` | Combinational inputs `mode,key_valid,count[63:0],used[6:0],chain[255:0],inner_seed[255:0],outer_seed[255:0],buffer_data[511:0],candidate[1535:0]`. Outputs `encoded[1535:0],candidate_valid`. Encoding is canonical; validation is complete before top-level restore commits. |
| `u_compress` / `rivet_h2_compress` | Inputs `clk,rst_n,clear,start,block_data[511:0],state_in[255:0]`. Outputs `busy,done,state_out[255:0]`. One block, 64 rounds and feed-forward. |
| `u_compress.u_schedule` / `rivet_h2_schedule` | Inputs `clk,rst_n,clear,load,step,block_data[511:0],round_index[5:0]`. Output `word[31:0]`. Owns sixteen 32-bit schedule words. |

The compressor and schedule arithmetic are derived from the supplied
`rivet_h1_reference/rtl/rivet_h1_compress.sv` and
`rivet_h1_reference/rtl/rivet_h1_schedule.sv`. Their arithmetic and round timing
are retained, with an explicit synchronous cancellation clear added. The five
reference files are immutable provenance, not a numerical oracle or a claimed
passing baseline. No linked repository intake index was supplied.

## State, storage and dependencies

The stream unit holds 512 block bits, a seven-bit used count, one 32-bit staged
beat, its remaining-byte count, validity and final flag. A full block suspends
draining even if the staged beat has remaining bytes. Releasing a compressed
data block clears the block/used count but preserves that beat. There is no
multi-byte dynamic write crossing a block boundary.

Top-level `byte_count` counts all bytes of a legally accepted beat immediately;
the stage then drains them. No context is available until the stage has drained
and any full block has completed compression. Thus exported count, chain and
partial bytes always describe the same prefix. Whole-beat length checks precede
capture; an overflowing beat changes no count or block byte.

The key manager retains at most 64 key bytes. All key bytes also pass through
the shared SHA engine. At final key hash completion, keys of at most 64 bytes
use the retained zero-padded original key, and longer keys replace it with
`SHA256(key) || 256'b0`. Hashing short keys is an implementation latency choice,
not a change to RFC normalization. No unbounded key array is inferred.
The compressor then processes the ipad and opad blocks from the SHA IV. The
outer-seed write installs the key and returns the top to empty SHA mode.
Normalized key storage is cleared after seed installation; only the seeds are
needed for subsequent messages.

| Consumer assumption | Producer guarantee |
| --- | --- |
| Stream capture sees a legal beat within its length bound | Top validates mask and complete proposed count before asserting capture. |
| Block input is complete and registered at compressor launch | Top prepares work registers before entering `LAUNCH`; no launch from a byte-append edge. |
| Stream release cannot discard remaining staged bytes | Release resets only block/used; top does not drain in `WAIT_BLOCK`. |
| Key byte order is the public lane order | Stream exposes exactly each byte appended, once, to the key manager. |
| Saved state has no transient compressor/padding state | Top permits SAVE only at quiescent points. |
| Imported mode, seeds, chain and buffer share ownership | Complete image validation gates one atomic restore edge. |
| A canceled compressor cannot finish later | CANCEL clears compressor, schedule, stream, key manager and top on the accepted edge. |

## Cycle & Degenerate-Boundary Table

Handshakes sample **pre-edge** values; changes below are **post-edge**
nonblocking updates. Readiness never promises same-edge processing of a newly
captured beat.

| Boundary / event | Result |
| --- | --- |
| `rst_n=0`, including between clocks | Every public output is zero; all sequential storage is asynchronously reset. |
| First clock after reset release | Fresh empty SHA can accept a beat or command if presented; no reset epoch output survives. |
| Legal beat accepted at E | Stage captures exactly once; readiness falls after E. |
| E+1 through E+n | At most one byte appends per edge. Full-block processing may interrupt this sequence. |
| Empty final beat | A zero-byte stage still drains on the following edge and sets finalization pending. |
| Last byte fills byte 63 of block | Used becomes 64; no further byte drains until block compression and release. |
| Non-final full block | Compress the data block, update chain, clear buffer, then resume remaining stage bytes. |
| Final full block | Compress full data block, then create a new padding block containing `80` and the final bit count. |
| Partial final block with used <=55 | One padded block; length in low 64 bits. |
| Partial final block with used >=56 | First block has marker, second zero block has length. |
| `PREPARE_DATA` / `PREPARE_PAD` | Register work block and initial chain; next state is `LAUNCH`. |
| Launch L | Compressor captures already-registered block/state; top enters `WAIT_BLOCK`. |
| L+1..L+64 | Rounds 0..63. |
| L+65 | Compressor registers feed-forward result and asserts `done`. |
| L+66 | Top consumes result. Continuations may prepare the next registered block here and launch on L+67. |
| Final inner HMAC result | Prepare `inner_digest || 80 || zeros || 64'd768` with the installed outer seed, then launch outer compression. |
| SAVE at E | Complete image and `ctx_valid` register after E; no same-edge output retirement. |
| Context stall / retirement | Image holds unchanged; retirement returns to gather. Ordinary input resumes no earlier than following edge. |
| RESTORE at E | Validate entire image, then atomically replace or fault; resumed input no earlier than E+1. |
| Digest retirement at E | Clear message count/buffer/stage and select IV or installed inner seed in the current mode; next input no earlier than E+1. |
| Simultaneous eligible command and stream offers | Command wins; both stream readiness signals are suppressed. |
| CANCEL and any other event | CANCEL wins, clears all work and keys, selects fresh SHA. Pending outputs are explicitly discarded. |
| Illegal accepted input / command / image | Sticky FAULT; no output validity or stream readiness. Only CANCEL is ready. |
| `PARTIAL_BEATS=0` / `1` | Strict H1 masks / explicit partial non-final extension. No other width/depth parameters. |
| `PARTIAL_BEATS=-1` / `2` or any other value | Explicit parameter diagnostic; unsupported hardware, not a clamped configuration. |

## Complete top-level state flow

`GATHER` captures or drains stream beats. When the registered block has 64 bytes,
it moves through `PREPARE_DATA -> LAUNCH -> WAIT_BLOCK`. Data completion updates
chain and releases only the block before returning to `GATHER`. A drained final
beat sets `final_pending`; after all data blocks it selects `PREPARE_PAD`.

`PREPARE_PAD -> LAUNCH -> WAIT_BLOCK` handles the marker/length block. A required
second padding block is prepared at the first padding completion and follows
`LAUNCH -> WAIT_BLOCK` again. SHA completion enters `OUTPUT_DIGEST`. Key-hash
completion normalizes the key and enters `PREPARE_IPAD`, then executes ipad and
opad compressions with the IV. Opad completion installs seeds and returns to
empty SHA `GATHER`. HMAC-inner completion launches the outer digest block;
outer completion enters `OUTPUT_DIGEST`.

`OUTPUT_CONTEXT` and `OUTPUT_DIGEST` accept only their own output retirement or
CANCEL. `FAULT` accepts only CANCEL. No state admits an ordinary command during
key ingestion, normalization, seed generation, staged-byte draining, full-block
processing or finalization.

A SAVE held during padding/compression is backpressured, not an in-flight
snapshot. If held through digest retirement, it can next capture only the newly
empty message. RESTORE held across the same interval likewise acts only when
quiescent. Software wanting the prefix before final padding must request SAVE
before accepting its final beat.

## Cost and performance scope

There is one compressor and one schedule, not separate key/inner/outer datapaths.
The architecture specifies fixed block-round timing but does not claim fixed
whole-message latency. Stream staging/draining, padding blocks, key length,
commands and downstream stalls all affect cycles. Independent verification owns
measured latency/throughput, completed-message counts, source/module sizes and
generic synthesis cell/state counts. No measured performance or correctness
results exist at this design handoff. Generic cell counts are not physical area,
timing closure, FPGA measurements or silicon-security certification.
