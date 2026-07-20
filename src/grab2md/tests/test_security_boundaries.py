"""Security regressions for filesystem and diagnostic boundaries."""

import logging
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from grab2md.config.writer import atomic_write_json
from grab2md.cookies import database, session_manager
from grab2md.markdown.archive import OutputPlanner
from grab2md.markdown.crawler import crawl_website
from grab2md.network.request_handler import FetchResult
from grab2md.utils.redaction import (
    REDACTED,
    get_redacting_logger,
    redact_mapping,
    redact_text,
)
from grab2md.utils.logger import default_log_file
from grab2md.utils.state_manager import StateManager


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

    directory = OutputPlanner(output).plan(url)

    directory.relative_to(output.resolve())
    assert not (tmp_path / "outside").exists()


def test_output_containment_rejects_existing_symlink_escape(tmp_path):
    output = tmp_path / "output"
    outside = tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    (output / "example.com").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes configured root"):
        OutputPlanner(output).plan("https://example.com/page")


def test_crawler_traversal_url_cannot_write_outside_root(tmp_path):
    url = "https://example.com/%2e%2e/%2e%2e/escaped/page"
    response = FetchResult(url, url, status_code=200, body="<h1>Safe</h1>")
    output = tmp_path / "output"
    manager = StateManager(state_dir=tmp_path / "states")
    with patch("grab2md.markdown.crawler.fetch_html", return_value=response):
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


def test_redaction_covers_url_userinfo_presigned_keys_and_all_cookie_values():
    secrets = {
        "user-password",
        "oauth-code",
        "api-secret",
        "signed-value",
        "credential-value",
        "cookie-one",
        "cookie-two",
    }
    text = (
        "Failed https://user:user-password@example.com/callback"
        "?code=oauth-code&api_key=api-secret&safe=visible"
        "&X-Amz-Signature=signed-value"
        "&X-Amz-Credential=credential-value "
        "Cookie: a=cookie-one; b=cookie-two"
    )

    redacted = redact_text(text)

    assert not any(secret in redacted for secret in secrets)
    assert "safe=visible" in redacted
    assert "example.com/callback" in redacted
    assert redacted.count(REDACTED) >= 6


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode assertions")
def test_rotating_diagnostic_logs_are_private_and_structurally_redacted(tmp_path):
    log_path = tmp_path / "logs" / "grab2md.log"
    script = """
import logging
from logging.handlers import RotatingFileHandler
from grab2md.utils.logger import setup_logging

logger = setup_logging(console_output=False)
logger.error(
    "Failed URL %s Cookie: a=first-cookie; b=second-cookie",
    "https://user:user-password@example.com/cb?code=oauth-code&api_key=api-secret&safe=visible",
)
try:
    raise RuntimeError("request failed with token=exception-secret")
except RuntimeError:
    logger.exception("conversion exception")
handler = next(item for item in logger.handlers if isinstance(item, RotatingFileHandler))
handler.doRollover()
logger.error("Authorization: Bearer bearer-secret")
for item in logger.handlers:
    item.flush()
"""
    environment = os.environ.copy()
    environment["GRAB2MD_LOG_PATH"] = str(log_path)
    subprocess.run([sys.executable, "-c", script], env=environment, check=True)

    current = log_path.read_text(encoding="utf-8")
    rotated = log_path.with_suffix(".log.1").read_text(encoding="utf-8")
    combined = current + rotated

    for secret in (
        "first-cookie",
        "second-cookie",
        "user-password",
        "oauth-code",
        "api-secret",
        "bearer-secret",
        "exception-secret",
    ):
        assert secret not in combined
    assert "safe=visible" in rotated
    assert log_path.stat().st_mode & 0o777 == 0o600
    assert log_path.with_suffix(".log.1").stat().st_mode & 0o777 == 0o600
    assert log_path.parent.stat().st_mode & 0o777 == 0o700


