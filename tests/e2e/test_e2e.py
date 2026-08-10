# SPDX-License-Identifier: Apache-2.0

"""Native MCP-protocol e2e: spawn the REAL server binary and speak JSON-RPC
over stdio (initialize -> tools/list -> tools/call). This tests the server as
an MCP client sees it — not the Python functions directly."""

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
_VENV_PY = ROOT / ".venv/bin/python"
# Prefer the repo venv (local dev), fall back to the running interpreter (CI).
SERVER_CMD = [str(_VENV_PY if _VENV_PY.exists() else Path(sys.executable)), "-m", "papers_mcp"]

pytestmark = pytest.mark.e2e

OPT_OUT_VARS = ("FIND_RESEARCH_PAPERS_MCP_TELEMETRY", "DISABLE_TELEMETRY", "DO_NOT_TRACK", "NO_TELEMETRY")


class CaptureServer:
    """Local stand-in for the Cloudflare gateway: records every telemetry
    POST so tests can assert what actually left the server."""

    def __init__(self):
        self.payloads = []
        self.requests = []
        lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # type: ignore[override]
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                with lock:
                    self.server.payloads.append(json.loads(body))  # type: ignore[attr-defined]
                    self.server.requests.append(dict(self.headers))  # type: ignore[attr-defined]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"recorded":true}')

            def log_message(self, *args):  # type: ignore[override]
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.payloads = self.payloads  # type: ignore[attr-defined]
        self.httpd.requests = self.requests  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_port}/e"

    def event_names(self):
        return [p["event"] for p in self.payloads]

    def wait_for_events(self, names, timeout=25):
        want = set(names)
        end = time.time() + timeout
        while time.time() < end:
            if want <= set(self.event_names()):
                return True
            time.sleep(0.2)
        return False

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _server_env(env_extra=None, telemetry_url=None):
    env = {k: "" for k in OPT_OUT_VARS}
    env.update(os.environ)
    env_extra = env_extra or {}
    env.update(env_extra)
    if "FIND_RESEARCH_PAPERS_MCP_TELEMETRY" not in env_extra:
        env.pop("FIND_RESEARCH_PAPERS_MCP_TELEMETRY", None)
    if telemetry_url is not None:
        env["FIND_RESEARCH_PAPERS_MCP_TELEMETRY_URL"] = telemetry_url
    return env


class MCPStdioClient:
    """Minimal JSON-RPC client that matches response IDs (pendingResolve must
    check resp.id === requestId, else responses from one call pollute another)."""

    def __init__(self, env_extra=None, telemetry_url=None):
        self.proc = subprocess.Popen(
            SERVER_CMD,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            env=_server_env(env_extra, telemetry_url),
        )
        self._next_id = 0

    def request(self, method, params=None, timeout=60):
        self._next_id += 1
        req_id = self._next_id
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"server closed: {self.proc.stderr.read()}")
            resp = json.loads(line)
            if resp.get("id") == req_id:  # id matching is mandatory
                return resp

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def handshake(self, capabilities=None):
        init = self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": capabilities if capabilities is not None else {},
            "clientInfo": {"name": "e2e-test", "version": "0.0.1"},
        })
        self.notify("notifications/initialized")
        return init

    def request_full(self, method, params=None, timeout=60,
                     request_handler=None):
        """Like request(), but also captures server->client notifications and
        answers server->client REQUESTS (e.g. elicitation/create) via
        request_handler(method, params) -> result dict.

        Returns (response, notifications)."""
        self._next_id += 1
        req_id = self._next_id
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        notifications = []
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"server closed: {self.proc.stderr.read()}")
            resp = json.loads(line)
            if "method" in resp and "id" in resp:  # server-initiated request
                if request_handler is not None:
                    result = request_handler(resp["method"],
                                             resp.get("params") or {})
                    self.proc.stdin.write(json.dumps({
                        "jsonrpc": "2.0", "id": resp["id"], "result": result,
                    }) + "\n")
                    self.proc.stdin.flush()
                continue
            if "method" in resp:  # notification
                notifications.append(resp)
                continue
            if resp.get("id") == req_id:
                return resp, notifications

    def shutdown(self, timeout=15):
        """Graceful exit: close stdin so the stdio loop ends and the process
        exits normally — atexit hooks (session_end) only run on this path."""
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.close()

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def parse_tool_text(result: dict) -> str:
    """MCP 2025-06-18 tools/call: content is a list of blocks; find text."""
    if result.get("structuredContent") is not None:
        return json.dumps(result["structuredContent"])
    for block in result.get("content", []):
        if block.get("type") == "text":
            return block["text"]
    return ""


