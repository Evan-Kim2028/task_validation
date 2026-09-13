import json
from pathlib import Path

import pytest

from task_validation.sampling.certificate import (
    SWE_EXEC_PROTOCOL,
    build_certificate,
    coverage_check,
    main,
    p_certify,
    render_certificate_md,
    swe_exec_to_verdicts,
)
from task_validation.sampling.designs import simple_random
from task_validation.sampling.estimators import hypergeometric_upper, srs_estimate


PROTOCOL = "test.protocol.v0"


def _verdict(uid, invalid, *, grade="A", protocol=PROTOCOL, adjudicator="human", evidence=""):
    return {
        "unit_id": uid,
        "invalid": invalid,
        "label_protocol": protocol,
        "grade": grade,
        "evidence": evidence,
        "adjudicator": adjudicator,
    }


def _manifest(ids, n_pop, seed="fix-v0", design="SRS without replacement"):
    return {
        "design": design,
        "N": n_pop,
        "n": len(ids),
        "ids": list(ids),
        "seed": seed,
    }


def test_hypergeometric_ucb_matches_estimators():
    n_pop, n, k = 1000, 50, 2
    ids = [f"t{i:03d}" for i in range(n)]
    verdicts = [_verdict(uid, i < k, evidence=f"flag {uid}" if i < k else "") for i, uid in enumerate(ids)]
    cert = build_certificate(_manifest(ids, n_pop), verdicts, 0.05, PROTOCOL, "human")
    est = srs_estimate(k, n, n_pop)
    hg = hypergeometric_upper(k, n, n_pop)
    assert cert["complete"] is True
    assert cert["k_invalid"] == k
    assert cert["p_hat"] == est.p_hat == k / n
    assert abs(cert["ucb95"] - est.ucb95) < 1e-15
    assert abs(cert["ucb95"] - hg) < 1e-15
    assert "hypergeometric" in cert["method"]
    assert cert["ucb95"] > cert["p_hat"]
    assert cert["decision"] == "reject"
    assert cert["flagged"][0]["unit_id"] == "t000"
    assert cert["p_certify"] == p_certify(n, n_pop, cert["p_hat"], 0.05)


def test_census_ucb_is_observed_rate():
    ids = [f"u{i}" for i in range(8)]
    verdicts = [_verdict(uid, uid in {"u0", "u3"}, evidence="x" if uid in {"u0", "u3"} else "") for uid in ids]
    cert = build_certificate(_manifest(ids, n_pop=8), verdicts, 0.30, PROTOCOL, "human")
    assert cert["n"] == cert["N"] == 8
    assert cert["k_invalid"] == 2
    assert cert["p_hat"] == 0.25
    assert cert["ucb95"] == 0.25
    assert cert["method"] == "census"
    assert cert["decision"] == "release"
    cp = srs_estimate(2, 8, 8)
    assert cp.ucb95 > cert["ucb95"]
    reject = build_certificate(_manifest(ids, n_pop=8), verdicts, 0.20, PROTOCOL, "human")
    assert reject["decision"] == "reject"
    assert reject["p_certify"] == 0.0


def test_incomplete_does_not_impute():
    ids = [f"t{i}" for i in range(5)]
    verdicts = [
        _verdict("t0", True, evidence="broken"),
        _verdict("t1", False),
        _verdict("t2", None),
        _verdict("t3", False, grade="C"),
        # t4 missing
    ]
    cert = build_certificate(_manifest(ids, n_pop=20), verdicts, 0.05, PROTOCOL, "human")
    assert cert["complete"] is False
    assert cert["decision"] == "incomplete"
    assert cert["ucb95"] is None
    assert cert["p_hat"] is None
    assert cert["k_invalid"] is None
    assert "t2" in cert["unadjudicated"]
    assert "t3" in cert["unadjudicated"]
    assert "t4" in cert["unadjudicated"]
    assert cert["n_unadjudicated"] == 3
    assert cert["flagged"][0]["unit_id"] == "t0"
    md = render_certificate_md(cert)
    assert "INCOMPLETE" in md
    assert "t2" in md


def test_coverage_check_300_replicates():
    n_pop, n, k_pop, reps = 400, 50, 8, 300
    ids = [f"p{i:03d}" for i in range(n_pop)]
    population = {uid: int(i < k_pop) for i, uid in enumerate(ids)}
    census = [{"unit_id": uid, "invalid": bool(population[uid])} for uid in ids]
    true_p = k_pop / n_pop
    hits = 0
    for r in range(reps):
        seed = f"cert-cover-v0:{r}"
        draw = simple_random(ids, n, seed)
        manifest = _manifest(draw.ids(), n_pop, seed=seed)
        report = coverage_check(census, manifest, 0.05, PROTOCOL, "human")
        assert abs(report["census_p"] - true_p) < 1e-15
        assert report["complete"] is True
        if report["covered"]:
            hits += 1
        assert report["covered"] == (true_p <= report["ucb95"] + 1e-12)
    assert hits / reps >= 0.95


