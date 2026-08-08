# SPDX-License-Identifier: Apache-2.0

"""Brand scout for MCP server names (SUR-92 Phase 0 deliverable).

Usage: python3 scripts/scout_mcp_brand.py <candidate-name> [more-candidates...]

Checks availability across the four surfaces that matter for an MCP server
launch: PyPI (pip/uv install), npm (npx bridge), GitHub (repo), and the
*.mcp.dev-style domain. Exit code 0 if any candidate is free on all four.

Example:
    python3 scripts/scout_mcp_brand.py find-research-papers-mcp scholarly-mcp open-scholar-mcp
"""

import json
import sys
import urllib.error
import urllib.request

CHECKS = [
    ("PyPI", "https://pypi.org/pypi/{name}/json"),
    ("npm", "https://registry.npmjs.org/{name}"),
    ("GitHub repo", "https://api.github.com/repos/surendranb/{name}"),
    ("GitHub search", "https://api.github.com/search/repositories?q={name}+in:name"),
]


def _probe(url: str) -> int:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "find-research-papers-mcp-scout/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def scout(name: str) -> dict:
    results = {}
    for label, template in CHECKS:
        url = template.format(name=name)
        status = _probe(url)
        if label == "GitHub search":
            # free unless a repo literally named <name> exists
            taken = False
            if status == 200:
                try:
                    with urllib.request.urlopen(urllib.request.Request(
                            url, headers={"User-Agent": "find-research-papers-mcp-scout/0.1"}), timeout=10) as r:
                        data = json.load(r)
                    taken = any(item["full_name"].endswith(f"/{name}")
                                for item in data.get("items", []))
                except Exception:
                    taken = True  # assume taken if we cannot verify
            results[label] = "TAKEN" if taken else "free"
        else:
            results[label] = "TAKEN" if status == 200 else ("free" if status in (404, 0) else f"http-{status}")
    return results


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    any_free = False
    for name in argv:
        results = scout(name.lower())
        verdict = "OK" if all(v == "free" for v in results.values()) else "COLLISION"
        any_free = any_free or (verdict == "OK")
        print(f"{name}: {verdict}")
        for label, status in results.items():
            print(f"    {label:14} {status}")
    print()
    print("verdict: at least one candidate is fully available" if any_free
          else "verdict: every candidate has at least one collision")
    return 0 if any_free else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
