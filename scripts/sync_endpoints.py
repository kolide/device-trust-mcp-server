#!/usr/bin/env python3
"""Reconcile the MCP endpoint registry (``endpoints.py``) with the published K2 specs.

The declarative registry in ``src/kolide_mcp/endpoints.py`` is the implementation
checklist for the REST contract described by the OpenAPI specs K2 publishes,
unauthenticated, on the API host itself: ``GET /openapi_specifications`` lists every
released version and its ``spec_url``, and ``GET /openapi_specifications/<version>``
serves that version's spec as pure JSON. This script discovers the published versions
from the index, fetches the spec for *every* supported Kolide API version, then
programmatically updates the registry so it mirrors those specs:

* **``api_versions`` gating** — the same operation is not exposed by every dated
  API version. For each ``EndpointSpec`` we compute the exact set of supported
  versions whose spec contains its ``(method, path)`` operation and write the
  matching gate: ``None`` when the operation is in *all* supported versions, or a
  ``frozenset({...})`` of just the versions that expose it. Operations are never
  deleted — an endpoint that drops out of a newer version is simply gated to the
  versions that still have it, so we never ship a backwards-incompatible change.
* **``paginated``** — set from whether the operation declares ``cursor`` /
  ``per_page`` query parameters.
* **``searchable_fields``** — derived from the operation's ``query`` parameter
  (its ``examples`` keys, e.g. ``name~`` -> ``name``). Only *inline list literals*
  are rewritten in place; entries that reference a shared ``_*_FIELDS`` constant
  are reported instead of rewritten, so we never silently change the fields of the
  other endpoints that share the constant.
* **New operations** — an operation with no matching ``EndpointSpec`` is scaffolded
  as a new entry (correctly version-gated) in a clearly marked review block at the
  end of the registry, and reported. Its ``description`` is taken from the spec's
  operation ``summary`` (falling back to a ``TODO`` placeholder when absent);
  descriptions on *existing* endpoints are never touched.
* **Drift we do not auto-apply** (request-body parameters, operations that vanished
  from *all* supported specs, a dated version the API publishes that this server does
  not support yet) is reported for a human to resolve.

Edits are surgical: the file is parsed with :mod:`ast`, only the spans of the
reconciled fields are rewritten, and every hand-authored ``description`` /
``search_examples`` / ``params`` value is left untouched.

Run by ``.github/workflows/sync-endpoints.yml`` on Tuesdays and Thursdays (and on
demand); when it changes ``endpoints.py`` the workflow opens a PR with the diff.
The repo does not commit OpenAPI snapshots — the live published specs are the
source of truth on every run.

Every run writes its report to ``$GITHUB_STEP_SUMMARY`` (when set) as well as to
``$SYNC_SUMMARY_PATH``, which the workflow reuses as the PR body. A run whose only
drift needs a human produces no PR, so the step summary is the only place that report
surfaces — the workflow turns that case red on purpose.

Exit codes:
    0  registry already matches the specs (or ``--check`` found nothing)
    1  registry updated (or, with ``--check``, drift was found)
    2  a spec could not be fetched / was not valid OpenAPI JSON, or the reconciler hit
       an unexpected exception (both are hard failures for the workflow)
    3  drift was found that requires a human (removed operations, body-param drift,
       shared-constant drift, an unsupported published version)

Usage:
    uv run python scripts/sync_endpoints.py            # fetch specs, rewrite the registry
    uv run python scripts/sync_endpoints.py --check     # report only, never write
    KOLIDE_API_URL=https://api.staging.kolide.com uv run python scripts/sync_endpoints.py
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from kolide_mcp.api_version import SUPPORTED_KOLIDE_API_VERSIONS  # noqa: E402

ENDPOINTS_PATH = REPO_ROOT / "src" / "kolide_mcp" / "endpoints.py"
# Same host and env var the runtime client uses (``src/kolide_mcp/client.py``); the
# spec endpoints live on the API itself and need no authentication.
DEFAULT_API_BASE_URL = "https://api.kolide.com"
SPEC_INDEX_PATH = "/openapi_specifications"
REQUEST_TIMEOUT_SECONDS = 30.0
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


# ===== Spec fetching =====


def spec_index_url(base_url: str) -> str:
    """Discovery URL listing every released spec (``GET /openapi_specifications``)."""
    return f"{base_url.rstrip('/')}{SPEC_INDEX_PATH}"


def spec_url(base_url: str, version: str) -> str:
    """Pure-JSON spec URL the API serves for *version*."""
    return f"{base_url.rstrip('/')}{SPEC_INDEX_PATH}/{version}"


def _get_json(url: str) -> dict:
    """GET *url* and parse it as a JSON object, or raise ValueError."""
    response = httpx.get(url, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
    response.raise_for_status()
    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{url} did not return valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{url} did not return a JSON object")
    return parsed


def fetch_spec_index(base_url: str) -> dict[str, str]:
    """Return ``{version: spec_url}`` for every spec the API publishes.

    ``GET /openapi_specifications`` renders the usual ``{"data": [...]}`` envelope with
    a ``version`` and ``spec_url`` per released version. The advertised ``spec_url`` is
    honoured only when it points at *base_url* — so a staging/dev override is never
    silently redirected to the production spec — otherwise it is rebuilt from
    *base_url*.
    """
    url = spec_index_url(base_url)
    payload = _get_json(url)
    entries = payload.get("data")
    if not isinstance(entries, list):
        raise ValueError(f"{url} did not return a 'data' list of published specs")

    origin = base_url.rstrip("/")
    index: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        if not isinstance(version, str) or not version:
            continue
        advertised = entry.get("spec_url")
        index[version] = (
            advertised
            if isinstance(advertised, str) and advertised.startswith(origin)
            else spec_url(base_url, version)
        )
    if not index:
        raise ValueError(f"{url} listed no published specs")
    return index


def fetch_published_spec(url: str, version: str) -> dict:
    """Return the parsed published spec for *version*, or raise ValueError."""
    parsed = _get_json(url)
    if "openapi" not in parsed:
        raise ValueError(f"{url} did not return an OpenAPI document (missing 'openapi' key)")
    declared = (parsed.get("info") or {}).get("version")
    if declared != version:
        raise ValueError(f"{url} declares info.version={declared!r}, expected {version!r}")
    return parsed


# ===== Spec parsing =====


def normalize_path(path: str) -> str:
    """Collapse ``{placeholder}`` segments so equivalent path templates compare equal."""
    parts = [
        "{}" if seg.startswith("{") and seg.endswith("}") else seg
        for seg in path.strip("/").split("/")
    ]
    return "/" + "/".join(parts) if parts else "/"


def op_key(method: str, path: str) -> tuple[str, str]:
    return method.upper(), normalize_path(path)


def extract_searchable_fields(operation: dict) -> list[str] | None:
    """Ordered searchable field names from an operation's ``query`` parameter.

    Kolide encodes the searchable fields as the keys of the ``query`` parameter's
    ``examples`` map (``"name~"``, ``"registered_at>"``, ...); the field name is the
    key with any trailing search operator (``: ~ < >``) stripped.
    """
    for param in operation.get("parameters", []):
        if param.get("in") == "query" and param.get("name") == "query":
            examples = param.get("examples") or {}
            fields: list[str] = []
            for raw in examples:
                name = raw.rstrip(":~<>")
                if name and name not in fields:
                    fields.append(name)
            return fields or None
    return None


def operation_is_paginated(operation: dict) -> bool:
    query_names = {
        p.get("name")
        for p in operation.get("parameters", [])
        if p.get("in") == "query"
    }
    return "cursor" in query_names or "per_page" in query_names


def operation_has_body(operation: dict) -> bool:
    return bool(operation.get("requestBody"))


@dataclass
class OperationInfo:
    """Merged view of one operation across every supported spec version."""

    method: str
    normalized_path: str
    raw_path: str
    versions: set[str] = field(default_factory=set)
    searchable_fields: list[str] | None = None
    paginated: bool = False
    has_body: bool = False
    summary: str = ""

    def api_versions_gate(self, supported: tuple[str, ...]) -> frozenset[str] | None:
        """``None`` if the operation is in every supported version, else the subset."""
        if self.versions >= set(supported):
            return None
        return frozenset(self.versions)


def collect_operations(
    specs: dict[str, dict],
    supported: tuple[str, ...],
) -> dict[tuple[str, str], OperationInfo]:
    """Index every operation across all supplied version specs by ``op_key``.

    Later (newer) versions win for metadata (searchable fields / pagination) so the
    registry describes the current shape, while :attr:`OperationInfo.versions`
    records exactly which versions expose the operation for gating.
    """
    ops: dict[tuple[str, str], OperationInfo] = {}
    for version in supported:
        spec = specs.get(version)
        if spec is None:
            continue
        for raw_path, item in (spec.get("paths") or {}).items():
            if not isinstance(item, dict):
                continue
            present = {m for m in _HTTP_METHODS if m in item}
            for method in _HTTP_METHODS:
                if method not in item:
                    continue
                # MCP implements PATCH, not the PUT alias some resources also list.
                if method == "put" and "patch" in present:
                    continue
                key = op_key(method, raw_path)
                info = ops.get(key)
                if info is None:
                    info = OperationInfo(
                        method=key[0], normalized_path=key[1], raw_path=raw_path
                    )
                    ops[key] = info
                info.versions.add(version)
                info.raw_path = raw_path
                info.searchable_fields = extract_searchable_fields(item[method])
                info.paginated = operation_is_paginated(item[method])
                info.has_body = operation_has_body(item[method])
                info.summary = (item[method].get("summary") or "").strip()
    return ops


# ===== Source (AST) model of endpoints.py =====


@dataclass
class SpecNode:
    """An ``EndpointSpec(...)`` call located in the registry source."""

    name: str
    method: str
    path: str
    call: ast.Call
    keywords: dict[str, ast.keyword]

    def keyword_value(self, key: str) -> ast.expr | None:
        kw = self.keywords.get(key)
        return kw.value if kw else None


def _const_str(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def parse_spec_nodes(tree: ast.Module) -> list[SpecNode]:
    """Every ``EndpointSpec(...)`` call in the module, in source order."""
    nodes: list[SpecNode] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "EndpointSpec":
            continue
        keywords = {kw.arg: kw for kw in node.keywords if kw.arg is not None}
        name = _const_str(keywords["name"].value) if "name" in keywords else None
        method = _const_str(keywords["method"].value) if "method" in keywords else None
        path = _const_str(keywords["path"].value) if "path" in keywords else None
        if name is None or method is None or path is None:
            continue
        nodes.append(SpecNode(name, method, path, node, keywords))
    return nodes


def find_endpoints_list(tree: ast.Module) -> ast.List | None:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "ENDPOINTS" and isinstance(node.value, ast.List):
                return node.value
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "ENDPOINTS" and isinstance(node.value, ast.List):
                    return node.value
    return None


# ===== Byte-offset editing =====


class SourceEditor:
    """Applies non-overlapping span replacements to UTF-8 source bytes."""

    def __init__(self, source: str) -> None:
        self._data = source.encode("utf-8")
        self._line_starts = [0]
        for i, byte in enumerate(self._data):
            if byte == 0x0A:  # newline
                self._line_starts.append(i + 1)
        self._edits: list[tuple[int, int, bytes]] = []

    def offset(self, lineno: int, col: int) -> int:
        return self._line_starts[lineno - 1] + col

    def node_span(self, node: ast.AST) -> tuple[int, int]:
        return (
            self.offset(node.lineno, node.col_offset),
            self.offset(node.end_lineno, node.end_col_offset),
        )

    def replace(self, start: int, end: int, text: str) -> None:
        self._edits.append((start, end, text.encode("utf-8")))

    def insert(self, at: int, text: str) -> None:
        self._edits.append((at, at, text.encode("utf-8")))

    def find_next(self, needle: str, start: int) -> int:
        idx = self._data.find(needle.encode("utf-8"), start)
        if idx < 0:
            raise ValueError(f"expected {needle!r} after byte {start}")
        return idx

    def find_within(self, needle: str, start: int, end: int) -> int | None:
        """First offset of *needle* in ``[start, end)``, or None. Never scans past *end*."""
        idx = self._data.find(needle.encode("utf-8"), start, end)
        return None if idx < 0 else idx

    def result(self) -> str:
        edits = sorted(self._edits, key=lambda e: e[0])
        for prev, nxt in zip(edits, edits[1:]):
            if prev[1] > nxt[0]:
                raise ValueError("overlapping edits")
        out = bytearray()
        cursor = 0
        for start, end, text in edits:
            out += self._data[cursor:start]
            out += text
            cursor = end
        out += self._data[cursor:]
        return out.decode("utf-8")

    @property
    def dirty(self) -> bool:
        return bool(self._edits)


# ===== Literal formatting =====


def format_api_versions(gate: frozenset[str] | None) -> str:
    if gate is None:
        return "None"
    inner = ", ".join(f'"{v}"' for v in sorted(gate))
    return f"frozenset({{{inner}}})"


def format_fields(fields: list[str]) -> str:
    return "[" + ", ".join(json.dumps(f) for f in fields) + "]"


# ===== Reconciliation =====


@dataclass
class Report:
    api_version_changes: list[str] = field(default_factory=list)
    paginated_changes: list[str] = field(default_factory=list)
    searchable_changes: list[str] = field(default_factory=list)
    searchable_constant_drift: list[str] = field(default_factory=list)
    body_drift: list[str] = field(default_factory=list)
    new_operations: list[str] = field(default_factory=list)
    removed_operations: list[str] = field(default_factory=list)
    unsupported_versions: list[str] = field(default_factory=list)

    @property
    def auto_applied(self) -> bool:
        return bool(
            self.api_version_changes
            or self.paginated_changes
            or self.searchable_changes
            or self.new_operations
        )

    @property
    def needs_human(self) -> bool:
        return bool(
            self.removed_operations
            or self.body_drift
            or self.searchable_constant_drift
            or self.unsupported_versions
        )


def _fields_from_node(node: ast.expr | None) -> tuple[list[str] | None, bool]:
    """Return (resolved inline fields, is_shared_constant_reference)."""
    if node is None:
        return None, False
    if isinstance(node, ast.Name):
        return None, True  # references a shared _*_FIELDS constant
    if isinstance(node, ast.List):
        vals = [_const_str(el) for el in node.elts]
        return [v for v in vals if v is not None], False
    return None, False


def _insert_keyword_after_last(
    editor: SourceEditor, spec_node: SpecNode, text: str
) -> None:
    """Insert ``<text>`` on its own line after the last keyword argument.

    The comma search is bounded by the ``EndpointSpec(...)`` call itself: an entry
    written without a trailing comma after its last kwarg gets one added here rather
    than splicing the new keyword in after some unrelated comma further down the file.
    """
    last = max(
        spec_node.keywords.values(),
        key=lambda kw: kw.value.end_lineno * 10_000 + kw.value.end_col_offset,
    )
    _, value_end = editor.node_span(last.value)
    _, call_end = editor.node_span(spec_node.call)
    comma = editor.find_within(",", value_end, call_end)
    if comma is None:
        editor.insert(value_end, f",\n        {text}")
    else:
        editor.insert(comma + 1, f"\n        {text}")


def reconcile(
    source: str,
    tree: ast.Module,
    spec_nodes: list[SpecNode],
    runtime_specs: list,
    operations: dict[tuple[str, str], OperationInfo],
    supported: tuple[str, ...],
) -> tuple[str, Report]:
    editor = SourceEditor(source)
    report = Report()
    runtime_by_name = {s.name: s for s in runtime_specs}
    node_by_name = {n.name: n for n in spec_nodes}
    matched_keys: set[tuple[str, str]] = set()

    for name, node in node_by_name.items():
        key = op_key(node.method, node.path)
        info = operations.get(key)
        rt = runtime_by_name.get(name)
        if info is None:
            # Endpoint that no supported spec exposes any longer.
            report.removed_operations.append(f"{node.method} {node.path} (kolide_{name})")
            continue
        matched_keys.add(key)

        # --- api_versions gating ---
        desired_gate = info.api_versions_gate(supported)
        current_gate = rt.api_versions if rt else None
        if desired_gate != current_gate:
            literal = format_api_versions(desired_gate)
            kw = node.keywords.get("api_versions")
            if kw is not None:
                start, end = editor.node_span(kw.value)
                editor.replace(start, end, literal)
            elif desired_gate is not None:
                _insert_keyword_after_last(editor, node, f"api_versions={literal},")
            report.api_version_changes.append(
                f"kolide_{name}: {_fmt_gate(current_gate)} -> {_fmt_gate(desired_gate)}"
            )

        # --- paginated ---
        current_paginated = bool(rt.paginated) if rt else False
        if info.paginated != current_paginated:
            kw = node.keywords.get("paginated")
            if kw is not None:
                start, end = editor.node_span(kw.value)
                editor.replace(start, end, "True" if info.paginated else "False")
            elif info.paginated:
                _insert_keyword_after_last(editor, node, "paginated=True,")
            report.paginated_changes.append(
                f"kolide_{name}: paginated {current_paginated} -> {info.paginated}"
            )

        # --- searchable_fields ---
        node_fields = node.keyword_value("searchable_fields")
        inline_fields, is_constant = _fields_from_node(node_fields)
        current_fields = rt.searchable_fields if rt else None
        desired_fields = info.searchable_fields
        same = set(current_fields or []) == set(desired_fields or [])
        if not same:
            if is_constant:
                report.searchable_constant_drift.append(
                    f"kolide_{name}: shared-constant fields differ from spec "
                    f"(spec={desired_fields})"
                )
            elif desired_fields:
                literal = format_fields(desired_fields)
                if node_fields is not None:
                    start, end = editor.node_span(node_fields)
                    editor.replace(start, end, literal)
                else:
                    _insert_keyword_after_last(
                        editor, node, f"searchable_fields={literal},"
                    )
                report.searchable_changes.append(
                    f"kolide_{name}: {current_fields} -> {desired_fields}"
                )
            # desired_fields empty while code has some: leave for human (rare).

        # --- request body presence (report only; descriptions are curated) ---
        has_params = bool(rt.params) if rt else False
        if info.has_body and not has_params and info.method in ("POST", "PATCH", "PUT"):
            report.body_drift.append(
                f"kolide_{name}: spec declares a request body but no params are defined"
            )

    # --- new operations: scaffold into a review block ---
    new_infos = [
        info for key, info in sorted(operations.items()) if key not in matched_keys
    ]
    if new_infos:
        endpoints_list = find_endpoints_list(tree)
        if endpoints_list is None:
            raise ValueError("could not locate the ENDPOINTS list in the source")
        # Insert after the last existing element's trailing comma, searching no further
        # than the list's closing bracket so a missing trailing comma is added instead
        # of matching a comma somewhere later in the file.
        last_elt_end = editor.node_span(endpoints_list.elts[-1])[1]
        list_end = editor.node_span(endpoints_list)[1]
        comma = editor.find_within(",", last_elt_end, list_end)
        block = "\n\n    # --- AUTO-GENERATED: review & refine (scripts/sync_endpoints.py) ---"
        for info in new_infos:
            block += _scaffold_endpoint(info, supported)
            report.new_operations.append(
                f"{info.method} {info.raw_path} (versions: {', '.join(sorted(info.versions))})"
            )
        if comma is None:
            editor.insert(last_elt_end, "," + block)
        else:
            editor.insert(comma + 1, block)

    return (editor.result() if editor.dirty else source), report


def _fmt_gate(gate: frozenset[str] | None) -> str:
    return "all versions" if gate is None else "{" + ", ".join(sorted(gate)) + "}"


def _derive_name(info: OperationInfo) -> str:
    """Best-effort tool name from an operation, e.g. GET /foo/{id}/bars -> get_foo_bars."""
    segments = [s for s in info.normalized_path.strip("/").split("/") if s != "{}"]
    verb = {
        "GET": "get",
        "POST": "create",
        "PATCH": "update",
        "PUT": "update",
        "DELETE": "delete",
    }[info.method]
    if info.method == "GET" and not info.normalized_path.rstrip("/").endswith("}"):
        verb = "list"
    tail = "_".join(segments) or "root"
    return f"{verb}_{tail}".replace("-", "_")


def _scaffold_endpoint(info: OperationInfo, supported: tuple[str, ...]) -> str:
    gate = info.api_versions_gate(supported)
    description = info.summary or "TODO: write a human-facing description for this endpoint"
    lines = [
        "    EndpointSpec(",
        f"        name={json.dumps(_derive_name(info))},",
        f"        description={json.dumps(description)},",
        f'        method="{info.method}",',
        f"        path={json.dumps(info.raw_path)},",
    ]
    if info.paginated:
        lines.append("        paginated=True,")
    if info.searchable_fields:
        lines.append(f"        searchable_fields={format_fields(info.searchable_fields)},")
    if gate is not None:
        lines.append(f"        api_versions={format_api_versions(gate)},")
    lines.append("    ),")
    return "\n" + "\n".join(lines)


# ===== Spec loading =====


def load_specs(
    supported: tuple[str, ...], base_url: str, index: dict[str, str]
) -> tuple[dict[str, dict], bool]:
    """Fetch each supported version's published spec. Returns (parsed, fetch_failed)."""
    parsed: dict[str, dict] = {}
    failed = False
    for version in supported:
        url = index.get(version)
        if url is None:
            print(
                f"::error::{version} is in SUPPORTED_KOLIDE_API_VERSIONS but "
                f"{spec_index_url(base_url)} does not publish a spec for it.",
                file=sys.stderr,
            )
            failed = True
            continue
        try:
            parsed[version] = fetch_published_spec(url, version)
        except (httpx.HTTPError, ValueError) as exc:
            print(f"::error::could not fetch {url}: {exc}", file=sys.stderr)
            failed = True
            continue
        print(f"{version}: fetched published spec from {url}")
    return parsed, failed


