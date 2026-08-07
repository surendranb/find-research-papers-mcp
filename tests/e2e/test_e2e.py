# SPDX-License-Identifier: Apache-2.0

"""Native MCP-protocol e2e: spawn the REAL server binary and speak JSON-RPC
over stdio (initialize -> tools/list -> tools/call). This tests the server as
an MCP client sees it — not the Python functions directly."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER_CMD = [str(ROOT / ".venv/bin/python"), "-m", "papers_mcp"]

pytestmark = pytest.mark.e2e


class MCPStdioClient:
    """Minimal JSON-RPC client that matches response IDs (pendingResolve must
    check resp.id === requestId, else responses from one call pollute another)."""

    def __init__(self):
        self.proc = subprocess.Popen(
            SERVER_CMD,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
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

    def handshake(self):
        init = self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "e2e-test", "version": "0.0.1"},
        })
        self.notify("notifications/initialized")
        return init

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
        assert init["result"]["serverInfo"]["name"] == "papers-mcp"
        assert "version" in init["result"]["serverInfo"]

        tools = c.request("tools/list")
        names = [t["name"] for t in tools["result"]["tools"]]
        assert names == ["search_papers", "get_paper", "list_sources"]


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