def test_swe_exec_to_verdicts_gold_fail_and_empty_accept():
    rows = [
        {
            "instance_id": "a",
            "treatment": "gold",
            "rep": 0,
            "status": "executed",
            "resolved": False,
            "pass_to_pass_failure": ["t_p2p"],
        },
        {
            "instance_id": "a",
            "treatment": "empty",
            "rep": 0,
            "status": "executed",
            "resolved": False,
            "pass_to_pass_failure": [],
        },
        {
            "instance_id": "b",
            "treatment": "gold",
            "rep": 0,
            "status": "executed",
            "resolved": True,
            "pass_to_pass_failure": [],
        },
        {
            "instance_id": "b",
            "treatment": "empty",
            "rep": 0,
            "status": "executed",
            "resolved": True,
            "pass_to_pass_failure": [],
        },
        {
            "instance_id": "c",
            "treatment": "gold",
            "rep": 0,
            "status": "executed",
            "resolved": True,
            "pass_to_pass_failure": [],
        },
        {
            "instance_id": "c",
            "treatment": "empty",
            "rep": 0,
            "status": "executed",
            "resolved": False,
            "pass_to_pass_failure": [],
        },
        {
            "instance_id": "d",
            "treatment": "gold",
            "rep": 0,
            "status": "infra",
            "resolved": None,
            "pass_to_pass_failure": [],
        },
        {
            "instance_id": "d",
            "treatment": "empty",
            "rep": 0,
            "status": "executed",
            "resolved": False,
            "pass_to_pass_failure": [],
        },
    ]
    verdicts = swe_exec_to_verdicts(rows)
    by = {v["unit_id"]: v for v in verdicts}
    assert by["a"]["invalid"] is True
    assert by["a"]["label_protocol"] == SWE_EXEC_PROTOCOL
    assert by["a"]["grade"] == "A"
    assert by["a"]["adjudicator"] == "machine"
    assert "reference fails own verifier" in by["a"]["evidence"]
    assert "P2P-break-on-gold: t_p2p" in by["a"]["evidence"]
    assert by["b"]["invalid"] is True
    assert "empty patch resolved (false accept)" in by["b"]["evidence"]
    assert by["c"]["invalid"] is False
    assert by["d"]["invalid"] is None
    ids = ["a", "b", "c"]
    cert = build_certificate(
        _manifest(ids, n_pop=10),
        [by[i] for i in ids],
        0.50,
        SWE_EXEC_PROTOCOL,
        "machine",
    )
    assert cert["adjudicator"] == "machine"
    assert cert["replaces_human_sample"] is False
    assert cert["k_invalid"] == 2
    assert "hypergeometric" in cert["method"]


def test_cli_writes_json_and_md(tmp_path: Path):
    ids = [f"t{i}" for i in range(4)]
    manifest = _manifest(ids, n_pop=20, seed="cli-v0")
    verdicts = [_verdict(uid, False) for uid in ids]
    mpath = tmp_path / "m.json"
    vpath = tmp_path / "v.jsonl"
    out = tmp_path / "c.certificate.json"
    md = tmp_path / "c.md"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    vpath.write_text("\n".join(json.dumps(v) for v in verdicts) + "\n", encoding="utf-8")
    rc = main(
        [
            "--manifest",
            str(mpath),
            "--verdicts",
            str(vpath),
            "--epsilon",
            "0.05",
            "--protocol",
            PROTOCOL,
            "--adjudicator",
            "human",
            "--out",
            str(out),
            "--md",
            str(md),
        ]
    )
    assert rc == 0
    cert = json.loads(out.read_text(encoding="utf-8"))
    assert cert["n"] == 4
    assert cert["k_invalid"] == 0
    assert "hypergeometric" in cert["method"]
    text = md.read_text(encoding="utf-8")
    assert "Validity certificate" in text
    assert PROTOCOL in text


def _judge_verdict(uid, invalid, *, model="judge-x-2026", agreement=None, protocol="judge.protocol.v0"):
    row = _verdict(uid, invalid, protocol=protocol, adjudicator="human")
    row["verifier_kind"] = "judge"
    row["judge_model"] = model
    row["judge_agreement"] = agreement or {
        "reference": {"accepts": 3, "runs": 3},
        "nop": {"rejects": 3, "runs": 3},
    }
    return row


