#!/usr/bin/env python3
"""Sync the committed OpenAPI snapshots against the canonical specs published by K2.

The K2 Rails app exposes each released spec inline at
``<docs-base>/docs/openapi/<version>`` (see kolide/k2#14492). The files under
``openapi/openapi<version>.json`` in this repo are meant to mirror those specs
exactly so the drift checks in ``tests/test_openapi_drift.py`` stay meaningful.

This script fetches the published spec for every version in
:data:`~kolide_mcp.api_version.SUPPORTED_KOLIDE_API_VERSIONS`, compares it
semantically (key order / whitespace ignored) with the local snapshot, and
rewrites any file that has drifted. It is run weekly (and on demand) by
``.github/workflows/openapi-spec-drift.yml``; when it rewrites a file, that
workflow opens a PR with the refreshed snapshot.

Exit codes:
    0  no drift (or ``--check`` found no drift)
    1  drift detected (files were rewritten, unless ``--check``)
    2  a spec could not be fetched / was not valid OpenAPI JSON

Usage:
    python scripts/sync_openapi_specs.py                 # rewrite drifted files
    python scripts/sync_openapi_specs.py --check          # report only, never write
    DOCS_BASE_URL=https://staging.kolide.com python scripts/sync_openapi_specs.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

# Import lazily-safe: the script lives in scripts/, the package in src/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kolide_mcp.api_version import SUPPORTED_KOLIDE_API_VERSIONS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENAPI_DIR = REPO_ROOT / "openapi"
DEFAULT_DOCS_BASE_URL = "https://www.kolide.com"
REQUEST_TIMEOUT_SECONDS = 30.0


def spec_url(base_url: str, version: str) -> str:
    """Canonical inline-JSON URL the K2 docs serve for *version*."""
    return f"{base_url.rstrip('/')}/docs/openapi/{version}"


def local_spec_path(version: str) -> Path:
    return OPENAPI_DIR / f"openapi{version}.json"


def _canonical(spec: dict) -> str:
    """Stable serialization used only for *comparison* (key order ignored)."""
    return json.dumps(spec, sort_keys=True, separators=(",", ":"))


def _operations(spec: dict) -> set[str]:
    """``"METHOD /path"`` for every HTTP operation, for the PR summary."""
    ops: set[str] = set()
    methods = ("get", "post", "put", "patch", "delete", "head", "options")
    for path, item in (spec.get("paths") or {}).items():
        if isinstance(item, dict):
            for method in methods:
                if method in item:
                    ops.add(f"{method.upper()} {path}")
    return ops


def fetch_published_spec(base_url: str, version: str) -> tuple[str, dict]:
    """Return ``(raw_text, parsed)`` for the published spec, or raise ValueError."""
    url = spec_url(base_url, version)
    response = httpx.get(url, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
    response.raise_for_status()
    text = response.text
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{url} did not return valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or "openapi" not in parsed:
        raise ValueError(f"{url} did not return an OpenAPI document (missing 'openapi' key)")
    declared = (parsed.get("info") or {}).get("version")
    if declared != version:
        raise ValueError(
            f"{url} declares info.version={declared!r}, expected {version!r}"
        )
    return text, parsed


def summarize_change(old: dict | None, new: dict) -> list[str]:
    """Human-readable bullet list of operation-level changes for the PR body."""
    new_ops = _operations(new)
    if old is None:
        return [f"new snapshot with {len(new_ops)} operations"]
    old_ops = _operations(old)
    added = sorted(new_ops - old_ops)
    removed = sorted(old_ops - new_ops)
    lines: list[str] = []
    for op in added:
        lines.append(f"added `{op}`")
    for op in removed:
        lines.append(f"removed `{op}`")
    if not lines:
        # Same operations, but schemas / params / descriptions changed.
        lines.append("schema or metadata changes (no operations added or removed)")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift without rewriting files (exit 1 if drift found).",
    )
    args = parser.parse_args()

    base_url = os.getenv("DOCS_BASE_URL", DEFAULT_DOCS_BASE_URL)
    drifted: list[tuple[str, list[str]]] = []
    fetch_failed = False

    for version in SUPPORTED_KOLIDE_API_VERSIONS:
        url = spec_url(base_url, version)
        try:
            raw_text, published = fetch_published_spec(base_url, version)
        except (httpx.HTTPError, ValueError) as exc:
            print(f"::error::Could not fetch {url}: {exc}", file=sys.stderr)
            fetch_failed = True
            continue

        path = local_spec_path(version)
        local = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

        if local is not None and _canonical(local) == _canonical(published):
            print(f"{version}: up to date")
            continue

        changes = summarize_change(local, published)
        drifted.append((version, changes))
        print(f"{version}: DRIFT detected ({path.name})")
        for line in changes:
            print(f"    - {line}")

        if not args.check:
            # Mirror the upstream bytes exactly so the snapshot equals what K2 serves.
            path.write_text(raw_text, encoding="utf-8")

    if fetch_failed:
        return 2

    _emit_outputs(drifted)

    if drifted and not args.check:
        print(f"\nRewrote {len(drifted)} snapshot(s).")
    return 1 if drifted else 0


def _emit_outputs(drifted: list[tuple[str, list[str]]]) -> None:
    """Expose results to the GitHub Actions step via GITHUB_OUTPUT / a summary file."""
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"drift={'true' if drifted else 'false'}\n")
            handle.write(f"versions={' '.join(v for v, _ in drifted)}\n")

    body_lines = ["## OpenAPI spec drift", ""]
    if drifted:
        body_lines.append(
            "The committed snapshots no longer match the specs published by the K2 "
            "docs. This PR refreshes them."
        )
        for version, changes in drifted:
            body_lines.append("")
            body_lines.append(f"### `{version}`")
            for line in changes:
                body_lines.append(f"- {line}")
    else:
        body_lines.append("All snapshots are up to date.")
    Path(os.getenv("DRIFT_SUMMARY_PATH", REPO_ROOT / ".openapi-drift-summary.md")).write_text(
        "\n".join(body_lines) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