# ===== GitHub Actions plumbing =====


def build_summary(report: Report, changed: bool) -> str:
    """The markdown report, used both as the PR body and as the job summary."""
    versions = ", ".join(f"`{v}`" for v in SUPPORTED_KOLIDE_API_VERSIONS)
    lines = ["## Endpoint registry sync", ""]
    if not report.auto_applied and not report.needs_human:
        lines.append("`endpoints.py` already mirrors the published specs. No changes.")
    elif changed:
        lines.append(
            "Reconciled `src/kolide_mcp/endpoints.py` against the specs published for "
            f"{versions}."
        )
    else:
        lines.append(
            "Compared `src/kolide_mcp/endpoints.py` against the specs published for "
            f"{versions}. The drift below was **not applied** — `endpoints.py` is "
            "unchanged."
        )
    if report.needs_human and not changed:
        lines.extend(
            [
                "",
                "**Nothing was applied automatically, so no pull request carries this.** "
                "The drift below has to be resolved by hand.",
            ]
        )
    _section(lines, "API-version gating updated", report.api_version_changes)
    _section(lines, "Pagination updated", report.paginated_changes)
    _section(lines, "Searchable fields updated", report.searchable_changes)
    _section(lines, "New operations scaffolded (review the TODOs)", report.new_operations)
    _section(lines, "⚠️ Removed from all specs — needs a human", report.removed_operations)
    _section(lines, "⚠️ Request-body drift — needs a human", report.body_drift)
    _section(
        lines,
        "⚠️ Shared `_*_FIELDS` constant differs from spec — needs a human",
        report.searchable_constant_drift,
    )
    _section(
        lines,
        "⚠️ Published API version this server does not support — needs a human",
        report.unsupported_versions,
    )
    return "\n".join(lines) + "\n"


