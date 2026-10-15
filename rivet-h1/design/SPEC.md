# RIVET-H1 specification

## Scope and numerical contract

`rivet_h1_top` is fixed-width, single-clock, synthesizable streaming SHA-256,
implementing FIPS 180-4 sections 4.1.2, 4.2.2, 5 and 6.2:
<https://doi.org/10.6028/NIST.FIPS.180-4>. There are no user parameters.
Every SHA word is unsigned, 32 bits, with addition modulo 2^32.
All 64 schedule words, 64 rounds, standard initial words and round constants,
feed-forward and inter-block chaining are required.

The supported message length is **0 through 2^61-1 bytes inclusive**. A
64-bit unsigned byte counter checks a widened proposed count before every
accepted beat; a count beyond the supported range is an error, not a wrap.
The encoded length is the original byte count shifted left three, in 64-bit
big-endian form. Padding bytes are not counted. Near-limit arithmetic tests
are not claims of end-to-end hashing at those lengths.

## External interface

| Signal | Direction | Width | Meaning |
| --- | --- | --- | --- |
| clk | input | 1 | Rising-edge clock |
| rst_n | input | 1 | Asynchronous active-low reset |
| s_valid | input | 1 | Producer presents a beat |
| s_ready | output | 1 | Core can accept a beat |
| s_data | input | 32 | Message bytes, most significant byte first |
| s_keep | input | 4 | Byte validity, bit 3 describes bits 31:24 |
| s_last | input | 1 | This beat terminates the message |
| m_valid | output | 1 | Complete digest reserved for consumer |
| m_ready | input | 1 | Consumer can retire digest |
| m_digest | output | 256 | H0 in bits 255:224 through H7 in bits 31:0 |
| error | output | 1 | Sticky framing/length error; reset required |

An input transfer occurs at a rising edge only with `rst_n && s_valid &&
s_ready`. The producer holds valid, data, keep and last stable throughout a
stall. Invalid or stalled input is ignored, including illegal masks.
Nonfinal beats require `s_keep=1111`. A final beat permits `1000`, `1100`,
`1110`, or `1111` for one to four bytes. The only legal zero-byte beat is
the first and only beat of an empty message: `s_last=1, s_keep=0000`.
Other masks, including a zero-byte terminator after prior data, are illegal.
Unselected data lanes are ignored.

There is no first-message marker. The first beat after reset or digest
retirement starts a message. A multiple-of-four length ends with a full
final beat, not an additional zero-byte terminator. A multiple-of-64 length
still requires an entire padding block.

An output transfer occurs at a rising edge with `rst_n && m_valid &&
m_ready`. Digest bits and valid remain stable until transfer. Only one
message is outstanding. No input is accepted on the digest-retirement edge;
readiness becomes available after that edge for acceptance at the next edge.
Input pauses may be arbitrarily long.

## Padding and storage

One 64-byte block is gathered at up to one input beat per cycle. Compression
stalls input; gathering and compression do not overlap. Append `80`, then
zero bytes, then the 64-bit original bit length. A final occupied block of
0..55 bytes requires one compression, 56..63 requires two. A full 64-byte
final data block requires its own compression and a separate padding block.
The total compressed block count is `ceil((message_bytes + 9)/64)`.

## Cycle & degenerate-boundary table

Handshakes sample **pre-edge** values; new registered state is visible
**post-edge**. Reset takes priority over any transfer. No parameter tuples
exist; empty and minimal messages replace parameter-degeneracy coverage.