def parse_result(result: dict) -> Any:
    """Unwrap a tools/call result to the tool's native return value.

    The MCP 2.x SDK returns list-typed tool results wrapped as
    {"result": [...]} in structuredContent while dict results pass through —
    normalize both, plus the text-block fallback."""
    if result.get("structuredContent") is not None:
        raw = result["structuredContent"]
    else:
        text = parse_tool_text(result)
        raw = json.loads(text) if text else None
    if isinstance(raw, dict) and list(raw.keys()) == ["result"]:
        return raw["result"]
    return raw


def test_initialize_and_list_tools():
    with MCPStdioClient() as c:
        init = c.handshake()
        assert init["result"]["serverInfo"]["name"] == "find-research-papers-mcp"
        assert "version" in init["result"]["serverInfo"]

        tools = c.request("tools/list")
        names = [t["name"] for t in tools["result"]["tools"]]
        assert names == ["search_papers", "get_paper", "get_research_method",
                         "list_sources", "skills_list", "skill_read"]


def test_list_sources_schema():
    with MCPStdioClient() as c:
        c.handshake()
        res = c.request("tools/call", {"name": "list_sources", "arguments": {}})
        assert "error" not in res
        sources = parse_result(res["result"])
        assert isinstance(sources, list) and len(sources) == 5
        for s in sources:
            for field in ("name", "display_name", "description", "coverage",
                          "rate_limit", "requires_key", "configured"):
                assert field in s, f"missing {field} in {s}"
        names = {s["name"] for s in sources}
        assert names == {"arxiv", "openalex", "crossref", "semanticscholar", "pubmed"}


def test_get_research_method_schema():
    with MCPStdioClient() as c:
        c.handshake()
        res = c.request("tools/call", {"name": "get_research_method",
                                       "arguments": {}})
        assert "error" not in res
        method = parse_result(res["result"])["method"]
        for field in ("tiers", "rules", "quirks", "verify_steps",
                      "retraction_note"):
            assert field in method, f"missing {field}"
        assert isinstance(method["tiers"], list) and method["tiers"]
        assert "verify_steps" in method and isinstance(method["verify_steps"], list)


def test_search_papers_aggregates_real_hits():
    with MCPStdioClient() as c:
        c.handshake()
        res = c.request("tools/call", {
            "name": "search_papers",
            "arguments": {"query": "attention is all you need", "limit": 3},
        })
        assert "error" not in res, res.get("error")
        data = parse_result(res["result"])
        assert "hits" in data and "skipped" in data
        assert len(data["hits"]) > 0, f"no hits; skipped={data['skipped']}"
        for hit in data["hits"]:
            # unified schema: guaranteed fields non-empty
            assert hit["id"], "hit missing id"
            assert hit["title"], "hit missing title"
            assert hit["url"], "hit missing url"
            assert hit["source"], "hit missing source"


def test_search_papers_validation():
    with MCPStdioClient() as c:
        c.handshake()
        res = c.request("tools/call", {
            "name": "search_papers",
            "arguments": {"query": "x", "sort": "bogus"},
        })
        assert res["result"].get("isError") is True


def test_get_paper_doi_references_and_citations():
    """Nature paper (AlphaFold2) via DOI: Crossref metadata + references, and
    the OpenAlex citations fallback — the paywalled-journal proof."""
    with MCPStdioClient() as c:
        c.handshake()
        res = c.request("tools/call", {
            "name": "get_paper",
            "arguments": {
                "identifier": "10.1038/s41586-020-2649-2",
                "id_type": "doi",
                "include_references": True,
                "include_citations": True,
            },
        }, timeout=90)
        assert "error" not in res, res.get("error")
        data = parse_result(res["result"])
        assert "error" not in data, data
        paper = data["paper"]
        assert paper["title"], "paper missing title"
        assert paper["doi"] == "10.1038/s41586-020-2649-2"
        assert paper["source"] == "crossref"
        assert len(data["references"]) > 0, "expected reference list from Crossref"
        assert len(data["citations"]) > 0, "expected OpenAlex citations fallback"


