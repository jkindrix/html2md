"""
Tests for SSL verification control (--insecure / --no-verify-ssl).
"""

import logging
from unittest.mock import MagicMock

import pytest
import requests
from click.utils import strip_ansi
from typer.testing import CliRunner

import html2md.cookies.session_manager as session_manager
from html2md.cookies.session_manager import (
    disable_ssl_verification,
    get_session,
    reset_session,
)
from html2md.markdown.converter import html_to_markdown


@pytest.fixture(autouse=True)
def reset_warning_state(monkeypatch):
    """Reset the once-per-process warning flag so each test observes it fresh."""
    monkeypatch.setattr(session_manager, "_insecure_warning_emitted", False)


class TestGetSession:
    """Test session creation with SSL verification control."""

    def test_default_verifies_ssl(self):
        session = get_session()
        assert session.verify is True

    def test_explicit_verify_ssl_true(self):
        session = get_session(verify_ssl=True)
        assert session.verify is True

    def test_verify_ssl_false_disables_verification(self):
        session = get_session(verify_ssl=False)
        assert session.verify is False

    def test_verify_ssl_false_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="html2md"):
            get_session(verify_ssl=False)
        assert any(
            "SSL certificate verification is DISABLED" in record.message
            for record in caplog.records
        )

    def test_warning_emitted_only_once(self, caplog):
        with caplog.at_level(logging.WARNING, logger="html2md"):
            get_session(verify_ssl=False)
            get_session(verify_ssl=False)
        warnings = [
            record
            for record in caplog.records
            if "SSL certificate verification is DISABLED" in record.message
        ]
        assert len(warnings) == 1


class TestDisableSslVerification:
    """Test the disable_ssl_verification helper."""

    def test_disables_verification_in_place(self):
        session = requests.Session()
        assert session.verify is True
        result = disable_ssl_verification(session)
        assert session.verify is False
        assert result is session

    def test_idempotent(self):
        session = requests.Session()
        disable_ssl_verification(session)
        disable_ssl_verification(session)
        assert session.verify is False


class TestResetSession:
    """Test that reset_session preserves the verification setting."""

    def test_preserves_disabled_verification(self):
        session = get_session(verify_ssl=False)
        new_session = reset_session(session)
        assert new_session.verify is False

    def test_preserves_default_verification(self):
        session = get_session()
        new_session = reset_session(session)
        assert new_session.verify is True

    def test_preserves_custom_ca_bundle(self):
        session = get_session()
        session.verify = "/path/to/ca-bundle.pem"
        new_session = reset_session(session)
        assert new_session.verify == "/path/to/ca-bundle.pem"


class TestHtmlToMarkdownVerifySsl:
    """Test verify_ssl threading through html_to_markdown."""

    @staticmethod
    def _mock_session(html="<html><body><h1>Title</h1></body></html>"):
        session = MagicMock(spec=requests.Session)
        session.headers = {}
        response = MagicMock()
        response.text = html
        response.content = html.encode("utf-8")
        response.encoding = "utf-8"
        response.status_code = 200
        response.headers = {}
        session.get.return_value = response
        return session

    @pytest.fixture(autouse=True)
    def route_mock_session(self, monkeypatch):
        def request(session, _method, url, **kwargs):
            return session.get(
                url,
                headers=kwargs.get("headers"),
                timeout=kwargs.get("timeout"),
            )

        monkeypatch.setattr("html2md.markdown.converter.guarded_request", request)

    def test_verify_ssl_false_disables_on_provided_session(self):
        session = self._mock_session()
        html_to_markdown(
            "https://internal.example.com", session=session, verify_ssl=False
        )
        assert session.verify is False

    def test_default_leaves_provided_session_untouched(self):
        session = self._mock_session()
        session.verify = True
        html_to_markdown("https://internal.example.com", session=session)
        assert session.verify is True

    def test_ssl_error_returns_none(self, caplog):
        session = self._mock_session()
        session.get.side_effect = requests.exceptions.SSLError(
            "certificate verify failed: self-signed certificate"
        )
        with caplog.at_level(logging.ERROR, logger="html2md"):
            result = html_to_markdown("https://internal.example.com", session=session)
        assert result is None
        assert any(
            "SSL certificate verification failed" in record.message
            and "--insecure" in record.message
            for record in caplog.records
        )

    def test_connection_error_includes_details(self, caplog):
        session = self._mock_session()
        session.get.side_effect = requests.exceptions.ConnectionError(
            "connection refused"
        )
        with caplog.at_level(logging.ERROR, logger="html2md"):
            result = html_to_markdown("https://internal.example.com", session=session)
        assert result is None
        assert any(
            "Connection error" in record.message
            and "connection refused" in record.message
            for record in caplog.records
        )


class TestCliInsecureFlag:
    """Test that the CLI exposes the --insecure / --no-verify-ssl flag."""

    runner = CliRunner()

    @pytest.mark.parametrize("command", ["convert", "batch", "crawl"])
    def test_flag_in_help(self, command):
        from html2md.cli.cli import app

        result = self.runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
        # Rich wraps and truncates long option names in the help panel
        # (e.g. "--insecure,--no-…"), so only assert on the primary name
        # and cover the alias via parsing tests below.
        assert "--insecure" in strip_ansi(result.output)

    @pytest.mark.parametrize("flag", ["--insecure", "--no-verify-ssl"])
    def test_convert_accepts_flag(self, flag, monkeypatch):
        import html2md.cli.cli as cli
        from html2md.cli.cli import app

        captured = {}

        def fake_process(**kwargs):
            captured.update(kwargs)
            return True

        monkeypatch.setattr(cli, "process_single_quiet", fake_process)
        result = self.runner.invoke(app, ["convert", flag, "https://example.com"])
        assert result.exit_code == 0
        assert captured["insecure"] is True

    def test_convert_defaults_to_secure(self, monkeypatch):
        import html2md.cli.cli as cli
        from html2md.cli.cli import app

        captured = {}

        def fake_process(**kwargs):
            captured.update(kwargs)
            return True

        monkeypatch.setattr(cli, "process_single_quiet", fake_process)
        result = self.runner.invoke(app, ["convert", "https://example.com"])
        assert result.exit_code == 0
        assert captured["insecure"] is False
