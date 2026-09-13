"""OpenAI-compatible judge shim backed by `devin -p` headless (doc 51).

A minimal HTTP server that answers the two endpoints the Harbor-Index judge
verifiers call through the OpenAI SDK (tests/native_judge.py in every judge
task): POST /v1/responses first, then POST /v1/chat/completions as the SDK
fallback. Each request's messages are assembled into a plain prompt and
answered by `devin --model swe-2-max -p` running in a scratch cwd with no
repo. The returned text is served as the completion.

Every request and its response (or error) is appended as one JSONL row to
data/gold/judge_shim_log.jsonl, carrying a sha256 of the assembled prompt.

Verifier containers run on per-trial docker-compose bridge networks
(<task>__<id>__verifier__trial_default). They reach this host-bound server at
the docker0 host address 172.17.0.1, which is a local address on the host
reachable from any bridge-networked container (verified from a probe
container, doc 51). Bind is 0.0.0.0 on a fixed port.

If a verifier ignored OPENAI_BASE_URL it would hit api.openai.com with the
dummy key and fail. The swap runner additionally flags any trial that
produced LLM-judged verdicts while the shim saw zero requests
(status=shim_bypassed), so a base-URL-ignoring verifier fails loudly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

DEFAULT_PORT = 8477
# docker0 host address: a local address on the host, reachable from any
# bridge-networked container regardless of that container's subnet.
DEFAULT_HOST_ADDR = "172.17.0.1"
DEFAULT_LOG = Path("data/gold/judge_shim_log.jsonl")
DEFAULT_SCRATCH = Path("/tmp/judge-shim-scratch")
DEFAULT_DEVIN_MODEL = "swe-2-max"
DEFAULT_DEVIN_TIMEOUT_SEC = 480.0

Responder = Callable[[str, str], dict]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_text(content: Any) -> str:
    """Flatten an OpenAI message content value to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def messages_from_chat(payload: dict) -> list[dict]:
    """messages list from a /chat/completions body."""
    out: list[dict] = []
    for msg in payload.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        out.append(
            {
                "role": str(msg.get("role") or "user"),
                "content": content_text(msg.get("content")),
            }
        )
    return out


def messages_from_responses(payload: dict) -> list[dict]:
    """Message list from a /responses body. input is a string or item list."""
    inp = payload.get("input")
    if isinstance(inp, str):
        return [{"role": "user", "content": inp}]
    out: list[dict] = []
    for item in inp or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") in (None, "message") or "role" in item:
            out.append(
                {
                    "role": str(item.get("role") or "user"),
                    "content": content_text(item.get("content")),
                }
            )
    return out


def assemble_prompt(messages: list[dict]) -> str:
    """Role-tagged transcript handed to devin as the prompt."""
    return "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages)


def invoke_devin(
    prompt: str,
    *,
    model: str = DEFAULT_DEVIN_MODEL,
    scratch_root: Path = DEFAULT_SCRATCH,
    timeout_sec: float = DEFAULT_DEVIN_TIMEOUT_SEC,
    devin_bin: str = "devin",
    environ: dict | None = None,
) -> dict:
    """Run `devin --model <model> -p` headless in a scratch dir with no repo.

    The prompt goes via --prompt-file so judge prompts of any size never hit
    argv limits. --respect-workspace-trust false is required: print mode
    cannot show the trust prompt and fails in an untrusted directory.
    """
    scratch_root = Path(scratch_root)
    scratch_root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="req-", dir=scratch_root))
    t0 = time.monotonic()
    try:
        (scratch / "prompt.txt").write_text(prompt, encoding="utf-8")
        cmd = [
            devin_bin,
            "--model",
            model,
            "--respect-workspace-trust",
            "false",
            "-p",
            "--prompt-file",
            "prompt.txt",
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=scratch,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                env=environ,
            )
            elapsed = time.monotonic() - t0
            return {
                "text": proc.stdout.strip(),
                "elapsed_sec": elapsed,
                "returncode": proc.returncode,
                "stderr_tail": (proc.stderr or "")[-2000:],
                "error": None if proc.returncode == 0 else f"devin_rc_{proc.returncode}",
            }
        except subprocess.TimeoutExpired:
            return {
                "text": "",
                "elapsed_sec": time.monotonic() - t0,
                "returncode": None,
                "stderr_tail": "",
                "error": f"devin_timeout_{timeout_sec}s",
            }
        except OSError as exc:
            return {
                "text": "",
                "elapsed_sec": time.monotonic() - t0,
                "returncode": None,
                "stderr_tail": "",
                "error": f"{type(exc).__name__}: {exc}",
            }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