| Event | Required post-edge result |
| --- | --- |
| Active reset, including between clocks | s_ready=0, m_valid=0, m_digest=0, error=0; cancel all work |
| Reset release in empty gather state | s_ready=1; first subsequent rising edge may accept input |
| Ordinary accepted nonfinal beat | Append four bytes; increment length; remain gathering unless full |
| First and final empty beat | Count remains zero; stop gathering and begin final preparation |
| One-byte final beat / full four-byte final beat | Count selected bytes only; stop gathering |
| Accepted full block or final beat at E | s_ready becomes zero |
| E+1 | Prepare/freeze first compression block |
| E+2 = launch L | Capture block and chain; initialize working state; no round yet |
| E+3..E+66 = L+1..L+64 | Exactly rounds 0..63 |
| E+67 = L+65 | Registered compressor completion and feed-forward result |
| E+68, nonfinal | Consume completion, release block, resume gather |
| E+68, final with one compression | Consume completion; assert m_valid and digest |
| E+68, final with two compressions | Consume completion and prepare second block |
| E+69 | Launch second block |
| E+70..E+133 | Second-block rounds 0..63 |
| E+134 | Second-block registered completion |
| E+135 | Consume completion; assert m_valid and digest |
| First output transfer, m_ready already high | No earlier than E+69 or E+136, respectively |
| Output stalled | Keep valid and digest stable, forbid input |
| Output retirement | Clear message count/buffer, restore initial chain; no simultaneous input |
| Accepted framing/overflow error | Suppress digest, latch error, forbid input until reset |
| Reset concurrent with input/output/error | Reset wins; no transfer or sticky error survives |

Final-beat-to-first-valid latency is 68 or 135 cycles, independent of
producer gaps before that beat or output stalls after first valid.
Internal compressor launch-to-completion latency is exactly 65 cycles.
Full data blocks of nonfinal messages also obey the E through E+68 table.

## Reset, failure and limits

All sequential processes use asynchronous active-low reset. Reset cancels
partial gathering, prepared blocks, active rounds, pending completion and
stalled output. While reset is asserted, public outputs are explicitly gated
to the specified values. Deassert reset in accordance with system reset
recovery/removal requirements; this IP does not supply a reset synchronizer.

An accepted illegal framing or count overflow aborts the message, sets
sticky `error`, and holds `s_ready=0, m_valid=0` until reset. No aborted
message produces a digest. `m_digest` is zero after reset and may retain
the most recently completed digest when not valid. Valid digests must
contain no unknown/high-impedance bits.

No physical area, timing closure, FPGA performance or silicon-security
claim is made. There is no CDC, key storage, software hashing engine,
lookup-table digest path, test configuration or debug port.

## Frozen acceptance and ownership

Designer owns the five `rtl/*.sv` sources and this document plus
`design/ARCHITECTURE.md`. Independent Verifier owns `tests/*.py`, generated
testbenches, independent Python FIPS reference and execution evidence.
Required checks compare actual Icarus behavior with hashlib, published
vectors and the independently authored reference, test protocol/reset/error
semantics, measure cycles, detect three executing semantic mutations, run
generic Yosys synthesis/latch checks and reproduce smoke in a clean copy.

Mandatory message lengths include
0,1,2,3,4,7,8,15,16,31,32,54,55,56,57,62,63,64,65,119,120,127,128,129;
all 256 one-byte values; NIST empty, abc, standard 56-byte and 112-byte
messages and one million `a` bytes; binary lengths
4097,8191,8192,8193,16384,32768,65535,65536; and at least 128 random binary
messages for each seed 11,29,89 across 0..4096 with every residue modulo 64.
Require zero digest-bit mismatches and missing/extra outputs. Representative
padded blocks, expanded schedules and inter-block states are independently
compared. Arithmetic experiments cover 2^32-byte/bit boundaries, exact
maximum and overflow by one through four bytes.

Protocol checks include all illegal masks, sticky failure/recovery, input
gaps, randomized ignored lanes, output-ready transitions, continuous
next-message valid while blocked, stalls of at least 256 cycles and reset
cancellation in gather/preparation/launch/round/completion/output states.
Mutants independently corrupt encoded length, an active schedule rotation,
and inter-block chaining; each must execute and show an actual digest
mismatch with a passing pristine control. Preserve failed evidence.
Measurements include 100 consecutive 64-byte and 100 consecutive 1024-byte
messages without externally imposed gaps/stalls. Full acceptance details
remain the admitted work order, not a passing result asserted by this file.