def test_judge_stratum_records_model_and_agreement():
    ids = [f"j{i}" for i in range(4)]
    verdicts = [_judge_verdict(uid, False) for uid in ids]
    verdicts[1] = _judge_verdict(
        "j1",
        True,
        agreement={
            "reference": {"accepts": 1, "runs": 3},
            "nop": {"rejects": 3, "runs": 3},
        },
    )
    cert = build_certificate(
        _manifest(ids, n_pop=10),
        verdicts,
        0.60,
        "judge.protocol.v0",
        "human",
        verifier_kind="judge",
    )
    assert cert["complete"] is True
    assert cert["verifier_kind"] == "judge"
    assert cert["judge_model"] == ["judge-x-2026"]
    assert cert["judge_agreement"]["j1"]["reference"]["accepts"] == 1
    assert cert["judge_agreement"]["j0"]["nop"]["rejects"] == 3
    assert cert["strata"] == {"judge": 4}
    assert cert["k_invalid"] == 1
    md = render_certificate_md(cert)
    assert "Verifier kind: judge" in md
    assert "judge-x-2026" in md
    assert "Judge agreement" in md


def test_judge_verdicts_never_pool_into_execution_stratum():
    ids = ["e0", "e1", "j0", "j1"]
    verdicts = [
        _verdict("e0", False),
        _verdict("e1", False),
        _judge_verdict("j0", False, protocol=PROTOCOL),
        _judge_verdict("j1", False, protocol=PROTOCOL),
    ]
    cert = build_certificate(
        _manifest(ids, n_pop=20), verdicts, 0.05, PROTOCOL, "human"
    )
    assert cert["complete"] is False
    assert set(cert["unadjudicated"]) == {"j0", "j1"}
    assert "verifier_kind" in cert["unadjudicated_reasons"]["j0"]
    assert cert["strata"] == {"execution": 2, "judge": 2}
    # The judge units did not enter the bound: k and p_hat stay uncomputed.
    assert cert["k_invalid"] is None

    # Splitting the strata makes the judge certificate complete.
    j_verdicts = [
        _judge_verdict("j0", False, protocol=PROTOCOL),
        _judge_verdict("j1", False, protocol=PROTOCOL),
    ]
    j_cert = build_certificate(
        _manifest(["j0", "j1"], n_pop=20),
        j_verdicts,
        0.60,
        PROTOCOL,
        "human",
        verifier_kind="judge",
    )
    assert j_cert["complete"] is True
    assert j_cert["n"] == 2


def test_judge_stratum_requires_model_and_human_adjudicator():
    ids = ["j0"]
    verdicts = [_judge_verdict("j0", False, model="")]
    cert = build_certificate(
        _manifest(ids, n_pop=5),
        verdicts,
        0.60,
        "judge.protocol.v0",
        "human",
        verifier_kind="judge",
    )
    assert cert["complete"] is False
    assert "judge_model" in cert["unadjudicated_reasons"]["j0"]

    with pytest.raises(ValueError, match="machine"):
        build_certificate(
            _manifest(ids, n_pop=5),
            [_judge_verdict("j0", False)],
            0.60,
            "judge.protocol.v0",
            "machine",
            verifier_kind="judge",
        )

    with pytest.raises(ValueError, match="verifier_kind"):
        build_certificate(
            _manifest(ids, n_pop=5),
            [_verdict("j0", False)],
            0.60,
            PROTOCOL,
            "human",
            verifier_kind="bogus",
        )


def test_infer_verifier_kind_mixed_raises(tmp_path: Path):
    ids = ["e0", "j0"]
    manifest = _manifest(ids, n_pop=10)
    exec_row = _verdict("e0", False)
    exec_row["verifier_kind"] = "execution"
    verdicts = [exec_row, _judge_verdict("j0", False, protocol=PROTOCOL)]
    mpath = tmp_path / "m.json"
    vpath = tmp_path / "v.jsonl"
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    vpath.write_text(
        "\n".join(json.dumps(v) for v in verdicts) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="mix verifier_kind"):
        main(
            [
                "--manifest",
                str(mpath),
                "--verdicts",
                str(vpath),
                "--protocol",
                PROTOCOL,
                "--adjudicator",
                "human",
            ]
        )


def test_verifier_kind_none_stratum():
    ids = ["n0", "n1"]
    verdicts = []
    for uid in ids:
        row = _verdict(uid, False, adjudicator="human")
        row["verifier_kind"] = "none"
        verdicts.append(row)
    cert = build_certificate(
        _manifest(ids, n_pop=2),
        verdicts,
        0.05,
        PROTOCOL,
        "human",
        verifier_kind="none",
    )
    assert cert["complete"] is True
    assert cert["verifier_kind"] == "none"
    assert cert["judge_model"] is None
    assert cert["judge_agreement"] is None
    assert cert["strata"] == {"none": 2}