def test_get_paper_arxiv_and_auto_id():
    with MCPStdioClient() as c:
        c.handshake()
        res = c.request("tools/call", {
            "name": "get_paper",
            "arguments": {"identifier": "1706.03762", "include_citations": False},
        }, timeout=90)
        data = parse_result(res["result"])
        assert "error" not in data, data
        assert data["id_type"] == "arxiv"
        assert data["paper"]["source"] == "arxiv"
        assert "Attention" in data["paper"]["title"]


def test_get_paper_unknown_identifier():
    with MCPStdioClient() as c:
        c.handshake()
        res = c.request("tools/call", {
            "name": "get_paper",
            "arguments": {"identifier": "10.9999/does-not-exist-xyz", "id_type": "doi"},
        }, timeout=60)
        data = parse_result(res["result"])
        assert "error" in data  # graceful structured error, not a crash


def test_telemetry_events_flow(tmp_path):
    """Fresh install: boot + tool events reach the gateway, PII-free (SUR-86).
    Contract v2: schema_version 2, no launch_channel, tool_executed carries
    status/latency_ms/rows_returned/result_chars, tools_listed has tool_count."""
    capture = CaptureServer()
    try:
        with MCPStdioClient(env_extra={"HOME": str(tmp_path)}, telemetry_url=capture.url) as c:
            c.handshake()
            c.request("tools/list")
            c.request("tools/call", {"name": "list_sources", "arguments": {}})
            assert capture.wait_for_events([
                "server_first_install", "package_download", "mcp_started",
                "tools_listed", "tool_executed", "tool_list_sources",
            ]), f"missing events, saw: {capture.event_names()}"

            blob = json.dumps(capture.payloads)
            for payload in capture.payloads:
                props = payload["properties"]
                assert payload["event"] in ("server_first_install", "package_download",
                                            "mcp_started", "tools_listed", "tool_executed",
                                            "tool_list_sources", "session_end")
                assert props["mcp_server_name"] == "find-research-papers-mcp"
                assert props.get("session_id", "").startswith("sess_")
                assert props.get("schema_version") == 2
                assert "launch_channel" not in props, "v2 envelope must drop launch_channel"

            listed = [p for p in capture.payloads if p["event"] == "tools_listed"]
            assert listed and listed[0]["properties"]["tool_count"] == 6

            executed = [p for p in capture.payloads if p["event"] == "tool_executed"]
            assert executed, "tool_executed missing"
            ex = executed[0]["properties"]
            assert ex["tool_name"] == "list_sources"
            assert ex["status"] == "success"
            assert isinstance(ex["latency_ms"], int)
            assert ex["rows_returned"] == 5  # five sources
            assert isinstance(ex["result_chars"], int) and ex["result_chars"] > 0
            # per-request dual-era client capture (legacy handshake era here)
            assert ex.get("mcp_client_name") == "e2e-test"
            assert ex.get("mcp_client_version") == "0.0.1"

            # zero PII / no local paths (SUR-86 #5, SUR-259 telemetry assertions)
            assert str(tmp_path) not in blob, "local path leaked into telemetry"
            assert "Users/" not in blob, "home path leaked into telemetry"
            assert "127.0.0.1" not in blob, "gateway URL leaked into telemetry"
            assert "reachsuren@" not in blob, "contact email leaked"
    finally:
        capture.close()


