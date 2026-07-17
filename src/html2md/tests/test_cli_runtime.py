import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from typer.testing import CliRunner

from html2md import __version__
from html2md.cli import cli
from html2md.cli.runtime import build_header_config
from html2md.config.loader import DEFAULT_CONFIG


def test_cli_version_uses_installed_distribution_metadata():
    result = CliRunner().invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == version("html2md-cli") == __version__


def test_cli_import_does_not_read_or_validate_user_config(tmp_path):
    config_path = tmp_path / "invalid.json"
    config_path.write_text("{not valid json", encoding="utf-8")
    env = os.environ.copy()
    env["HTML2MD_CONFIG_PATH"] = str(config_path)

    result = subprocess.run(
        [sys.executable, "-c", "import html2md.cli.cli"],
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr


def test_deferred_cli_default_reads_config_each_time(monkeypatch):
    values = iter((17, 23))
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: {"cli_defaults": {"crawl": {"max_pages": next(values)}}},
    )
    resolve = cli.get_cli_default("crawl", "max_pages", 100)

    assert resolve() == 17
    assert resolve() == 23


def test_all_network_commands_share_one_header_config_factory():
    source = Path(cli.__file__).read_text(encoding="utf-8")
    conversion_source = (
        Path(cli.__file__)
        .with_name("conversion_service.py")
        .read_text(encoding="utf-8")
    )
    presenter_source = (
        Path(cli.__file__)
        .with_name("conversion_presenter.py")
        .read_text(encoding="utf-8")
    )

    assert source.count("build_header_config(") == 1
    assert conversion_source.count("build_header_config(") == 1
    assert presenter_source.count("def process_single_") == 2
    assert presenter_source.count("convert_source(") == 1
    assert "HeaderConfig(" not in source


def test_header_factory_uses_one_honest_default_identity():
    for _command in ("convert", "batch", "crawl"):
        header_config = build_header_config(
            DEFAULT_CONFIG,
            enhanced_headers=True,
            user_agent_contact="crawler@example.com",
        )
        assert header_config.user_agent_name == "html2md"
        assert header_config.contact_email == "crawler@example.com"
