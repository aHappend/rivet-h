"""Disposable compiled RTL mutations; compile failures never count as detection."""

import json
import secrets
import shutil

from core_vectors import generate as core_generate
from execution import digest
from mldsa_reference import crosscheck_kats,decode_signature,encode_signature
from reference import PARAMS
from signature_vectors import Writer
from simulation import build,simulate,cleanup_objects,check_counts


MUTATIONS = (
    dict(name="montgomery-correction",file="rivet_h5_montgomery.sv",
         before="result <= normalized[22:0];",after="result <= normalized[22:0] ^ 23'd1;",
         bench="core_tb",diagnostic="Montgomery a="),
    dict(name="inverse-normalization",file="rivet_h5_ntt.sv",
         before="23'd16382",after="23'd16383",
         bench="core_tb",diagnostic="NTT inv=1"),
    dict(name="sampler-nonce-order",file="rivet_h5_sampler.sv",
         before="nonce[7:0] : nonce[15:8]",after="nonce[15:8] : nonce[7:0]",
         bench="core_tb",diagnostic="sampler op=0"),
    dict(name="norm-boundary",file="rivet_h5_verify.sv",
         before="23'd130994",after="23'd130995",
         bench="signature_tb",diagnostic="signature result transaction="),
    dict(name="usehint-sign",file="rivet_h5_usehint.sv",
         before="!wrapped && !round_up && (remainder != 0)",
         after="!wrapped && round_up && (remainder != 0)",
         bench="signature_tb",diagnostic="signature result transaction="),
    dict(name="challenge-comparison-bypass",file="rivet_h5_verify.sv",
         before="if (mismatch || (hash_m_data != challenge[8*hash_index +: 8])) begin",
         after="if (1'b0) begin",
         bench="signature_tb",diagnostic="signature result transaction="),
)


def signature_targets(path, fixture_path):
    fixture = json.loads(fixture_path.read_text())
    kat_outcomes = crosscheck_kats(fixture)
    group = next(g for g in fixture["testGroups"] if g["parameterSet"]=="ML-DSA-44")
    t = next(t for t in group["tests"] if t["testPassed"])
    level = 0
    pk,sig,msg,ctx = (bytes.fromhex(t[key]) for key in ("pk","signature","message","context"))
    with path.open("x") as f:
        w = Writer(f)
        w.reset()
        w.provision(pk,level)
        assert w.verification(pk,sig,msg,ctx,level,"public_valid")["auth"]
        c,z,hints = decode_signature(sig,level)
        forged = encode_signature(bytes([c[0]^1])+c[1:],z,hints,level)
        assert not w.verification(pk,forged,msg,ctx,level,"forged_challenge")["auth"]
        p = PARAMS[level]
        z = [[0]*256 for _ in range(p["l"])]
        z[0][0] = p["gamma1"]-p["beta"]
        forged = encode_signature(bytes(p["cbytes"]),z,[[0]*256 for _ in range(p["k"])],level)
        assert w.verification(pk,forged,b"",b"",level,"norm_exact_threshold")["status"]==4
    return dict(counts=dict(w.counts),cases=w.cases,public_kat_validation=kat_outcomes)


