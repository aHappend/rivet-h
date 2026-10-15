# RIVET-H2

HMAC-SHA-256 and context save/restore.

**Status:** Engineering accepted.

## Reproduce

Requires Python 3, Icarus Verilog (`iverilog`, `vvp`) and Yosys.
Run the admitted checks from this generation's directory:

```bash
python3 tests/verify.py --check behavior --output evidence/behavior
python3 tests/verify.py --check compatibility --output evidence/compatibility
python3 tests/verify.py --check defects --output evidence/defects
python3 tests/verify.py --check synthesis --output evidence/synthesis
python3 tests/verify.py --check portable --output evidence/portable
```

The test driver creates fresh local evidence. A published status is not a new run on your machine.

Use a clean checkout or fresh output directories when a driver refuses existing evidence.

[Specification](design/SPEC.md) · [Architecture](design/ARCHITECTURE.md) · [RTL](rtl/) · [Verification source](tests/) · [Recorded check statuses](STATUS.json)

[Reviewed product report](REPORT.pdf) · [LaTeX source](REPORT.tex)

Simulation and generic synthesis do not establish physical signoff or measured silicon performance.