def write_step_summary(markdown: str) -> None:
    """Append *markdown* to the job summary so every run leaves a visible report.

    A run whose only drift needs a human opens no PR, so without this the report would
    be written to a temp file nobody ever reads.
    """
    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if not step_summary:
        return
    with open(step_summary, "a", encoding="utf-8") as fh:
        fh.write(markdown)


def emit_outputs(report: Report, changed: bool) -> None:
    gh_out = os.getenv("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")
            fh.write(f"needs_human={'true' if report.needs_human else 'false'}\n")

    markdown = build_summary(report, changed)
    Path(
        os.getenv("SYNC_SUMMARY_PATH", REPO_ROOT / ".endpoints-sync-summary.md")
    ).write_text(markdown, encoding="utf-8")
    write_step_summary(markdown)


def _section(lines: list[str], title: str, items: list[str]) -> None:
    if not items:
        return
    lines.append("")
    lines.append(f"### {title}")
    lines.extend(f"- {item}" for item in items)


def _print_report(report: Report) -> None:
    for title, items in (
        ("api_versions", report.api_version_changes),
        ("paginated", report.paginated_changes),
        ("searchable_fields", report.searchable_changes),
        ("new operations", report.new_operations),
        ("removed operations", report.removed_operations),
        ("body drift", report.body_drift),
        ("shared-constant drift", report.searchable_constant_drift),
        ("unsupported published version", report.unsupported_versions),
    ):
        for item in items:
            print(f"  [{title}] {item}")