def suite(run, selection=None):
    core = run.path/"core-defect-vectors.txt"
    signature = run.path/"signature-defect-vectors.txt"
    core_coverage,_ = core_generate(core,compact=True)
    signature_coverage = signature_targets(signature,run.root/"tests/acvp_sigver.json")
    paths = dict(core_tb=core,signature_tb=signature)
    baselines = {}
    for bench in paths:
        argv,obj,obs = build(run,bench,"verilator",observe=(bench=="signature_tb"),
                            clock_limit=500000 if bench=="core_tb" else None)
        try:
            rec,out = simulate(run,argv,paths[bench],f"unchanged-baseline-{bench}","verilator")
            inventory = core_coverage if bench=="core_tb" else signature_coverage["counts"]
            observed = check_counts(out,inventory,bench)
            baselines[bench] = dict(stdout=rec["stdout"],stderr=rec["stderr"],
                                    observation=obs,observed=observed)
        finally:
            cleanup_objects(obj)
    results = []
    selected = MUTATIONS if selection is None else tuple(
        mutation for mutation in MUTATIONS if mutation["name"] in selection)
    if not selected and selection != ("legacy-digest",):
        raise ValueError("empty diagnostic mutation selection")
    for mutation in selected:
        copy_root = run.path/("mutant-"+mutation["name"]+"-"+secrets.token_hex(4))
        (copy_root/"rtl").mkdir(parents=True)
        for p in sorted(run.root.glob("rtl/*.sv")):
            shutil.copyfile(p,copy_root/"rtl"/p.name)
        mutated = copy_root/"rtl"/mutation["file"]
        original_hash = digest(mutated)
        text = mutated.read_text()
        if text.count(mutation["before"])!=1:
            raise AssertionError(f"mutation anchor not unique: {mutation['name']}")
        # Disposable copies only, never accepted RTL.
        mutated.write_text(text.replace(mutation["before"],mutation["after"]))
        argv,obj,obs = build(run,mutation["bench"],"verilator",source_root=copy_root,
                            observe=(mutation["bench"]=="signature_tb"),
                            clock_limit=500000 if mutation["bench"]=="core_tb" else None)
        try:
            rec,out,err = run.command([*argv,"+vectors="+str(paths[mutation["bench"]])],
                                      "mutated-"+mutation["name"],expect_failure=True)
            if rec["exit_status"]==0 or rec["timed_out"]:
                raise AssertionError(f"mutation not behaviorally detected: {mutation['name']}")
            if mutation["diagnostic"] not in out+err:
                raise AssertionError(f"mutation failed without intended comparison: {mutation['name']}")
            results.append(dict(name=mutation["name"],original_sha256=original_hash,
                                mutated_sha256=digest(mutated),file=run.relative(mutated),
                                mutation=mutation,observation=obs,stdout=rec["stdout"],
                                stderr=rec["stderr"],exit_status=rec["exit_status"],
                                discriminating_failure=next(
                                    line for line in (out+err).splitlines()
                                    if mutation["diagnostic"] in line)))
        finally:
            cleanup_objects(obj)
    if selection is None or "legacy-digest" in selection:
        results.append(legacy_mutation(run))
    return dict(baselines=baselines,mutations=results,
                core_inventory=core_coverage,signature_inventory=signature_coverage)


def legacy_mutation(run):
    from legacy_checks import build as legacy_build, check_counts as legacy_counts
    from legacy_vectors import generate as legacy_generate
    path = run.path/("legacy-defect-vectors-"+secrets.token_hex(4)+".txt")
    inventory = legacy_generate(path,1,3,compact=True)
    argv,obj,parent = legacy_build(run,1,3)
    try:
        rec,out,_ = run.command([*argv,"+vectors="+str(path)],"unchanged-legacy-baseline")
        baseline = dict(stdout=rec["stdout"],stderr=rec["stderr"],
                        observed=legacy_counts(out,inventory),parent_copy=parent)
    finally:
        cleanup_objects(obj)
    copied = run.path/("mutant-legacy-digest-"+secrets.token_hex(4))
    (copied/"rtl").mkdir(parents=True)
    for source in sorted(run.root.glob("rtl/*.sv")):
        shutil.copyfile(source,copied/"rtl"/source.name)
    source = copied/"rtl/rivet_h3_top.sv"
    original = digest(source)
    before = "channel_digest[digest_grant] : 512'd0;"
    after = "(channel_digest[digest_grant] ^ 512'd1) : 512'd0;"
    text = source.read_text()
    if text.count(before)!=1:
        raise AssertionError("legacy digest mutation anchor not unique")
    source.write_text(text.replace(before,after))
    argv,obj,parent = legacy_build(run,1,3,source_root=copied)
    try:
        rec,out,err = run.command([*argv,"+vectors="+str(path)],"mutated-legacy-digest",
                                  expect_failure=True)
        diagnostic = "interleaved legacy digest ch="
        if rec["exit_status"]==0 or rec["timed_out"] or diagnostic not in out+err:
            raise AssertionError("legacy public-pin oracle did not detect disposable digest defect")
        return dict(name="legacy-digest",original_sha256=original,mutated_sha256=digest(source),
                    file=run.relative(source),before=before,after=after,baseline=baseline,
                    stdout=rec["stdout"],stderr=rec["stderr"],exit_status=rec["exit_status"],
                    discriminating_failure=next(line for line in (out+err).splitlines()
                                                if diagnostic in line))
    finally:
        cleanup_objects(obj)