def test_failure_telemetry_error_and_exception(tmp_path):
    """The v2 headline: errors and exceptions are no longer invisible.
    Error-shaped result -> status=error; raised exception -> status=exception;
    both carry the taxonomy. Offline (no upstream API is hit)."""
    capture = CaptureServer()
    try:
        with MCPStdioClient(env_extra={"HOME": str(tmp_path)}, telemetry_url=capture.url) as c:
            c.handshake()
            # error-shaped result dict (unknown id_type short-circuits offline)
            # — carries intent, which must arrive verbatim in tool_executed
            res = c.request("tools/call", {
                "name": "get_paper",
                "arguments": {"identifier": "whatever", "id_type": "bogus",
                              "intent": "check if this paper was retracted "
                                        "before citing it"},
            })
            assert "error" in parse_result(res["result"])
            # raised exception (sort validation)
            res = c.request("tools/call", {
                "name": "search_papers",
                "arguments": {"query": "x", "sort": "bogus"},
            })
            assert res["result"].get("isError") is True

            assert capture.wait_for_events(["tool_executed", "tool_get_paper",
                                            "tool_search"]), capture.event_names()
            executed = {p["properties"]["tool_name"]: p["properties"]
                        for p in capture.payloads if p["event"] == "tool_executed"}

            err = executed["get_paper"]
            assert err["status"] == "error"
            assert err["error_category"] == "ValidationError"
            assert "unknown id_type" in err["error_message"]
            assert err["rows_returned"] == 0
            assert isinstance(err["latency_ms"], int)
            # intent-bearing call: captured VERBATIM (no truncation/bucketing)
            assert err["intent"] == ("check if this paper was retracted "
                                     "before citing it")

            exc = executed["search_papers"]
            assert exc["status"] == "exception"
            assert exc["error_category"] == "ValidationError"
            assert "sort must be one of" in exc["error_message"]
            assert exc["rows_returned"] == 0
            # no intent passed -> property must be absent, not null/empty
            assert "intent" not in exc

            # domain events now fire on failure paths too, with a status prop
            gp = [p["properties"] for p in capture.payloads if p["event"] == "tool_get_paper"]
            assert gp and gp[0]["status"] == "error"
            ts = [p["properties"] for p in capture.payloads if p["event"] == "tool_search"]
            assert ts and ts[0]["status"] == "exception"
    finally:
        capture.close()


def test_session_end(tmp_path):
    """Graceful exit emits session_end with duration, tool sequence/counts."""
    capture = CaptureServer()
    try:
        c = MCPStdioClient(env_extra={"HOME": str(tmp_path)}, telemetry_url=capture.url)
        try:
            c.handshake()
            c.request("tools/call", {"name": "get_research_method", "arguments": {}})
            c.request("tools/call", {"name": "get_research_method", "arguments": {}})
            c.shutdown()
            assert capture.wait_for_events(["session_end"]), capture.event_names()
            props = [p for p in capture.payloads if p["event"] == "session_end"][0]["properties"]
            assert isinstance(props["session_duration_s"], int)
            assert props["tool_sequence"] == ["get_research_method", "get_research_method"]
            assert props["tool_counts"] == {"get_research_method": 2}
            assert props["calls_total"] == 2
        finally:
            c.close()
    finally:
        capture.close()


def test_per_request_meta_client_capture(tmp_path):
    """2026-era per-request _meta clientInfo must win over the stored
    initialize handshake. (The SDK rejects the protocolVersion _meta key on a
    handshake-era connection with -32600 — era separation is SDK-enforced —
    so only the clientInfo key is exercised here.)"""
    capture = CaptureServer()
    try:
        with MCPStdioClient(env_extra={"HOME": str(tmp_path)}, telemetry_url=capture.url) as c:
            c.handshake()  # handshake says e2e-test
            res = c.request("tools/call", {
                "name": "get_research_method", "arguments": {},
                "_meta": {
                    "io.modelcontextprotocol/clientInfo": {
                        "name": "meta-era-client", "version": "9.9.9"},
                },
            })
            assert "error" not in res, res.get("error")
            assert capture.wait_for_events(["tool_executed"]), capture.event_names()
            ex = [p["properties"] for p in capture.payloads
                  if p["event"] == "tool_executed"][0]
            assert ex.get("mcp_client_name") == "meta-era-client", \
                "per-request _meta clientInfo must override the handshake"
            assert ex.get("mcp_client_version") == "9.9.9"
            # protocol version falls back to the handshake era on this connection
            assert ex.get("mcp_protocol_version") == "2025-06-18"
    finally:
        capture.close()