def _run(args: argparse.Namespace) -> int:
    base_url = os.getenv("KOLIDE_API_URL", DEFAULT_API_BASE_URL)
    supported = SUPPORTED_KOLIDE_API_VERSIONS

    index_url = spec_index_url(base_url)
    try:
        index = fetch_spec_index(base_url)
    except (httpx.HTTPError, ValueError) as exc:
        print(f"::error::could not fetch {index_url}: {exc}", file=sys.stderr)
        return 2
    print(f"{index_url} publishes: {', '.join(sorted(index))}")

    parsed, fetch_failed = load_specs(supported, base_url, index)
    if fetch_failed:
        return 2

    operations = collect_operations(parsed, supported)

    from kolide_mcp.endpoints import ENDPOINTS as runtime_specs

    source = ENDPOINTS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    spec_nodes = parse_spec_nodes(tree)

    updated, report = reconcile(
        source, tree, spec_nodes, runtime_specs, operations, supported
    )
    changed = updated != source

    # Supporting a newly released dated version is a hand-made decision (it changes
    # the tools this server exposes and its default version) — the reconciler can only
    # flag that the API is publishing one we do not list.
    for version in sorted(index):
        if version not in supported:
            report.unsupported_versions.append(
                f"`{version}` is published at {index[version]} but is missing from "
                "`SUPPORTED_KOLIDE_API_VERSIONS` (`src/kolide_mcp/api_version.py`)"
            )

    print(f"Reconciled {len(spec_nodes)} endpoints against {len(parsed)} spec(s).")
    _print_report(report)

    if changed and not args.check:
        ast.parse(updated)  # never write syntactically broken source
        ENDPOINTS_PATH.write_text(updated, encoding="utf-8")
        print("Wrote updated endpoints.py")

    emit_outputs(report, changed and not args.check)

    if report.needs_human:
        return 3
    return 1 if changed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Report only; never write files."
    )
    args = parser.parse_args()

    # Any unexpected exception has to be loud: it must not share an exit code with
    # "registry updated", and it must leave a report behind even though the run wrote
    # no step outputs.
    try:
        return _run(args)
    except Exception:
        detail = traceback.format_exc()
        print(detail, file=sys.stderr)
        print(
            "::error::scripts/sync_endpoints.py raised an unexpected exception and did "
            "not complete.",
            file=sys.stderr,
        )
        write_step_summary(
            "## Endpoint registry sync\n\n"
            "❌ The reconciler raised an unexpected exception and did not complete, so "
            "this run reconciled nothing. Read the traceback, then check the working "
            "tree before trusting it.\n\n"
            f"```\n{detail}```\n"
        )
        # Same exit code as a fetch failure: the workflow treats both as hard failures.
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
