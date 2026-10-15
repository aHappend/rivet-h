# RIVET-H1 architecture and integration

## Source inventory and literal hierarchy

All required design sources are the five files below, with no include files,
generated ROMs, external engines or legal parameter variants.

```text
rtl/rivet_h1_top.sv            rivet_h1_top
  rtl/rivet_h1_length.sv        u_length
  rtl/rivet_h1_pad.sv           u_pad
  rtl/rivet_h1_compress.sv      u_compress
    rtl/rivet_h1_schedule.sv      u_schedule
design/SPEC.md
design/ARCHITECTURE.md
```

The top sequences a single-block buffer and iterative compressor. Keeping
ownership serialized avoids double buffering, throughput overlap and
multiple outstanding-message machinery. It does not limit total message
length to buffer capacity. The supported byte count remains 0..2^61-1.
See `design/SPEC.md` for the complete frozen external interface and cycle
table.

## Internal contracts and ownership

All controls below are sampled on rising edges; all sequential modules have
asynchronous active-low reset. Inputs to a launch remain stable through the
launch edge. Internal block/word/state vectors use the same big-endian
packing as the public stream/digest.

| Module | Inputs/control | Outputs/storage | Dependency guaranteed by top |
| --- | --- | --- | --- |
| u_length | clear, accept, beat_bytes[2:0] | byte_count[63:0], next_byte_count[63:0], overflow | accept only a legal, nonoverflowing public transfer; clear on output retirement |
| u_pad | clear, append, beat_data[31:0], beat_bytes[2:0], prepare, final_block, prepare_second, release_block, bit_length[63:0] | block_data[511:0], used_bytes[6:0], needs_second | append only in gather with space; prepare after last append; freeze while compressing |
| u_compress | start, block_data[511:0], state_in[255:0] | busy, done, state_out[255:0] | one-cycle start while idle, no overlapping launch |
| u_schedule | load, step, block_data[511:0], round_index[5:0] | word[31:0], sixteen 32-bit words | load on compressor launch; step once for every round |

`clear` dominates acceptance in the length module. Its 65-bit proposed sum
is compared with 2^61-1 before committing the 64-bit count. `overflow` and
`next_byte_count` are combinational proposals, meaningful even when accept
is low; only an accepted beat can cause a top-level error.

The pad module has one 512-bit block register, a 0..64 byte occupancy and
two padding flags. The next unused byte and all following bytes are zero
because reset, retirement and nonfinal-block release clear the buffer.
Only selected input lanes are copied. Preparation writes the marker and,
when space permits, the length. For a full final data block it leaves
data unchanged and records that the second block needs a marker. For a
56..63-byte tail it puts the marker in the first block; the second block
needs only zeros and length. `prepare_second` replaces the buffer after
first-block completion, never during active compression. Its priority is
reset, clear/release, prepare_second, prepare, append.

The schedule module loads big-endian W0..W15 at launch. Rounds 0..15 read
these words without shifting. For rounds 16..63 the array contains
W[t-16]..W[t-1], and computes
`sigma1(words[14]) + words[9] + sigma0(words[1]) + words[0]`.
At each such round edge it shifts and appends the computed word.
Small sigma rotations/shifts are (7,18,3) and (17,19,10).

The compressor captures the incoming eight-word chain and initializes
a..h on launch. Each of the next 64 edges performs one SHA-256 round
using the schedule output and a constant selected by the round index.
Big sigma rotations are (2,13,22) and (6,11,25); Ch and Maj are bitwise.
The following edge adds the original chain to the final working state
and pulses registered `done` for one cycle. `state_out` remains registered
until another completion. The top consumes that pulse one edge later.
No round executes at launch.

The top's states are GATHER, PREPARE, LAUNCH, WAIT_BLOCK, OUTPUT_DIGEST,
and FAULT. A full block or final beat exits gathering. PREPARE freezes
the padded/data block, LAUNCH starts compression, and WAIT_BLOCK consumes
the registered result. Nonfinal completion releases the buffer; final
completion either prepares/launches the second padding block or reserves
the digest. Every result updates `chain_state`; digest retirement resets
that chain to the standard initial state before another message.

