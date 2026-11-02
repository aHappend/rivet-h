"""Explicit full-top legal elaboration and executable illegal diagnostics."""

import secrets

from legacy_checks import wiring


def diagnostic(run, all_legal=False):
    directory = run.path / ("parameter-build-" + secrets.token_hex(4))
    directory.mkdir()
    wiring(run, directory, parameter_only=True)
    bench = directory / "parameter_tb.sv"
    with bench.open("x") as f:
        f.write("module parameter_tb; parameter integer PARTIAL_BEATS=0, MAX_PAGE_BYTES=1;\n"
                "reg clk=0,rst_n=0; always #5 clk=!clk;\n"
                '`include "legacy_wires.svh"\n'
                'initial begin #20; $display("LEGAL_PARAMETER_EXECUTION"); $finish; end\n'
                "endmodule\n")
    sources = [str(p) for p in sorted(run.root.glob("rtl/*.sv"))]
    results = []
    for partial, page in [(-1, 1), (2, 1), (0, 0), (0, 4097)]:
        binary = directory / (f"illegal-p{partial}-page{page}-" + secrets.token_hex(4) + ".vvp")
        run.command(["iverilog", "-g2012", "-Wall", "-s", "parameter_tb", "-I", str(directory),
                     f"-Pparameter_tb.PARTIAL_BEATS={partial}",
                     f"-Pparameter_tb.MAX_PAGE_BYTES={page}", "-o", str(binary),
                     str(bench), *sources], "compile-illegal-parameter")
        rec, out, err = run.command(["vvp", str(binary)], "reject-illegal-parameter",
                                   timeout=600, expect_failure=True)
        if rec["exit_status"] == 0 or "PARAMETER ERROR" not in out + err:
            raise AssertionError(f"illegal tuple {partial}/{page} lacks explicit rejection")
        results.append(dict(partial=partial, page=page, stdout=rec["stdout"], stderr=rec["stderr"]))
    legal = range(1,4097) if all_legal else (1,3,4,5,4095,4096)
    timings = []
    for partial in (0, 1):
        for page in legal:
            rec,_,_ = run.command(["iverilog", "-g2012", "-Wall", "-tnull", "-s", "parameter_tb",
                         "-I", str(directory), f"-Pparameter_tb.PARTIAL_BEATS={partial}",
                         f"-Pparameter_tb.MAX_PAGE_BYTES={page}", str(bench), *sources],
                        f"elaborate-p{partial}-page{page}")
            timings.append(rec["duration_seconds"])
            if page % 128 == 0:
                print(f"legal parameter elaboration p={partial} page={page}/4096", flush=True)
    return dict(legal_elaborations=2*len(legal), illegal_rejections=results,
                elapsed_compiler_seconds=sum(timings),
                scope="Full rivet_h5_top elaboration", page_values=list(legal))


def suite(run):
    return diagnostic(run, all_legal=True)
