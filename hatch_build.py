"""Custom hatch build hook that bakes the latest ``origin/main`` SHA into the wheel.

At build time we resolve the current tip of the ``main`` branch on the remote
``origin`` and write it to ``src/kolide_mcp/_main_sha.py``. The runtime
``KolideClient`` reads this file to advertise the published main SHA in its
``User-Agent`` header, regardless of which branch the build was run from.

Builds whose ``origin`` does not point at the canonical upstream repository
are tagged ``"fork"`` so server-side telemetry can distinguish them from
official builds.

Resolution order:
    1. ``"fork"`` if ``origin`` is not the canonical upstream
    2. ``git ls-remote origin main`` (network — always current)
    3. ``git rev-parse origin/main`` (cached remote tracking ref)
    4. ``git rev-parse HEAD`` (last resort: local HEAD on an upstream checkout)
    5. ``"unknown"`` (no git available)
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
else:
    try:
        from hatchling.builders.hooks.plugin.interface import BuildHookInterface
    except ImportError:
        BuildHookInterface = object  # type: ignore[assignment,misc]

OUTPUT_RELPATH = "src/kolide_mcp/_main_sha.py"
REMOTE_NAME = "origin"
BRANCH_NAME = "main"
UPSTREAM_OWNER = "kolide"
UPSTREAM_REPO = "device-trust-mcp-server"

_UPSTREAM_PATTERN = re.compile(
    rf"(?:^|//|@)github\.com[:/]{re.escape(UPSTREAM_OWNER)}/"
    rf"{re.escape(UPSTREAM_REPO)}(?:\.git)?/?$",
    re.IGNORECASE,
)


def _run_git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def _is_upstream_origin(repo_root: Path) -> bool | None:
    """Return True/False if origin is known, or None if it can't be determined."""
    url = _run_git(["remote", "get-url", REMOTE_NAME], repo_root)
    if not url:
        return None
    return bool(_UPSTREAM_PATTERN.search(url))


def resolve_main_sha(repo_root: Path) -> str:
    """Resolve the latest ``origin/main`` SHA, with graceful fallbacks.

    Returns ``"fork"`` when the build's ``origin`` remote does not match the
    canonical upstream repository, so downstream telemetry does not mistake a
    fork's main SHA for an official build.
    """
    is_upstream = _is_upstream_origin(repo_root)
    if is_upstream is None:
        return "unknown"
    if not is_upstream:
        return "fork"

    output = _run_git(["ls-remote", REMOTE_NAME, BRANCH_NAME], repo_root)
    if output:
        sha = output.split()[0]
        if sha:
            return sha

    sha = _run_git(["rev-parse", f"{REMOTE_NAME}/{BRANCH_NAME}"], repo_root)
    if sha:
        return sha

    sha = _run_git(["rev-parse", "HEAD"], repo_root)
    if sha:
        return sha

    return "unknown"


class CustomBuildHook(BuildHookInterface):
    """Writes ``_main_sha.py`` before the wheel/sdist is assembled."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        repo_root = Path(self.root)
        sha = resolve_main_sha(repo_root)
        output_path = repo_root / OUTPUT_RELPATH
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            '"""Generated at build time. Do not edit or track in version control."""\n'
            "\n"
            f'MAIN_SHA = "{sha}"\n'
        )
        build_data.setdefault("force_include", {})
        build_data["force_include"][str(output_path)] = OUTPUT_RELPATH
