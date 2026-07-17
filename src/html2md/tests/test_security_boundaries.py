"""Security regressions for filesystem and diagnostic boundaries."""

import logging
import os
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from html2md.config.writer import atomic_write_json
from html2md.cookies import session_manager
from html2md.markdown.batch_processor import create_directory_structure
from html2md.markdown.crawler import crawl_website
from html2md.network.request_handler import FetchResult
from html2md.utils.redaction import (
    REDACTED,
    get_redacting_logger,
    redact_mapping,
    redact_text,
)
from html2md.utils.state_manager import StateManager


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/../../../../outside/page",
        "https://example.com/%2e%2e/%2e%2e/outside/page",
        "https://example.com/%2F..%2F..%2Foutside/page",
    ],
)
def test_url_directories_remain_inside_output_root(tmp_path, url):
    output = tmp_path / "output"

    directory = Path(create_directory_structure(output, url))

    directory.relative_to(output.resolve())
    assert not (tmp_path / "outside").exists()


def test_output_containment_rejects_existing_symlink_escape(tmp_path):
    output = tmp_path / "output"
    outside = tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    (output / "example.com").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes configured root"):
        create_directory_structure(output, "https://example.com/page")


def test_crawler_traversal_url_cannot_write_outside_root(tmp_path):
    url = "https://example.com/%2e%2e/%2e%2e/escaped/page"
    response = FetchResult(url, url, status_code=200, body="<h1>Safe</h1>")
    output = tmp_path / "output"
    manager = StateManager(state_dir=tmp_path / "states")
    with (
        patch("html2md.markdown.crawler.fetch_html", return_value=response),
        patch(
            "html2md.markdown.crawler.html_content_to_markdown", return_value="# Safe"
        ),
    ):
        result = crawl_website(
            url,
            output,
            max_pages=1,
            max_depth=0,
            respect_robots=False,
            state_manager=manager,
        )

    assert result.success is True
    for generated_file in result.url_mapping.values():
        Path(generated_file).resolve().relative_to(output.resolve())
    assert not (tmp_path / "escaped").exists()


def test_redaction_covers_headers_tokens_passwords_and_url_queries():
    secret = "super-secret-value"
    text = (
        f"Authorization: Bearer {secret} password={secret} "
        f"https://example.com/?token={secret} Cookie: session={secret}"
    )

    redacted = redact_text(text)
    headers = redact_mapping(
        {
            "Authorization": f"Bearer {secret}",
            "Set-Cookie": secret,
            "Accept": "text/html",
        }
    )

    assert secret not in redacted
    assert redacted.count(REDACTED) >= 4
    assert headers["Authorization"] == REDACTED
    assert headers["Set-Cookie"] == REDACTED
    assert headers["Accept"] == "text/html"


def test_redacting_logger_sanitizes_every_log_level(caplog):
    logger = get_redacting_logger("html2md.security-test")
    secret = "level-secret"
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        for level in (
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        ):
            logger.log(level, "Authorization: Bearer %s", secret)

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in rendered
    assert rendered.count(REDACTED) >= 5


def test_private_cookie_copy_is_unique_owner_only_and_cleanup_is_explicit(tmp_path):
    source = tmp_path / "cookies.sqlite"
    source.write_bytes(b"sqlite fixture")

    first_directory, first_copy = session_manager._copy_cookie_database(source)
    second_directory, second_copy = session_manager._copy_cookie_database(source)
    try:
        assert first_copy != second_copy
        assert first_copy.read_bytes() == b"sqlite fixture"
        if os.name == "posix":
            assert first_copy.stat().st_mode & 0o777 == 0o600
            assert Path(first_directory.name).stat().st_mode & 0o777 == 0o700
    finally:
        first_path = Path(first_directory.name)
        second_path = Path(second_directory.name)
        first_directory.cleanup()
        second_directory.cleanup()

    assert not first_path.exists()
    assert not second_path.exists()


def test_cookie_copy_rejects_preexisting_symlink_destination(tmp_path):
    source = tmp_path / "source.sqlite"
    target = tmp_path / "target"
    temp_dir = tmp_path / "forced-temp"
    source.write_bytes(b"source")
    target.write_bytes(b"do not overwrite")
    temp_dir.mkdir()
    (temp_dir / "cookies.sqlite").symlink_to(target)

    fake_directory = Mock(name=str(temp_dir))
    fake_directory.name = str(temp_dir)
    fake_directory.cleanup.side_effect = lambda: shutil.rmtree(temp_dir)
    with (
        patch(
            "html2md.cookies.session_manager.tempfile.TemporaryDirectory",
            return_value=fake_directory,
        ),
        pytest.raises(FileExistsError),
    ):
        session_manager._copy_cookie_database(source)

    assert target.read_bytes() == b"do not overwrite"
    fake_directory.cleanup.assert_called_once()


@pytest.mark.parametrize(
    "failure", [RuntimeError("broken sqlite"), KeyboardInterrupt()]
)
def test_chrome_cookie_temp_storage_cleans_up_on_failure_and_interruption(
    tmp_path, failure
):
    source = tmp_path / "cookies.sqlite"
    source.write_bytes(b"fixture")
    captured = {}
    real_copy = session_manager._copy_cookie_database

    def capture_copy(path):
        directory, copied = real_copy(path)
        captured["directory"] = Path(directory.name)
        return directory, copied

    with (
        patch(
            "html2md.cookies.session_manager.get_browser_cookie_path",
            return_value=source,
        ),
        patch(
            "html2md.cookies.session_manager.get_chrome_encryption_key",
            return_value=b"key",
        ),
        patch(
            "html2md.cookies.session_manager._copy_cookie_database",
            side_effect=capture_copy,
        ),
        patch("html2md.cookies.session_manager.sqlite3.connect", side_effect=failure),
    ):
        if isinstance(failure, KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                session_manager.get_chrome_cookies("example.com")
        else:
            with pytest.raises(
                session_manager.CookieSourceError, match="broken sqlite"
            ):
                session_manager.get_chrome_cookies("example.com")

    assert not captured["directory"].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode assertions")
def test_private_config_and_state_use_owner_only_modes(tmp_path):
    config_file = tmp_path / "config" / "config.json"
    atomic_write_json(config_file, {"headers": {"custom_headers": {}}}, private=True)
    os.chmod(config_file, 0o644)
    atomic_write_json(
        config_file,
        {"headers": {"custom_headers": {"X-Test": "updated"}}},
        private=True,
    )
    assert config_file.stat().st_mode & 0o777 == 0o600
    assert config_file.parent.stat().st_mode & 0o777 == 0o700

    manager = StateManager(state_dir=tmp_path / "states")
    state = manager.create_new_state(
        "https://example.com/?token=secret", tmp_path / "out", {}
    )
    state_file = manager.state_dir / f"{state.crawl_id}.json"
    assert state_file.stat().st_mode & 0o777 == 0o600
    assert state_file.parent.stat().st_mode & 0o777 == 0o700