Illegal accepted framing or overflow enters FAULT and asserts sticky
error. No further transfer is possible until reset. Invalid input while
not accepted cannot alter the message. The output state itself reserves
the digest, preventing input acceptance even on the retirement edge.
Public output gating enforces active-reset values independently of the
current FSM state. All datapath registers are reset; no uninitialized
buffer or schedule word is used.

## Integration

Compile all five files as SystemVerilog and select `rivet_h1_top`. Supply
one clock and active-low asynchronous reset; externally synchronize reset
release to meet the implementation technology's requirements. Assert
reset before the first message. After release, transfer MSB-first beats
only when ready, preserving the complete beat under stall. Terminate using
the legal masks in the specification, including the empty-message token.
Wait for digest valid, and drive ready to retire it. Following an error,
reset before sending any new message. There are no configuration registers,
parameters, initialization files or nonstandard simulation dependencies.

Static parse/elaboration from the delivered project root:

```sh
iverilog -g2012 -s rivet_h1_top -t null rtl/rivet_h1_top.sv rtl/rivet_h1_length.sv rtl/rivet_h1_pad.sv rtl/rivet_h1_compress.sv rtl/rivet_h1_schedule.sv
```

The independent verification entry point is `tests/verify.py`; its Python
helpers, testbench generation and evidence belong to Verifier, not to RTL.
Required tools are Python 3 with standard-library hashlib, Icarus
`iverilog`/`vvp`, and Yosys. Exact installed versions and real results must
come from retained execution receipts, not assumptions in this document.
No installation is part of reproduction.

Run from the project root after the independent verification sources are
delivered:

```sh
python3 tests/verify.py --suite behavior --out evidence/behavior
python3 tests/verify.py --suite sensitivity --out evidence/sensitivity
python3 tests/verify.py --suite synthesis --out evidence/synthesis
python3 tests/verify.py --suite portable --out evidence/portable
python3 tests/verify.py --suite smoke --out evidence/smoke
```

Declared portable inputs are `rtl/*.sv`, `tests/*.py`, `design/SPEC.md` and
`design/ARCHITECTURE.md`. Generated testbenches, models' intermediate data,
simulator executables, synthesis scripts/netlists/statistics and raw
stdout/stderr are outputs under each selected evidence directory. Fresh
portable reproduction copies only the declared sources and runs a child
smoke suite; it must not depend on prior generated files. The final product
PDF is authored after engineering acceptance and is not a source dependency
of any engineering check.

## Cycle measurements and claims

The contract requires 65 cycles per compressor launch-to-completion,
64 round-update edges, top completion consumption one edge later, and
68/135 final-beat-to-first-valid cycles for one/two final compressions.
First-input latency also includes prior gathering, input gaps and nonfinal
block compression. Output stalls affect retirement but not first-valid time.
These are architectural requirements, not measured results in this handoff.

The independent trace must report acceptance and retirement edges, block
and round counts, first-input/final-beat-to-first-valid latency, output-stall
duration and elapsed cycles. Sustained 64-byte and 1024-byte message runs
each contain at least 100 consecutive messages with no externally imposed
gaps or output stalls. Measure inclusive cycles from the first input
handshake to the last output handshake. Divide that interval by message
count for cycles/message and total accepted payload bytes by that interval
for payload bytes/cycle; do not count padding as payload. Distinguish padding
overhead, serialized compression cost and externally stalled traffic.

Report actual source/module line and byte counts, verification source size,
zero cryptographic mismatch counts and Yosys generic cell statistics only
from independently retained execution. Generic cells are not physical area;
there is no clock-frequency, timing-closure, FPGA or silicon-security claim.
No functional, mutation or synthesis pass is asserted by implementation alone.
