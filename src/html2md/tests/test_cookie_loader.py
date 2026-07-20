"""Behavior tests for exported and browser-derived cookie loading."""

import json
import importlib
import os
import sqlite3
import sys
from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
import pytest

from html2md.cookies.session_manager import (
    CookieRecord,
    CookieSourceError,
    apply_browser_cookies,
    decrypt_chrome_cookie,
    get_browser_cookie_path,
    get_chrome_cookies,
    get_chrome_encryption_key,
    get_domain_cookies,
    get_firefox_cookies,
    load_cookies_from_json,
)
from html2md.cookies.firefox import find_firefox_profile


def write_private_cookie_file(path, payload, *, encode=True):
    contents = json.dumps(payload) if encode else payload
    path.write_text(contents, encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)
    return path


def test_exported_cookie_list_filters_exact_hosts_and_real_subdomains(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    write_private_cookie_file(
        cookie_file,
        [
            {"name": "parent", "value": "a", "domain": ".example.com"},
            {"name": "exact", "value": "b", "domain": "docs.example.com"},
            {"name": "other", "value": "c", "domain": "notexample.com"},
        ],
    )
    cookies = load_cookies_from_json(cookie_file, "https://docs.example.com/page")

    assert [(cookie.name, cookie.domain, cookie.host_only) for cookie in cookies] == [
        ("parent", ".example.com", False),
        ("exact", "docs.example.com", True),
    ]


def test_exported_cookie_dict_requires_target_and_creates_host_only_records(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    write_private_cookie_file(cookie_file, {"session": "token", "theme": "dark"})

    with pytest.raises(CookieSourceError, match="target URL"):
        load_cookies_from_json(cookie_file)
    cookies = load_cookies_from_json(cookie_file, "https://example.com")
    assert [(item.name, item.domain, item.host_only) for item in cookies] == [
        ("session", "example.com", True),
        ("theme", "example.com", True),
    ]


def test_malformed_cookie_export_fails_explicitly(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    write_private_cookie_file(cookie_file, "not-json", encode=False)

    with pytest.raises(CookieSourceError, match="Could not load cookie export"):
        load_cookies_from_json(cookie_file, "https://example.com")


def test_empty_cookie_export_fails_before_unauthenticated_fallback(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    write_private_cookie_file(cookie_file, [])

    with pytest.raises(CookieSourceError, match="No applicable cookies"):
        apply_browser_cookies(
            requests.Session(), "https://example.com", cookie_json=cookie_file
        )


def test_unsupported_browser_fails_explicitly():
    with pytest.raises(CookieSourceError, match="chrome and firefox"):
        get_domain_cookies("https://example.com", browser="safari")


def test_apply_cookie_export_preserves_domain_and_path(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    write_private_cookie_file(
        cookie_file,
        [
            {
                "name": "session",
                "value": "secret",
                "domain": ".example.com",
                "path": "/docs",
            }
        ],
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


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
def test_cookie_export_rejects_group_or_world_access(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text('{"session":"secret"}', encoding="utf-8")
    cookie_file.chmod(0o640)

    with pytest.raises(CookieSourceError, match="chmod 600"):
        load_cookies_from_json(cookie_file, "https://example.com")


def test_cookie_export_rejects_symlinks(tmp_path):
    target = write_private_cookie_file(tmp_path / "target.json", {"session": "secret"})
    cookie_file = tmp_path / "cookies.json"
    cookie_file.symlink_to(target)

    with pytest.raises(CookieSourceError, match="regular file"):
        load_cookies_from_json(cookie_file, "https://example.com")


def test_browser_cookie_mapping_is_applied_to_target_host():
    session = requests.Session()
    source = Mock(name="chrome_source")
    source.name = "chrome"
    source.load.return_value = {"session": "value"}
    with patch("html2md.cookies.sources.browser_cookie_source", return_value=source):
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
    source = Mock(name="chrome_source")
    source.name = "chrome"
    source.load.return_value = [
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
    ]
    with patch("html2md.cookies.sources.browser_cookie_source", return_value=source):
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
    source = Mock(name="firefox_source")
    source.name = "firefox"
    source.load.return_value = {"session": "value"}
    with patch(
        "html2md.cookies.sources.browser_cookie_source", return_value=source
    ) as select:
        session = apply_browser_cookies(
            session, "https://example.com/page", browser="firefox"
        )

    select.assert_called_once_with("firefox", None)
    source.load.assert_called_once_with("https://example.com/page")


def test_domain_cookie_loader_routes_to_configured_browser():
    with (
        patch(
            "html2md.cookies.sources.load_config",
            return_value={"browser": {"preferred": "firefox"}},
        ),
        patch(
            "html2md.cookies.firefox.get_firefox_cookies",
            return_value=[
                CookieRecord("firefox", "cookie", "www.example.com", host_only=True)
            ],
        ) as firefox,
    ):
        result = get_domain_cookies("https://www.example.com/path")

    assert result == [
        CookieRecord("firefox", "cookie", "www.example.com", host_only=True)
    ]
    firefox.assert_called_once_with("www.example.com", cookie_path=None)


def test_browser_source_selection_reads_configuration_at_call_time():
    from html2md.cookies.sources import ChromeCookieSource, FirefoxCookieSource

    with patch(
        "html2md.cookies.sources.load_config",
        side_effect=[
            {"browser": {"preferred": "chrome"}},
            {"browser": {"preferred": "firefox"}},
        ],
    ):
        from html2md.cookies.sources import browser_cookie_source

        assert isinstance(browser_cookie_source(), ChromeCookieSource)
        assert isinstance(browser_cookie_source(), FirefoxCookieSource)


def test_cookie_module_does_not_load_configuration_during_import():
    import html2md.config.loader as config_loader
    import html2md.cookies.session_manager as module

    with patch.object(config_loader, "load_config") as load:
        importlib.reload(module)

    load.assert_not_called()


def test_exported_cookie_source_reports_capability_without_loading(tmp_path):
    from html2md.cookies.sources import ExportedCookieSource

    source = ExportedCookieSource(tmp_path / "cookies.json")
    assert source.capability().available is False
    source.path.write_text("[]", encoding="utf-8")
    capability = source.capability()
    assert capability.available is True
    assert capability.name == "exported JSON"


def test_macos_chrome_source_fails_closed_before_cookie_decryption(tmp_path):
    from html2md.cookies.sources import ChromeCookieSource
    import html2md.cookies.session_manager as session_manager

    database = tmp_path / "Cookies"
    database.write_bytes(b"fixture")
    with (
        patch("html2md.cookies.sources.sys.platform", "darwin"),
        patch(
            "html2md.cookies.browser_paths.get_browser_cookie_path",
            return_value=database,
        ),
    ):
        capability = ChromeCookieSource().capability()

    assert capability.available is False
    assert "unavailable on macOS" in capability.detail

    with patch("html2md.cookies.chrome.sys.platform", "darwin"):
        with pytest.raises(CookieSourceError, match="owner-private JSON"):
            session_manager.get_chrome_encryption_key()


@pytest.mark.parametrize(
    ("platform", "browser", "relative_path"),
    [
        (
            "win32",
            "chrome",
            "AppData/Local/Google/Chrome/User Data/Default/Network/Cookies",
        ),
        ("win32", "firefox", "AppData/Roaming/Mozilla/Firefox/Profiles"),
        (
            "darwin",
            "chrome",
            "Library/Application Support/Google/Chrome/Default/Cookies",
        ),
        ("darwin", "firefox", "Library/Application Support/Firefox/Profiles"),
        ("linux", "chrome", ".config/google-chrome/Default/Cookies"),
        ("linux", "firefox", ".mozilla/firefox"),
    ],
)
def test_browser_cookie_default_paths_are_explicit_platform_contracts(
    tmp_path, platform, browser, relative_path
):
    with (
        patch("html2md.cookies.browser_paths.load_config", return_value={}),
        patch("html2md.cookies.browser_paths.sys.platform", platform),
        patch("html2md.cookies.browser_paths.Path.home", return_value=tmp_path),
    ):
        path = get_browser_cookie_path(browser)

    assert path == tmp_path / relative_path


@pytest.mark.parametrize(
    ("platform", "platform_name"), [("darwin", "macOS"), ("linux", "Linux")]
)
def test_chrome_capability_rejects_unimplemented_key_stores(
    tmp_path, platform, platform_name
):
    from html2md.cookies.sources import ChromeCookieSource

    database = tmp_path / "Cookies"
    database.write_bytes(b"fixture")
    with (
        patch("html2md.cookies.sources.sys.platform", platform),
        patch(
            "html2md.cookies.browser_paths.get_browser_cookie_path",
            return_value=database,
        ),
    ):
        capability = ChromeCookieSource().capability()

    assert capability.available is False
    assert platform_name in capability.detail
    assert "exported cookie JSON" in capability.detail


def test_windows_chrome_capability_probes_the_key_boundary(tmp_path):
    from html2md.cookies.sources import ChromeCookieSource

    database = tmp_path / "Cookies"
    database.write_bytes(b"fixture")
    with (
        patch("html2md.cookies.sources.sys.platform", "win32"),
        patch(
            "html2md.cookies.browser_paths.get_browser_cookie_path",
            return_value=database,
        ),
        patch(
            "html2md.cookies.chrome.get_chrome_encryption_key",
            side_effect=CookieSourceError("DPAPI permission denied"),
        ) as retrieve_key,
    ):
        capability = ChromeCookieSource().capability()

    assert capability.available is False
    assert capability.detail == "DPAPI permission denied"
    retrieve_key.assert_called_once_with()


def test_windows_chrome_key_decodes_and_removes_dpapi_prefix(tmp_path):
    local_state = tmp_path / "AppData/Local/Google/Chrome/User Data/Local State"
    local_state.parent.mkdir(parents=True)
    local_state.write_text(
        json.dumps(
            {"os_crypt": {"encrypted_key": b64encode(b"DPAPIwrapped").decode()}}
        ),
        encoding="utf-8",
    )
    crypt = SimpleNamespace(
        CryptUnprotectData=Mock(return_value=(None, b"decrypted-key"))
    )
    with (
        patch("html2md.cookies.chrome.sys.platform", "win32"),
        patch("html2md.cookies.chrome.Path.home", return_value=tmp_path),
        patch.dict(sys.modules, {"win32crypt": crypt}),
    ):
        key = get_chrome_encryption_key()

    assert key == b"decrypted-key"
    assert crypt.CryptUnprotectData.call_args.args[0] == b"wrapped"


def test_chrome_app_bound_cookie_format_fails_explicitly():
    with pytest.raises(CookieSourceError, match="app-bound"):
        decrypt_chrome_cookie(b"v20opaque", b"unused")


def _create_chrome_database(path: Path):
    connection = sqlite3.connect(path)
    connection.execute("""
        CREATE TABLE cookies (
            name TEXT, value TEXT, encrypted_value BLOB, host_key TEXT,
            expires_utc INTEGER, path TEXT, is_secure INTEGER, is_httponly INTEGER
        )
        """)
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
            "html2md.cookies.chrome.get_browser_cookie_path",
            return_value=database,
        ),
        patch(
            "html2md.cookies.chrome.get_chrome_encryption_key",
            return_value=b"key",
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
    firefox_root = tmp_path / "firefox"
    profile = firefox_root / "profile"
    profile.mkdir(parents=True)
    (firefox_root / "profiles.ini").write_text(
        "[Profile0]\nDefault=1\nIsRelative=1\nPath=profile\n",
        encoding="utf-8",
    )
    database = profile / "cookies.sqlite"
    connection = sqlite3.connect(database)
    connection.execute("""
        CREATE TABLE moz_cookies (
            name TEXT, value TEXT, host TEXT, expiry INTEGER, path TEXT,
            isSecure INTEGER, isHttpOnly INTEGER
        )
        """)
    future = int(datetime.now(timezone.utc).timestamp() + 3600)
    connection.executemany(
        "INSERT INTO moz_cookies VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("malformed", "ignored", ".example.com", "not-a-time", "/", 0, 0),
            ("shared", "good", ".example.com", future, "/", 1, 1),
            ("lookalike", "bad", "evilexample.com", future, "/", 0, 0),
        ],
    )
    connection.commit()
    connection.close()

    with (
        patch(
            "html2md.cookies.firefox.get_browser_cookie_path",
            return_value=firefox_root,
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


def test_firefox_profile_selection_prefers_install_default_over_relative_profiles(
    tmp_path,
):
    firefox_root = tmp_path / "firefox"
    relative = firefox_root / "Profiles" / "relative"
    profile_default = firefox_root / "Profiles" / "profile-default"
    install_default = firefox_root / "Profiles" / "install-default"
    for profile in (relative, profile_default, install_default):
        profile.mkdir(parents=True)
    (firefox_root / "profiles.ini").write_text(
        """[InstallABC]
Default=Profiles/install-default
Locked=1

[Profile0]
IsRelative=1
Path=Profiles/relative

[Profile1]
Default=1
IsRelative=1
Path=Profiles/profile-default
""",
        encoding="utf-8",
    )

    assert find_firefox_profile(firefox_root) == install_default


def test_firefox_profile_selection_reads_install_defaults_from_installs_ini(tmp_path):
    firefox_root = tmp_path / "firefox"
    selected = firefox_root / "Profiles" / "selected"
    selected.mkdir(parents=True)
    (firefox_root / "installs.ini").write_text(
        "[ABC]\nDefault=Profiles/selected\nLocked=1\n",
        encoding="utf-8",
    )

    assert find_firefox_profile(firefox_root) == selected