@dataclass
class ShimConfig:
    port: int = DEFAULT_PORT
    host_addr: str = DEFAULT_HOST_ADDR
    log_path: Path = DEFAULT_LOG
    scratch_root: Path = DEFAULT_SCRATCH
    devin_model: str = DEFAULT_DEVIN_MODEL
    devin_timeout_sec: float = DEFAULT_DEVIN_TIMEOUT_SEC
    devin_bin: str = "devin"
    max_concurrent: int = 1
    responder: Responder | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host_addr}:{self.port}/v1"

    def default_responder(self) -> Responder:
        def _respond(prompt: str, model: str) -> dict:
            return invoke_devin(
                prompt,
                model=self.devin_model,
                scratch_root=self.scratch_root,
                timeout_sec=self.devin_timeout_sec,
                devin_bin=self.devin_bin,
            )

        return _respond


class _ShimState:
    def __init__(self, config: ShimConfig):
        self.config = config
        self.seq = 0
        self.seq_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.devin_semaphore = threading.Semaphore(max(1, config.max_concurrent))
        self.responder = config.responder or config.default_responder()

    def next_seq(self) -> int:
        with self.seq_lock:
            self.seq += 1
            return self.seq

    def append_log(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self.log_lock:
            path = Path(self.config.log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def _error_body(message: str, err_type: str = "judge_shim_error") -> bytes:
    return json.dumps(
        {"error": {"message": message, "type": err_type, "code": None}}
    ).encode("utf-8")


def _chat_body(seq: int, model: str, text: str) -> bytes:
    return json.dumps(
        {
            "id": f"chatcmpl-jshim-{seq}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
    ).encode("utf-8")


def _responses_body(seq: int, model: str, text: str) -> bytes:
    now = int(time.time())
    return json.dumps(
        {
            "id": f"resp-jshim-{seq}",
            "object": "response",
            "created_at": now,
            "completed_at": now,
            "status": "completed",
            "model": model,
            "output": [
                {
                    "id": f"msg-jshim-{seq}",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": text, "annotations": []}
                    ],
                }
            ],
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
    ).encode("utf-8")


def endpoint_for_path(path: str) -> str | None:
    clean = path.split("?", 1)[0].rstrip("/")
    if clean.endswith("/chat/completions"):
        return "chat_completions"
    if clean.endswith("/responses"):
        return "responses"
    return None


class JudgeShimHandler(BaseHTTPRequestHandler):
    server: "_JudgeHTTPServer"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(
            f"[judge_shim] {self.address_string()} {fmt % args}\n"
        )

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("", "/health", "/v1/models"):
            body = json.dumps(
                {
                    "status": "ok",
                    "requests": self.server.state.seq,
                    "base_url": self.server.state.config.base_url,
                    "model": self.server.state.config.devin_model,
                }
            ).encode("utf-8")
            self._send(200, body)
            return
        self._send(404, _error_body(f"unknown path {path}", "not_found"))

    def do_POST(self) -> None:
        state = self.server.state
        seq = state.next_seq()
        ts = _utc_now()
        path = self.path.split("?", 1)[0]
        kind = endpoint_for_path(path)
        record: dict[str, Any] = {
            "seq": seq,
            "ts": ts,
            "method": "POST",
            "path": path,
            "endpoint": kind,
        }
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError as exc:
            record.update({"status": 400, "error": f"bad_json: {exc}"})
            state.append_log(record)
            self._send(400, _error_body(f"invalid JSON body: {exc}", "invalid_request"))
            return
        if kind is None:
            record.update({"status": 404, "error": "unknown_endpoint"})
            state.append_log(record)
            self._send(404, _error_body(f"unknown endpoint {path}", "not_found"))
            return

        model = str(payload.get("model") or "")
        if kind == "chat_completions":
            messages = messages_from_chat(payload)
        else:
            messages = messages_from_responses(payload)
        prompt = assemble_prompt(messages)
        record.update(
            {
                "model": model,
                "n_messages": len(messages),
                "prompt_chars": len(prompt),
                "prompt_sha256": _sha256(prompt),
            }
        )

        with state.devin_semaphore:
            result = state.responder(prompt, model)
        text = str(result.get("text") or "")
        error = result.get("error")
        if not error and not text:
            error = "devin_empty_response"
        record["elapsed_sec"] = result.get("elapsed_sec")
        record["devin_returncode"] = result.get("returncode")
        if result.get("stderr_tail"):
            record["devin_stderr_tail"] = str(result["stderr_tail"])[-500:]
        if error:
            record.update({"status": 502, "error": str(error)})
            state.append_log(record)
            self._send(
                502,
                _error_body(f"judge shim backend failed: {error}"),
            )
            return

        record.update(
            {
                "status": 200,
                "response_chars": len(text),
                "response_sha256": _sha256(text),
                "error": None,
            }
        )
        state.append_log(record)
        if kind == "responses":
            body = _responses_body(seq, model, text)
        else:
            body = _chat_body(seq, model, text)
        self._send(200, body)


class _JudgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr: tuple[str, int], config: ShimConfig):
        self.state = _ShimState(config)
        super().__init__(addr, JudgeShimHandler)


def make_server(config: ShimConfig) -> _JudgeHTTPServer:
    """Bind on 0.0.0.0 so verifier containers on any bridge net can reach it."""
    return _JudgeHTTPServer(("0.0.0.0", config.port), config)


def serve_in_thread(config: ShimConfig) -> tuple[_JudgeHTTPServer, threading.Thread]:
    server = make_server(config)
    thread = threading.Thread(target=server.serve_forever, name="judge-shim", daemon=True)
    thread.start()
    return server, thread


def count_shim_requests(log_path: Path) -> int:
    """Judge-call rows (chat_completions/responses) currently in the log."""
    path = Path(log_path)
    if not path.is_file():
        return 0
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("endpoint") in ("chat_completions", "responses"):
                n += 1
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--host-addr", default=DEFAULT_HOST_ADDR)
    p.add_argument("--log", type=Path, default=DEFAULT_LOG)
    p.add_argument("--scratch", type=Path, default=DEFAULT_SCRATCH)
    p.add_argument("--devin-model", default=DEFAULT_DEVIN_MODEL)
    p.add_argument("--devin-timeout-sec", type=float, default=DEFAULT_DEVIN_TIMEOUT_SEC)
    p.add_argument("--devin-bin", default="devin")
    p.add_argument("--max-concurrent", type=int, default=1)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ShimConfig(
        port=args.port,
        host_addr=args.host_addr,
        log_path=args.log,
        scratch_root=args.scratch,
        devin_model=args.devin_model,
        devin_timeout_sec=args.devin_timeout_sec,
        devin_bin=args.devin_bin,
        max_concurrent=args.max_concurrent,
    )
    server = make_server(config)
    print(
        f"[judge_shim] listening on 0.0.0.0:{config.port} "
        f"base_url={config.base_url} log={config.log_path} "
        f"devin_model={config.devin_model}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