def test_default_log_file_uses_per_user_platform_locations(tmp_path):
    assert (
        default_log_file(platform="linux", home=tmp_path, environ={})
        == tmp_path / ".local" / "state" / "grab2md" / "grab2md.log"
    )
    assert default_log_file(
        platform="linux",
        home=tmp_path,
        environ={"XDG_STATE_HOME": "/state"},
    ) == Path("/state/grab2md/grab2md.log")
    assert (
        default_log_file(platform="darwin", home=tmp_path, environ={})
        == tmp_path / "Library" / "Logs" / "grab2md" / "grab2md.log"
    )
    assert default_log_file(
        platform="win32",
        home=tmp_path,
        environ={"LOCALAPPDATA": "C:/Users/test/AppData/Local"},
    ) == Path("C:/Users/test/AppData/Local/grab2md/Logs/grab2md.log")


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode assertions")
def test_logging_secures_old_rotated_files_without_chmoding_custom_parent(tmp_path):
    log_directory = tmp_path / "shared-logs"
    log_directory.mkdir(mode=0o750)
    old_log = log_directory / "grab2md.log.1"
    old_log.write_text("old diagnostic\n", encoding="utf-8")
    old_log.chmod(0o644)
    log_path = log_directory / "grab2md.log"
    script = """
from grab2md.utils.logger import setup_logging
logger = setup_logging(console_output=False)
logger.error("rotation trigger")
for item in logger.handlers:
    item.flush()
"""
    environment = os.environ.copy()
    environment["GRAB2MD_LOG_PATH"] = str(log_path)

    subprocess.run([sys.executable, "-c", script], env=environment, check=True)

    assert log_directory.stat().st_mode & 0o777 == 0o750
    assert old_log.stat().st_mode & 0o777 == 0o600
    assert log_path.stat().st_mode & 0o777 == 0o600


def test_redacting_logger_sanitizes_every_log_level(caplog):
    logger = get_redacting_logger("grab2md.security-test")
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

    first_directory, first_copy = database.copy_cookie_database(source)
    second_directory, second_copy = database.copy_cookie_database(source)
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


def test_cookie_snapshot_includes_committed_wal_records(tmp_path):
    source = tmp_path / "cookies.sqlite"
    writer = sqlite3.connect(source)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE cookies (name TEXT NOT NULL)")
        writer.commit()
        writer.execute("INSERT INTO cookies VALUES ('wal-cookie')")
        writer.commit()

        with database.copied_cookie_connection(source) as snapshot:
            rows = snapshot.execute("SELECT name FROM cookies").fetchall()

        assert rows == [("wal-cookie",)]
    finally:
        writer.close()


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
            "grab2md.cookies.database.tempfile.TemporaryDirectory",
            return_value=fake_directory,
        ),
        pytest.raises(FileExistsError),
    ):
        database.copy_cookie_database(source)

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
    real_copy = database.copy_cookie_database

    def capture_copy(path):
        directory, copied = real_copy(path)
        captured["directory"] = Path(directory.name)
        return directory, copied

    with (
        patch(
            "grab2md.cookies.chrome.get_browser_cookie_path",
            return_value=source,
        ),
        patch(
            "grab2md.cookies.chrome.get_chrome_encryption_key",
            return_value=b"key",
        ),
        patch(
            "grab2md.cookies.database.copy_cookie_database",
            side_effect=capture_copy,
        ),
        patch("grab2md.cookies.database.sqlite3.connect", side_effect=failure),
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
    atomic_write_json(
        config_file,
        {"headers": {"custom_headers": {}}},
        private=True,
        private_parent=True,
    )
    os.chmod(config_file, 0o644)
    atomic_write_json(
        config_file,
        {"headers": {"custom_headers": {"X-Test": "updated"}}},
        private=True,
        private_parent=True,
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


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode assertions")
def test_state_export_preserves_caller_parent_permissions(tmp_path):
    manager = StateManager(state_dir=tmp_path / "states")
    state = manager.create_new_state("https://example.com", tmp_path / "out", {})
    shared_parent = tmp_path / "shared"
    shared_parent.mkdir()
    shared_parent.chmod(0o750)

    export_file = shared_parent / "crawl.json"
    manager.export_state(state.crawl_id, export_file)

    assert shared_parent.stat().st_mode & 0o777 == 0o750
    assert export_file.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX durability contract")
def test_atomic_writer_fsyncs_file_and_parent_directory(tmp_path):
    target = tmp_path / "state.json"
    with patch("grab2md.config.writer.os.fsync", wraps=os.fsync) as fsync:
        atomic_write_json(target, {"value": 1}, private=True)

    assert fsync.call_count == 2
