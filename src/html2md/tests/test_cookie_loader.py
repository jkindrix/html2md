"""Behavior tests for exported and browser-derived cookie loading."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import requests
import pytest

from html2md.cookies.session_manager import (
    CookieRecord,
    CookieSourceError,
    apply_browser_cookies,
    get_chrome_cookies,
    get_domain_cookies,
    get_firefox_cookies,
    load_cookies_from_json,
)


def test_exported_cookie_list_filters_exact_hosts_and_real_subdomains(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(
        json.dumps(
            [
                {"name": "parent", "value": "a", "domain": ".example.com"},
                {"name": "exact", "value": "b", "domain": "docs.example.com"},
                {"name": "other", "value": "c", "domain": "notexample.com"},
            ]
        ),
        encoding="utf-8",
    )

    cookies = load_cookies_from_json(cookie_file, "https://docs.example.com/page")

    assert [(cookie.name, cookie.domain, cookie.host_only) for cookie in cookies] == [
        ("parent", ".example.com", False),
        ("exact", "docs.example.com", True),
    ]


def test_exported_cookie_dict_requires_target_and_creates_host_only_records(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(json.dumps({"session": "token", "theme": "dark"}))

    with pytest.raises(CookieSourceError, match="target URL"):
        load_cookies_from_json(cookie_file)
    cookies = load_cookies_from_json(cookie_file, "https://example.com")
    assert [(item.name, item.domain, item.host_only) for item in cookies] == [
        ("session", "example.com", True),
        ("theme", "example.com", True),
    ]


def test_malformed_cookie_export_fails_explicitly(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text("not-json", encoding="utf-8")

    with pytest.raises(CookieSourceError, match="Could not load cookie export"):
        load_cookies_from_json(cookie_file, "https://example.com")


def test_empty_cookie_export_fails_before_unauthenticated_fallback(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text("[]", encoding="utf-8")

    with pytest.raises(CookieSourceError, match="No applicable cookies"):
        apply_browser_cookies(
            requests.Session(), "https://example.com", cookie_json=cookie_file
        )


def test_unsupported_browser_fails_explicitly():
    with pytest.raises(CookieSourceError, match="chrome and firefox"):
        get_domain_cookies("https://example.com", browser="safari")


def test_apply_cookie_export_preserves_domain_and_path(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(
        json.dumps(
            [
                {
                    "name": "session",
                    "value": "secret",
                    "domain": ".example.com",
                    "path": "/docs",
                }
            ]
        ),
        encoding="utf-8",
    )
    session = requests.Session()

    returned = apply_browser_cookies(
        session, "https://docs.example.com/docs/page", cookie_file
    )

    assert returned is not session
    cookie = next(iter(returned.cookies))
    assert (cookie.name, cookie.value, cookie.domain, cookie.path) == (
        "session",
        "secret",
        ".example.com",
        "/docs",
    )


def test_browser_cookie_mapping_is_applied_to_target_host():
    session = requests.Session()
    with patch(
        "html2md.cookies.session_manager.get_domain_cookies",
        return_value={"session": "value"},
    ):
        session = apply_browser_cookies(session, "https://example.com/page")

    cookie = next(iter(session.cookies))
    assert (cookie.name, cookie.value, cookie.domain) == (
        "session",
        "value",
        "example.com",
    )

    subdomain_request = session.prepare_request(
        requests.Request("GET", "https://child.example.com/")
    )
    assert "Cookie" not in subdomain_request.headers


def test_scoped_cookie_session_enforces_domain_path_secure_and_expiry():
    session = requests.Session()
    with patch(
        "html2md.cookies.session_manager.get_domain_cookies",
        return_value=[
            CookieRecord("parent", "yes", ".example.com", host_only=False),
            CookieRecord(
                "secure",
                "yes",
                ".example.com",
                path="/private",
                secure=True,
                host_only=False,
            ),
            CookieRecord(
                "expired",
                "no",
                ".example.com",
                expires=1,
                host_only=False,
            ),
        ],
    ):
        session = apply_browser_cookies(session, "https://docs.example.com/private")

    https_request = session.prepare_request(
        requests.Request("GET", "https://child.example.com/private/page")
    )
    assert https_request.headers["Cookie"] == "secure=yes; parent=yes"

    http_request = session.prepare_request(
        requests.Request("GET", "http://child.example.com/private/page")
    )
    assert http_request.headers["Cookie"] == "parent=yes"

    other_path = session.prepare_request(
        requests.Request("GET", "https://child.example.com/public")
    )
    assert other_path.headers["Cookie"] == "parent=yes"


def test_browser_cookie_mapping_honors_explicit_browser():
    session = requests.Session()
    with patch(
        "html2md.cookies.session_manager.get_domain_cookies",
        return_value={"session": "value"},
    ) as extract:
        session = apply_browser_cookies(
            session, "https://example.com/page", browser="firefox"
        )

    extract.assert_called_once_with("https://example.com/page", browser="firefox")


def test_domain_cookie_loader_routes_to_configured_browser():
    with (
        patch.dict(
            "html2md.cookies.session_manager.config",
            {"browser": {"preferred": "firefox"}},
            clear=True,
        ),
        patch(
            "html2md.cookies.session_manager.get_firefox_cookies",
            return_value=[
                CookieRecord("firefox", "cookie", "www.example.com", host_only=True)
            ],
        ) as firefox,
    ):
        result = get_domain_cookies("https://www.example.com/path")

    assert result == [
        CookieRecord("firefox", "cookie", "www.example.com", host_only=True)
    ]
    firefox.assert_called_once_with("www.example.com")


class _CopiedDatabase:
    def cleanup(self):
        return None


def _create_chrome_database(path: Path):
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE cookies (
            name TEXT, value TEXT, encrypted_value BLOB, host_key TEXT,
            expires_utc INTEGER, path TEXT, is_secure INTEGER, is_httponly INTEGER
        )
        """
    )
    future = int(
        (datetime.now(timezone.utc).timestamp() + 3600 + 11_644_473_600) * 1_000_000
    )
    connection.executemany(
        "INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("exact", "one", b"", "docs.example.com", future, "/", 1, 1),
            ("shared", "two", b"", ".example.com", future, "/docs", 0, 0),
            ("shared", "three", b"", ".example.com", future, "/other", 0, 0),
            ("lookalike", "bad", b"", "evilexample.com", future, "/", 0, 0),
        ],
    )
    connection.commit()
    connection.close()