def test_skills_list_and_read(tmp_path):
    """skills_list names the starter skill; skill_read returns its content
    (GitHub raw fetch with local-checkout fallback) and fires the skill_read
    event with skill_name + fetch_ok."""
    capture = CaptureServer()
    try:
        with MCPStdioClient(env_extra={"HOME": str(tmp_path)}, telemetry_url=capture.url) as c:
            c.handshake()
            res = c.request("tools/call", {"name": "skills_list", "arguments": {}})
            skills = parse_result(res["result"])["skills"]
            assert {"interpreting-errors"} == {s["name"] for s in skills}
            assert all(s["description"] for s in skills)

            res = c.request("tools/call", {
                "name": "skill_read",
                "arguments": {"name": "interpreting-errors"},
            }, timeout=30)
            data = parse_result(res["result"])
            assert "error" not in data, data
            assert data["name"] == "interpreting-errors"
            assert "search_papers" in data["content"]

            # unknown skill: graceful error, never a crash
            res = c.request("tools/call", {
                "name": "skill_read", "arguments": {"name": "no-such-skill"},
            })
            assert "not found" in parse_result(res["result"])["error"]

            assert capture.wait_for_events(["skill_read"]), capture.event_names()
            reads = [p["properties"] for p in capture.payloads if p["event"] == "skill_read"]
            assert any(r["skill_name"] == "interpreting-errors" and
                       isinstance(r["fetch_ok"], bool) for r in reads)
    finally:
        capture.close()


def test_telemetry_opt_out(tmp_path):
    """Opt-out env var: server boots and works, but nothing is sent — and no
    side effects either: no identity dir, no ~/.find_research_papers_mcp writes."""
    capture = CaptureServer()
    try:
        c = MCPStdioClient(env_extra={"HOME": str(tmp_path),
                                      "FIND_RESEARCH_PAPERS_MCP_TELEMETRY": "false"},
                           telemetry_url=capture.url)
        try:
            c.handshake()
            c.request("tools/list")
            c.request("tools/call", {"name": "list_sources", "arguments": {}})
            c.shutdown()  # graceful exit: session_end must ALSO be suppressed
            time.sleep(1)
            assert capture.payloads == [], f"expected no telemetry, got: {capture.event_names()}"
            assert not (tmp_path / ".find_research_papers_mcp").exists(), \
                "opt-out must gate identity-file creation, not just the send"
        finally:
            c.close()
    finally:
        capture.close()


@pytest.mark.parametrize("var", ["DISABLE_TELEMETRY", "DO_NOT_TRACK", "NO_TELEMETRY"])
def test_telemetry_opt_out_generic_vars(tmp_path, var):
    """Each generic opt-out var disables telemetry and all side effects."""
    capture = CaptureServer()
    try:
        with MCPStdioClient(env_extra={"HOME": str(tmp_path), var: "1"},
                            telemetry_url=capture.url) as c:
            c.handshake()
            c.request("tools/call", {"name": "get_research_method", "arguments": {}})
            time.sleep(2)
            assert capture.payloads == [], f"{var}=1: got {capture.event_names()}"
            assert not (tmp_path / ".find_research_papers_mcp").exists()
    finally:
        capture.close()


def test_first_run_disclosure(tmp_path):
    """First boot prints the telemetry disclosure before any event is sent."""
    capture = CaptureServer()
    try:
        env = _server_env(env_extra={"HOME": str(tmp_path)}, telemetry_url=capture.url)
        proc = subprocess.Popen(
            SERVER_CMD, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE,
            stdout=subprocess.PIPE, env=env, text=True,
        )
        time.sleep(4)
        proc.terminate()
        err = proc.communicate(timeout=5)[1]
        assert "find-research-papers-mcp collects anonymous usage telemetry" in err
        assert "FIND_RESEARCH_PAPERS_MCP_TELEMETRY=false" in err
    finally:
        capture.close()


# ---------------------------------------------------------------------------
# Protocol Surfaces v1 (S1-S9)
# ---------------------------------------------------------------------------

# Unroutable proxy: forces every upstream API call to fail fast and
# deterministically, while NO_PROXY keeps the local telemetry gateway
# reachable. Turns the live fan-out into an offline fixture.
PROXY_ENV = {
    "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
    "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
    "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
}


def test_serverinfo_polish():
    """S9: serverInfo carries the human title and websiteUrl (additive)."""
    with MCPStdioClient() as c:
        info = c.handshake()["result"]["serverInfo"]
        assert info["name"] == "find-research-papers-mcp"
        assert info["title"] == "Find Research Papers"
        assert info["websiteUrl"] == \
            "https://github.com/surendranb/find-research-papers-mcp"


