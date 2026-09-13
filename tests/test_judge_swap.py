"""Fixture tests for the judge shim and judge-swap runner. No network."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from task_validation.evidence.judge_shim import (
    ShimConfig,
    assemble_prompt,
    content_text,
    count_shim_requests,
    endpoint_for_path,
    messages_from_chat,
    messages_from_responses,
    serve_in_thread,
)
from task_validation.evidence.judge_swap import (
    SWAP_GRADE,
    SWAP_JUDGE_MODEL,
    SWAP_PROTOCOL,
    SWAP_VERIFIER_KIND,
    build_swap_row,
    details_imply_llm_calls,
    run_key,
    summarize_swap,
    swap_verifier_env,
    verdict_sha256,
)
from task_validation.evidence.judge_verifier import provider_for_model
from task_validation.sampling.certificate import build_certificate


def test_content_text_variants():
    assert content_text("abc") == "abc"
    assert content_text(None) == ""
    assert content_text([{"type": "input_text", "text": "a"}, {"type": "input_text", "text": "b"}]) == "a\nb"
    assert content_text(["x", {"type": "output_text", "text": "y"}, {"type": "refusal"}]) == "x\ny"


def test_messages_from_chat():
    payload = {
        "model": "devin-swe2max",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        ],
    }
    msgs = messages_from_chat(payload)
    assert msgs == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]


def test_messages_from_responses_string_and_items():
    assert messages_from_responses({"input": "just text"}) == [
        {"role": "user", "content": "just text"}
    ]
    payload = {
        "input": [
            {"type": "message", "role": "system", "content": [{"type": "input_text", "text": "s"}]},
            {"role": "user", "content": [{"type": "input_text", "text": "u"}]},
        ]
    }
    msgs = messages_from_responses(payload)
    assert msgs == [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def test_assemble_prompt_role_tags():
    prompt = assemble_prompt(
        [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    )
    assert prompt == "[system]\nS\n\n[user]\nU"


def test_endpoint_for_path():
    assert endpoint_for_path("/v1/chat/completions") == "chat_completions"
    assert endpoint_for_path("/v1/responses") == "responses"
    assert endpoint_for_path("/v1/responses/") == "responses"
    assert endpoint_for_path("/v1/messages") is None
    assert endpoint_for_path("/health") is None


def _echo_responder(prompt: str, model: str) -> dict:
    return {
        "text": f"echo:{model}:{prompt[:40]}",
        "elapsed_sec": 0.01,
        "returncode": 0,
        "stderr_tail": "",
        "error": None,
    }


def test_shim_http_endpoints_and_log(tmp_path: Path):
    log = tmp_path / "shim_log.jsonl"
    cfg = ShimConfig(port=0, log_path=log, responder=_echo_responder)
    server, _t = serve_in_thread(cfg)
    try:
        port = server.server_address[1]
        body = json.dumps(
            {
                "model": "devin-swe2max",
                "messages": [{"role": "user", "content": "judge this"}],
            }
        ).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        assert resp["object"] == "chat.completion"
        assert resp["choices"][0]["message"]["content"].startswith("echo:devin-swe2max:")
        assert "[user]\njudge this" in resp["choices"][0]["message"]["content"]

        body2 = json.dumps(
            {
                "model": "devin-swe2max",
                "input": [{"role": "user", "content": [{"type": "input_text", "text": "rank"}]}],
            }
        ).encode()
        req2 = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/responses",
            data=body2,
            headers={"Content-Type": "application/json"},
        )
        resp2 = json.loads(urllib.request.urlopen(req2, timeout=10).read())
        assert resp2["status"] == "completed"
        assert resp2["output"][0]["content"][0]["type"] == "output_text"
        assert "rank" in resp2["output"][0]["content"][0]["text"]

        req3 = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/messages", data=b"{}", method="POST"
        )
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req3, timeout=10)
        assert err.value.code == 404
    finally:
        server.shutdown()
        server.server_close()

    rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    judge_rows = [r for r in rows if r.get("endpoint")]
    assert len(judge_rows) == 2
    assert {r["endpoint"] for r in judge_rows} == {"chat_completions", "responses"}
    for r in judge_rows:
        assert r["status"] == 200
        assert len(r["prompt_sha256"]) == 64
        assert r["prompt_chars"] > 0
        assert r["model"] == "devin-swe2max"
        assert len(r["response_sha256"]) == 64
    assert any(r.get("error") == "unknown_endpoint" for r in rows)
    assert count_shim_requests(log) == 2


def test_shim_backend_error_is_loud(tmp_path: Path):
    def _bad(prompt: str, model: str) -> dict:
        return {"text": "", "elapsed_sec": 0.0, "returncode": 1, "error": "devin_rc_1"}

    cfg = ShimConfig(port=0, log_path=tmp_path / "l.jsonl", responder=_bad)
    server, _t = serve_in_thread(cfg)
    try:
        port = server.server_address[1]
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=json.dumps({"model": "m", "messages": []}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=10)
        assert err.value.code == 502
    finally:
        server.shutdown()
        server.server_close()
    rows = [json.loads(l) for l in (tmp_path / "l.jsonl").read_text().splitlines()]
    assert rows[0]["status"] == 502
    assert rows[0]["error"] == "devin_rc_1"


def test_swap_env_routes_openai():
    env = swap_verifier_env("http://172.17.0.1:8477/v1")
    assert env["JUDGE_MODELS"] == SWAP_JUDGE_MODEL
    assert env["OPENAI_API_KEY"].startswith("sk-")
    assert env["OPENAI_BASE_URL"] == "http://172.17.0.1:8477/v1"
    assert env["JUDGE_REPEATS"] == "1"
    assert env["JUDGE_CONCURRENCY"] == "1"
    assert provider_for_model(env["JUDGE_MODELS"]) == "openai"


def test_details_imply_llm_calls():
    hle_details = {
        "judgment.json": {
            "runs": [
                {
                    "model": "devin-swe2max",
                    "reward": 1.0,
                    "details": {"model_answer": "x", "reasoning": "y", "correct": "yes"},
                }
            ]
        }
    }
    assert details_imply_llm_calls(hle_details) is True

    gaia2_det = {
        "gaia2_cli_result.json": {
            "runs": [
                {"model": "devin-swe2max", "reward": 1.0,
                 "details": {"result_type": "exact_normalized", "reward": 1.0}}
            ]
        }
    }
    assert details_imply_llm_calls(gaia2_det) is False

    gaia2_llm = {
        "gaia2_cli_result.json": {
            "runs": [
                {"model": "m", "reward": 0.0,
                 "details": {
                     "matched_pairs": [{"reason": "Reasoning: semantic match. Evaluation: [[Match]]"}],
                     "unmatched_details": [],
                 }}
            ]
        }
    }
    assert details_imply_llm_calls(gaia2_llm) is True

    gaia2_det_only = {
        "gaia2_cli_result.json": {
            "runs": [
                {"model": "m", "reward": 0.0,
                 "details": {
                     "matched_pairs": [],
                     "unmatched_details": [
                         "oracle[0] Tool vs agent[1] rejected: Missing required agent args: ['x']"
                     ],
                 }}
            ]
        }
    }
    assert details_imply_llm_calls(gaia2_det_only) is False
    assert details_imply_llm_calls({}) is False


def test_verdict_sha256_stability():
    assert verdict_sha256({}) is None
    a = verdict_sha256({"f.json": {"reward": 1.0, "runs": [{"model": "m"}]}})
    b = verdict_sha256({"f.json": {"runs": [{"model": "m"}], "reward": 1.0}})
    assert a == b and a and len(a) == 64


def _shim_row(seq: int, status: int = 200, elapsed: float = 1.5) -> dict:
    return {
        "seq": seq,
        "endpoint": "responses",
        "status": status,
        "elapsed_sec": elapsed,
        "prompt_sha256": "ab" * 32,
    }


def test_build_swap_row_schema():
    row = build_swap_row(
        task_id="hle-x",
        src="hle",
        probe="oracle",
        rep=0,
        reward=1.0,
        status="executed",
        elapsed_sec=12.5,
        details={"judgment.json": {"runs": [{"model": "m", "reward": 1.0, "details": {"reasoning": "r"}}]}},
        shim_rows_new=[_shim_row(1), _shim_row(2, status=502)],
        shim_rows_before=0,
        memory_mb=2048,
        test_stdout_tail="",
        job_name="jswap-hle-x-oracle-0-t",
        path="/p",
        base_url="http://172.17.0.1:8477/v1",
    )
    assert row["label_protocol"] == SWAP_PROTOCOL
    assert row["grade"] == SWAP_GRADE == "B"
    assert row["verifier_kind"] == SWAP_VERIFIER_KIND == "judge_swap"
    assert row["judge_model"] == "devin-swe2max"
    assert row["accepted"] is True
    assert row["intended"] == "accept"
    assert row["shim_requests"] == 2
    assert row["shim_request_errors"] == 1
    assert row["shim_elapsed_sec"] == 3.0
    assert row["status"] == "executed"
    assert row["judge_llm_evidence"] is True
    assert row["verdict_sha256"]
    assert row["judge_runs"][0]["model"] == "m"


def test_build_swap_row_nop_and_bypass():
    nop = build_swap_row(
        task_id="hle-x", src="hle", probe="nop", rep=1, reward=0.0,
        status="executed", elapsed_sec=3.0, details=None, shim_rows_new=[],
        shim_rows_before=5, memory_mb=2048, test_stdout_tail="",
    )
    assert nop["intended"] == "reject"
    assert nop["accepted"] is False
    assert nop["status"] == "executed"  # no LLM evidence, zero shim calls is legitimate

    bypassed = build_swap_row(
        task_id="hle-x", src="hle", probe="oracle", rep=0, reward=1.0,
        status="executed", elapsed_sec=3.0,
        details={"judgment.json": {"runs": [{"model": "m", "reward": 1.0, "details": {"reasoning": "r"}}]}},
        shim_rows_new=[], shim_rows_before=0, memory_mb=2048, test_stdout_tail="",
    )
    assert bypassed["status"] == "shim_bypassed"
    assert bypassed["reward"] == 1.0  # kept for forensics

    failed = build_swap_row(
        task_id="hle-x", src="hle", probe="oracle", rep=0, reward=0.0,
        status="infra", elapsed_sec=3.0, details=None, shim_rows_new=[],
        shim_rows_before=0, memory_mb=2048, test_stdout_tail="",
    )
    assert failed["reward"] is None


def test_run_key_and_summarize():
    row = build_swap_row(
        task_id="t", src="s", probe="nop", rep=2, reward=0.0, status="executed",
        elapsed_sec=1.0, details=None, shim_rows_new=[], shim_rows_before=0,
        memory_mb=None, test_stdout_tail="",
    )
    assert run_key(row) == ("t", "nop", 2)
    summary = summarize_swap([row], wall_clock_total=5.0, n_judge_tasks=16)
    assert summary["protocol"] == SWAP_PROTOCOL
    assert summary["verifier_kind"] == "judge_swap"
    assert summary["grade"] == "B"
    assert summary["n_runs"] == 1
    assert summary["tasks"]["t"]["nop"]["rewards"] == [0.0]
    assert summary["tasks"]["t"]["reference"]["runs"] == 0


def _manifest() -> dict:
    return {"ids": ["t1"], "n": 1, "N": 10, "design": "SRS", "seed": "s"}


def _swap_verdict() -> dict:
    return {
        "unit_id": "t1",
        "invalid": False,
        "label_protocol": SWAP_PROTOCOL,
        "grade": "B",
        "verifier_kind": "judge_swap",
        "adjudicator": "machine",
        "evidence": "judge-swap diagnostic",
    }


def test_certificate_rejects_judge_swap_under_execution():
    with pytest.raises(ValueError, match="judge_swap"):
        build_certificate(
            _manifest(),
            [_swap_verdict()],
            0.05,
            SWAP_PROTOCOL,
            "machine",
            verifier_kind="execution",
        )


def test_certificate_rejects_judge_swap_under_judge():
    with pytest.raises(ValueError, match="judge_swap"):
        build_certificate(
            _manifest(),
            [_swap_verdict()],
            0.05,
            SWAP_PROTOCOL,
            "human",
            verifier_kind="judge",
        )


def test_certificate_still_accepts_execution_rows():
    cert = build_certificate(
        _manifest(),
        [
            {
                "unit_id": "t1",
                "invalid": False,
                "label_protocol": "verifier_invalid.fresh_environment.execution",
                "grade": "A",
                "adjudicator": "machine",
            }
        ],
        0.05,
        "verifier_invalid.fresh_environment.execution",
        "machine",
        verifier_kind="execution",
    )
    assert cert["complete"] is True
    assert cert["verifier_kind"] == "execution"