def test_chrome_lookup_enforces_boundaries_and_preserves_scope(tmp_path):
    database = tmp_path / "Cookies"
    _create_chrome_database(database)

    with (
        patch(
            "html2md.cookies.session_manager.get_browser_cookie_path",
            return_value=database,
        ),
        patch(
            "html2md.cookies.session_manager.get_chrome_encryption_key",
            return_value=b"key",
        ),
        patch(
            "html2md.cookies.session_manager._copy_cookie_database",
            return_value=(_CopiedDatabase(), database),
        ),
    ):
        records = get_chrome_cookies("docs.example.com")

    assert [(item.name, item.value, item.domain, item.path) for item in records] == [
        ("exact", "one", "docs.example.com", "/"),
        ("shared", "two", ".example.com", "/docs"),
        ("shared", "three", ".example.com", "/other"),
    ]
    assert records[0].secure is True
    assert records[0].http_only is True


def test_firefox_lookup_enforces_boundaries_and_preserves_scope(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    (tmp_path / "profiles.ini").write_text(
        "[Profile0]\nDefault=1\nIsRelative=1\nPath=profile\n",
        encoding="utf-8",
    )
    database = profile / "cookies.sqlite"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE moz_cookies (
            name TEXT, value TEXT, host TEXT, expiry INTEGER, path TEXT,
            isSecure INTEGER, isHttpOnly INTEGER
        )
        """
    )
    future = int(datetime.now(timezone.utc).timestamp() + 3600)
    connection.executemany(
        "INSERT INTO moz_cookies VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("shared", "good", ".example.com", future, "/", 1, 1),
            ("lookalike", "bad", "evilexample.com", future, "/", 0, 0),
        ],
    )
    connection.commit()
    connection.close()

    with (
        patch(
            "html2md.cookies.session_manager.get_browser_cookie_path",
            return_value=profile,
        ),
        patch(
            "html2md.cookies.session_manager._copy_cookie_database",
            return_value=(_CopiedDatabase(), database),
        ),
    ):
        records = get_firefox_cookies("docs.example.com")

    assert records == [
        CookieRecord(
            "shared",
            "good",
            ".example.com",
            secure=True,
            http_only=True,
            expires=future,
            host_only=False,
        )
    ]