def test_tool_annotations_and_output_schema():
    """S1: every tool is read-only + idempotent, openWorld only for tools
    hitting external APIs. S2: outputSchema on search_papers (new) and
    list_sources (pre-existing SDK auto-detection) only."""
    open_world = {"search_papers": True, "get_paper": True,
                  "get_research_method": False, "list_sources": False,
                  "skills_list": False, "skill_read": True}
    with MCPStdioClient() as c:
        c.handshake()
        tools = c.request("tools/list")["result"]["tools"]
        assert len(tools) == 6
        for t in tools:
            ann = t.get("annotations")
            assert ann, f"{t['name']} missing annotations"
            assert ann["readOnlyHint"] is True
            assert ann["idempotentHint"] is True
            assert ann["openWorldHint"] is open_world[t["name"]]
        with_schema = {t["name"] for t in tools if "outputSchema" in t}
        assert with_schema == {"search_papers", "list_sources"}
        sp = next(t for t in tools if t["name"] == "search_papers")
        assert "hits" in sp["outputSchema"]["properties"]


def test_search_papers_structured_content_matches_text():
    """S2 dual representation: text block unchanged (legacy clients), with
    structuredContent alongside carrying the same payload."""
    with MCPStdioClient() as c:
        c.handshake()
        res = c.request("tools/call", {
            "name": "search_papers",
            "arguments": {"query": "attention is all you need", "limit": 3},
        })["result"]
        text_blocks = [b for b in res["content"] if b["type"] == "text"]
        assert text_blocks, "text content must survive for legacy clients"
        assert res.get("structuredContent") is not None
        assert json.loads(text_blocks[0]["text"]) == res["structuredContent"]


def test_2026_era_stateless_request():
    """Dual-era: a 2026-era client (no initialize handshake, envelope in
    _meta) gets the same tool text a legacy-handshake client gets."""
    meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "era2026",
                                               "version": "1.0"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    with MCPStdioClient() as modern:
        res = modern.request("tools/call", {
            "name": "get_research_method", "arguments": {}, "_meta": meta})
        modern_text = parse_tool_text(res["result"])
    with MCPStdioClient() as legacy:
        legacy.handshake()
        res = legacy.request("tools/call", {"name": "get_research_method",
                                            "arguments": {}})
        legacy_text = parse_tool_text(res["result"])
    assert modern_text == legacy_text


def test_prompts_and_prompt_used_telemetry(tmp_path):
    """S6: the three workflow prompts are listed, render with arguments, and
    fire prompt_used (prompt_name, has_args)."""
    capture = CaptureServer()
    try:
        with MCPStdioClient(env_extra={"HOME": str(tmp_path)},
                            telemetry_url=capture.url) as c:
            c.handshake()
            prompts = c.request("prompts/list")["result"]["prompts"]
            names = {p["name"] for p in prompts}
            assert names == {"literature-review", "verify-before-citing",
                             "find-recent-work"}
            lit = next(p for p in prompts if p["name"] == "literature-review")
            args = {a["name"]: a.get("required", False)
                    for a in lit.get("arguments", [])}
            assert args == {"topic": True, "depth": False}

            got = c.request("prompts/get", {
                "name": "literature-review",
                "arguments": {"topic": "sleep and memory consolidation",
                              "depth": "quick"},
            })["result"]
            text = got["messages"][0]["content"]["text"]
            assert "sleep and memory consolidation" in text
            assert "intent" in text            # teaches the intent param
            assert "interpreting-errors" in text  # teaches the skills loop

            got = c.request("prompts/get", {"name": "find-recent-work"})
            assert got["result"]["messages"], got

            assert capture.wait_for_events(["prompt_used"]), \
                capture.event_names()
            used = [p["properties"] for p in capture.payloads
                    if p["event"] == "prompt_used"]
            assert {"literature-review", "find-recent-work"} <= \
                {u["prompt_name"] for u in used}
            by_name = {u["prompt_name"]: u for u in used}
            assert by_name["literature-review"]["has_args"] is True
            assert by_name["find-recent-work"]["has_args"] is False
    finally:
        capture.close()


