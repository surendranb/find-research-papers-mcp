# SPDX-License-Identifier: Apache-2.0
"""Test package build, wheel contents, and clean importability.
Run: pytest tests/test_packaging.py"""

import io
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


def test_package_imports():
    """Verify that importing papers_mcp exports version and subpackages cleanly."""
    import papers_mcp
    import papers_mcp.server
    import papers_mcp.sources
    import papers_mcp.telemetry

    assert papers_mcp.__version__ == "0.4.5"
    assert hasattr(papers_mcp.server, "search_papers")
    assert hasattr(papers_mcp.sources, "SOURCES")
    assert "arxiv" in papers_mcp.sources.SOURCES
    assert "semanticscholar" in papers_mcp.sources.SOURCES


def test_wheel_archive_contents(tmp_path):
    """Build a wheel with uv and verify zip contents contain sources subpackage."""
    root_dir = Path(__file__).resolve().parents[1]
    res = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=root_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"Expected 1 wheel, got: {wheels}"
    
    with zipfile.ZipFile(wheels[0], "r") as zf:
        names = zf.namelist()
        assert "papers_mcp/__init__.py" in names
        assert "papers_mcp/server.py" in names
        assert "papers_mcp/sources/__init__.py" in names
        assert "papers_mcp/sources/arxiv.py" in names
        assert "papers_mcp/sources/openalex.py" in names
        assert "papers_mcp/sources/pubmed.py" in names
        assert "papers_mcp/sources/crossref.py" in names
        assert "papers_mcp/sources/semanticscholar.py" in names
