"""Tests for honest outbound HTTP identity."""

import time

import pytest

from html2md import __version__
from html2md.network.header_manager import (
    HeaderConfig,
    HeaderManager,
    format_http_date,
    parse_http_date,
)


def test_default_identity_uses_installed_package_version_without_request_context():
    headers = HeaderManager().get_headers("https://example.com/page")

    assert headers["User-Agent"] == f"html2md/{__version__}"
    assert "Referer" not in headers
    assert "If-Modified-Since" not in headers
    assert not any(name.casefold().startswith("sec-") for name in headers)


def test_contact_identity_is_explicit_and_does_not_impersonate_a_browser():
    manager = HeaderManager(
        HeaderConfig(
            contact_email="admin@example.com",
            contact_url="https://example.com/crawler",
        )
    )

    user_agent = manager.get_headers("https://example.com")["User-Agent"]

    assert user_agent.startswith(f"html2md/{__version__}")
    assert "Contact: admin@example.com" in user_agent
    assert "Info: https://example.com/crawler" in user_agent
    assert "Mozilla" not in user_agent


def test_basic_identity_omits_optional_contact_but_still_identifies_the_tool():
    manager = HeaderManager(
        HeaderConfig(
            use_enhanced_user_agent=False,
            contact_email="admin@example.com",
        )
    )

    assert manager.get_headers("https://example.com")["User-Agent"] == (
        f"html2md/{__version__}"
    )


def test_compression_language_and_cache_policy_are_configurable():
    manager = HeaderManager(
        HeaderConfig(
            enable_compression=False,
            include_accept_language=False,
            respect_caching=False,
        )
    )
    headers = manager.get_headers("https://example.com")

    assert "Accept-Encoding" not in headers
    assert "Accept-Language" not in headers
    assert headers["Cache-Control"] == "no-cache"


def test_custom_headers_override_managed_values():
    manager = HeaderManager(
        HeaderConfig(custom_headers={"User-Agent": "explicit-client", "X-Test": "1"})
    )

    headers = manager.get_headers("https://example.com")

    assert headers["User-Agent"] == "explicit-client"
    assert headers["X-Test"] == "1"


def test_config_update_invalidates_cached_base_headers():
    manager = HeaderManager()
    manager.get_headers("https://example.com")
    manager.update_config(HeaderConfig(user_agent_name="archive-bot"))

    assert manager.get_headers("https://example.com")["User-Agent"] == (
        f"archive-bot/{__version__}"
    )


def test_config_summary_reports_only_implemented_policy():
    manager = HeaderManager(
        HeaderConfig(
            contact_email="crawler@example.com",
            custom_headers={"X-Test": "value"},
        )
    )

    assert manager.get_config_summary() == {
        "enhanced_user_agent": True,
        "contact_email": "crawler@example.com",
        "contact_url": None,
        "compression_enabled": True,
        "custom_headers_count": 1,
    }


def test_format_http_date_specific_time():
    assert format_http_date(1_700_000_000).endswith(" GMT")
    assert "2023" in format_http_date(1_700_000_000)


@pytest.mark.parametrize(
    "date_string",
    [
        "Wed, 15 Nov 2023 12:00:00 GMT",
        "Wednesday, 15-Nov-23 12:00:00 GMT",
        "Wed Nov 15 12:00:00 2023",
    ],
)
def test_parse_supported_http_dates(date_string):
    assert isinstance(parse_http_date(date_string), float)


def test_parse_invalid_http_date_returns_none():
    assert parse_http_date("invalid date string") is None


def test_http_date_round_trip_is_second_precision():
    original = time.time()
    parsed = parse_http_date(format_http_date(original))
    assert parsed is not None
    assert abs(original - parsed) < 1.0