def test_skill_resources_and_resource_read_telemetry(tmp_path):
    """S5: every skill is mirrored as a skill:// resource serving the same
    content as skill_read, and reads fire resource_read (resource_uri)."""
    capture = CaptureServer()
    try:
        with MCPStdioClient(env_extra={"HOME": str(tmp_path)},
                            telemetry_url=capture.url) as c:
            c.handshake()
            resources = c.request("resources/list")["result"]["resources"]
            uris = {r["uri"] for r in resources}
            assert "skill://interpreting-errors" in uris

            read = c.request("resources/read", {
                "uri": "skill://interpreting-errors"}, timeout=30)["result"]
            content = read["contents"][0]["text"]
            assert "search_papers" in content

            skill = c.request("tools/call", {
                "name": "skill_read",
                "arguments": {"name": "interpreting-errors"}}, timeout=30)
            assert parse_result(skill["result"])["content"] == content, \
                "resource mirror must serve exactly what skill_read serves"

            assert capture.wait_for_events(["resource_read"]), \
                capture.event_names()
            reads = [p["properties"] for p in capture.payloads
                     if p["event"] == "resource_read"]
            assert any(r["resource_uri"] == "skill://interpreting-errors"
                       for r in reads)
    finally:
        capture.close()


def test_brief_version_on_validation_error(tmp_path):
    """S3: a versioned brief tags its tool_executed with brief_version."""
    capture = CaptureServer()
    try:
        with MCPStdioClient(env_extra={"HOME": str(tmp_path)},
                            telemetry_url=capture.url) as c:
            c.handshake()
            res = c.request("tools/call", {
                "name": "get_paper",
                "arguments": {"identifier": "whatever", "id_type": "bogus"}})
            assert "error" in parse_result(res["result"])
            assert capture.wait_for_events(["tool_executed"]), \
                capture.event_names()
            ex = [p["properties"] for p in capture.payloads
                  if p["event"] == "tool_executed"][0]
            assert ex["status"] == "error"
            assert ex["brief_version"] == "papers-id-type-v1"
    finally:
        capture.close()


def test_progress_messages_flagship(tmp_path):
    """S8 FLAGSHIP: a progressToken on search_papers yields one
    notifications/progress per upstream source with a human-readable
    message; telemetry captures progress_updates_sent. No token -> no
    notifications (zero cost). Offline via the unroutable proxy."""
    capture = CaptureServer()
    try:
        env = {"HOME": str(tmp_path), **PROXY_ENV}
        with MCPStdioClient(env_extra=env, telemetry_url=capture.url) as c:
            c.handshake()
            res, notes = c.request_full("tools/call", {
                "name": "search_papers",
                "arguments": {"query": "anything", "limit": 3},
                "_meta": {"progressToken": "tok-1"},
            }, timeout=90)
            assert "error" not in res, res.get("error")
            progress = [n["params"] for n in notes
                        if n["method"] == "notifications/progress"]
            assert len(progress) == 5, f"one update per source: {progress}"
            assert all(p["progressToken"] == "tok-1" for p in progress)
            messages = [p["message"] for p in progress]
            assert all(m for m in messages)
            assert any("pending:" in m for m in messages)
            assert "all sources done" in messages[-1]
            assert progress[-1]["progress"] == 5.0
            assert progress[-1]["total"] == 5.0
            # sources are named for the human, in fan-out order
            assert messages[0].startswith("arXiv:")
            assert messages[-1].startswith("PubMed:")

            # zero-cost path: same call without a token -> no notifications
            res, notes = c.request_full("tools/call", {
                "name": "search_papers",
                "arguments": {"query": "anything", "limit": 3},
            }, timeout=90)
            assert "error" not in res, res.get("error")
            assert [n for n in notes
                    if n["method"] == "notifications/progress"] == []

            assert capture.wait_for_events(["tool_executed"]), \
                capture.event_names()
            ex = [p["properties"] for p in capture.payloads
                  if p["event"] == "tool_executed"
                  and p["properties"]["tool_name"] == "search_papers"]
            assert len(ex) == 2
            assert ex[0]["has_progress_token"] is True
            assert ex[0]["progress_updates_sent"] == 5
            assert ex[1]["has_progress_token"] is False
            assert "progress_updates_sent" not in ex[1]
    finally:
        capture.close()


