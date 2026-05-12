"""Tests for the User-Agent header construction."""

import re

import pytest

from kolide_mcp.client import (
    PRODUCT_NAME,
    KolideAPIError,
    KolideClient,
    _build_user_agent,
)


class TestBuildUserAgent:
    def test_full_sha_is_truncated_to_nine_chars(self):
        ua = _build_user_agent("af48dd0915c2e6b7d0e0f7c8a1b2c3d4e5f60718")
        assert ua == f"{PRODUCT_NAME}/sha:af48dd091"

    def test_short_sha_passed_through(self):
        ua = _build_user_agent("1a2b3c4")
        assert ua == f"{PRODUCT_NAME}/sha:1a2b3c4"

    def test_unknown_sha_emits_bare_product(self):
        ua = _build_user_agent("unknown")
        assert ua == PRODUCT_NAME

    def test_empty_sha_emits_bare_product(self):
        ua = _build_user_agent("")
        assert ua == PRODUCT_NAME

    def test_whitespace_sha_emits_bare_product(self):
        ua = _build_user_agent("   ")
        assert ua == PRODUCT_NAME

    def test_fork_sentinel_emits_fork_token(self):
        ua = _build_user_agent("fork")
        assert ua == f"{PRODUCT_NAME}/fork"

    def test_header_has_no_spaces(self):
        ua = _build_user_agent("af48dd091")
        assert " " not in ua

    def test_header_shape(self):
        ua = _build_user_agent("af48dd091")
        pattern = re.compile(rf"^{re.escape(PRODUCT_NAME)}/sha:[0-9a-f]{{1,9}}$")
        assert pattern.match(ua), f"User-Agent {ua!r} does not match expected shape"

    def test_product_name_contains_no_spaces(self):
        assert " " not in PRODUCT_NAME


class TestKolideClientUserAgent:
    def test_user_agent_class_attribute_starts_with_product_name(self):
        assert KolideClient.USER_AGENT.startswith(PRODUCT_NAME)

    def test_headers_include_user_agent(self, monkeypatch):
        monkeypatch.setattr("kolide_mcp.client.load_dotenv", lambda **_: None)
        monkeypatch.setenv("KOLIDE_API_KEY", "test-key")
        client = KolideClient()
        headers = client._get_headers()
        assert headers["User-Agent"] == KolideClient.USER_AGENT

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.setattr("kolide_mcp.client.load_dotenv", lambda **_: None)
        monkeypatch.delenv("KOLIDE_API_KEY", raising=False)
        client = KolideClient()
        with pytest.raises(KolideAPIError) as exc:
            client._get_headers()
        assert exc.value.status_code == 401


class TestBuildHookResolution:
    """Tests for hatch_build.resolve_main_sha (build-time SHA resolution)."""

    def test_falls_back_to_unknown_outside_git(self, monkeypatch, tmp_path):
        import hatch_build

        monkeypatch.setattr(hatch_build, "_run_git", lambda *a, **kw: None)
        assert hatch_build.resolve_main_sha(tmp_path) == "unknown"

    def test_ls_remote_result_used(self, monkeypatch, tmp_path):
        import hatch_build

        sha = "abcdef0123456789abcdef0123456789abcdef01"

        def fake_run_git(args, cwd):
            if args[:2] == ["remote", "get-url"]:
                return "https://github.com/kolide/device-trust-mcp-server.git"
            if args[0] == "ls-remote":
                return f"{sha}\trefs/heads/main"
            return None

        monkeypatch.setattr(hatch_build, "_run_git", fake_run_git)
        assert hatch_build.resolve_main_sha(tmp_path) == sha

    def test_non_upstream_origin_emits_fork(self, monkeypatch, tmp_path):
        import hatch_build

        def fake_run_git(args, cwd):
            if args[:2] == ["remote", "get-url"]:
                return "https://github.com/someone-else/device-trust-mcp-server.git"
            return "should-not-be-used"

        monkeypatch.setattr(hatch_build, "_run_git", fake_run_git)
        assert hatch_build.resolve_main_sha(tmp_path) == "fork"

    def test_ssh_upstream_origin_recognized(self, monkeypatch, tmp_path):
        import hatch_build

        sha = "0123456789abcdef0123456789abcdef01234567"

        def fake_run_git(args, cwd):
            if args[:2] == ["remote", "get-url"]:
                return "git@github.com:kolide/device-trust-mcp-server.git"
            if args[0] == "ls-remote":
                return f"{sha}\trefs/heads/main"
            return None

        monkeypatch.setattr(hatch_build, "_run_git", fake_run_git)
        assert hatch_build.resolve_main_sha(tmp_path) == sha

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/kolide/device-trust-mcp-server",
            "https://github.com/kolide/device-trust-mcp-server.git",
            "https://github.com/kolide/device-trust-mcp-server/",
            "https://github.com/KOLIDE/Device-Trust-MCP-Server.git",
            "git@github.com:kolide/device-trust-mcp-server.git",
            "ssh://git@github.com/kolide/device-trust-mcp-server.git",
        ],
    )
    def test_upstream_url_variants_recognized(self, monkeypatch, tmp_path, url):
        import hatch_build

        monkeypatch.setattr(hatch_build, "_run_git", lambda args, cwd: url)
        assert hatch_build._is_upstream_origin(tmp_path) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/someone/device-trust-mcp-server.git",
            "https://github.com/kolide/some-other-repo.git",
            "https://gitlab.com/kolide/device-trust-mcp-server.git",
            "https://example.com/github.com/kolide/device-trust-mcp-server",
        ],
    )
    def test_non_upstream_urls_rejected(self, monkeypatch, tmp_path, url):
        import hatch_build

        monkeypatch.setattr(hatch_build, "_run_git", lambda args, cwd: url)
        assert hatch_build._is_upstream_origin(tmp_path) is False