def test_elicitation_s2_key_accept(tmp_path):
    """S7: semanticscholar explicitly requested + skipped (rate limited) +
    client declares form elicitation -> the server elicits the key, applies
    it session-only, retries once. setup_flow fires; the key NEVER appears
    in telemetry. Offline via the unroutable proxy (retry still fails ->
    flow_outcome=still_failing)."""
    capture = CaptureServer()
    secret = "elicited-test-key-000111222333"
    try:
        env = {"HOME": str(tmp_path), **PROXY_ENV}
        with MCPStdioClient(env_extra=env, telemetry_url=capture.url) as c:
            c.handshake(capabilities={"elicitation": {"form": {}}})
            seen = {}

            def answer(method, params):
                seen["method"] = method
                seen["message"] = params.get("message", "")
                return {"action": "accept", "content": {"api_key": secret}}

            res, _ = c.request_full("tools/call", {
                "name": "search_papers",
                "arguments": {"query": "anything", "limit": 3,
                              "sources": ["semanticscholar"]},
            }, timeout=120, request_handler=answer)
            assert "error" not in res, res.get("error")
            assert seen["method"] == "elicitation/create"
            assert "semanticscholar.org/product/api" in seen["message"]
            assert "never written to disk" in seen["message"]

            assert capture.wait_for_events(["setup_flow"]), \
                capture.event_names()
            flow = [p["properties"] for p in capture.payloads
                    if p["event"] == "setup_flow"][0]
            assert flow["flow_branch"] == "source_key"
            assert flow["elicit_action"] == "accept"
            assert flow["flow_outcome"] == "still_failing"  # proxy blocks retry

            blob = json.dumps(capture.payloads)
            assert secret not in blob, "elicited key leaked into telemetry"
    finally:
        capture.close()


def test_elicitation_gated_off_without_capability(tmp_path):
    """S7 gate: a client that does NOT declare elicitation gets today's
    behavior exactly — skipped + hint, no elicitation request, no
    setup_flow."""
    capture = CaptureServer()
    try:
        env = {"HOME": str(tmp_path), **PROXY_ENV}
        with MCPStdioClient(env_extra=env, telemetry_url=capture.url) as c:
            c.handshake()  # capabilities: {}

            def fail_on_request(method, params):
                raise AssertionError(f"unexpected server request: {method}")

            res, _ = c.request_full("tools/call", {
                "name": "search_papers",
                "arguments": {"query": "anything", "limit": 3,
                              "sources": ["semanticscholar"]},
            }, timeout=90, request_handler=fail_on_request)
            assert "error" not in res, res.get("error")
            data = parse_result(res["result"])
            assert data["skipped"] and \
                data["skipped"][0]["source"] == "semanticscholar"
            assert capture.wait_for_events(["tool_executed"])
            assert "setup_flow" not in capture.event_names()
    finally:
        capture.close()


def test_retracted_paper_relay_block():
    """S3/S4: a retracted paper (Wakefield 1998, stably flagged by OpenAlex)
    returns the usual JSON data block PLUS one audience:["user"] relay block,
    and its tool_executed carries brief_version papers-retracted-v1."""
    capture = CaptureServer()
    try:
        import tempfile
        with MCPStdioClient(env_extra={"HOME": tempfile.mkdtemp()},
                            telemetry_url=capture.url) as c:
            c.handshake()
            res = c.request("tools/call", {
                "name": "get_paper",
                "arguments": {"identifier": "10.1016/S0140-6736(97)11096-0",
                              "id_type": "doi", "include_references": False,
                              "include_citations": False, "verify": True},
            }, timeout=90)["result"]
            blocks = res["content"]
            data = json.loads(blocks[0]["text"])
            if (data.get("verification") or {}).get("retracted") is not True:
                pytest.skip("OpenAlex did not flag the fixture as retracted "
                            "(offline or upstream change)")
            assert len(blocks) == 2, "expected data block + relay block"
            relay = blocks[1]
            assert relay["annotations"]["audience"] == ["user"]
            assert "RELAY TO THE USER" in relay["text"]
            assert "retracted" in relay["text"]
            # the data block parses exactly like a plain dict return
            # (Crossref lowercases DOIs)
            assert data["paper"]["doi"].lower() == \
                "10.1016/s0140-6736(97)11096-0"

            assert capture.wait_for_events(["tool_executed"]), \
                capture.event_names()
            ex = [p["properties"] for p in capture.payloads
                  if p["event"] == "tool_executed"][0]
            assert ex["status"] == "success"
            assert ex["brief_version"] == "papers-retracted-v1"
            assert ex["rows_returned"] == 1  # counts the data payload
    finally:
        capture.close()
