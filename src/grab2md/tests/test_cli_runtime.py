import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

from typer.testing import CliRunner

from grab2md import __version__
import grab2md
from grab2md.cli import cli
from grab2md.cli.runtime import build_header_config
from grab2md.config.loader import DEFAULT_CONFIG


def test_cli_version_uses_installed_distribution_metadata():
    result = CliRunner().invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == version("grab2md") == __version__


def test_default_source_routing_preserves_root_options_and_real_commands():
    assert cli.route_default_source(["https://example.com", "-o", "page.md"]) == [
        "convert",
        "https://example.com",
        "-o",
        "page.md",
    ]
    assert cli.route_default_source(
        ["--log-level", "INFO", "page.html", "--local"]
    ) == ["--log-level", "INFO", "convert", "page.html", "--local"]
    assert cli.route_default_source(["crawl", "https://example.com"]) == [
        "crawl",
        "https://example.com",
    ]
    assert cli.route_default_source(["config", "show"]) == ["config", "show"]
    assert cli.route_default_source(["convert", "page.html"]) == [
        "convert",
        "page.html",
    ]
    assert cli.route_default_source(["--version"]) == ["--version"]


def test_root_help_presents_direct_sources_and_deemphasizes_convert_alias():
    result = CliRunner().invoke(cli.app, ["--help"])
    normalized_output = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "[SOURCE ...] | COMMAND [ARGS]..." in result.output
    assert "grab2md https://example.com" in result.output
    assert "grab2md page.html -o page.md" in normalized_output
    assert "grab2md page.html --local" not in normalized_output
    assert "\n│ convert" not in result.output

    alias_help = CliRunner().invoke(cli.app, ["convert", "--help"])
    assert alias_help.exit_code == 0
    assert "URLs or local HTML files to convert" in alias_help.output


def test_package_root_exports_only_version_metadata():
    assert grab2md.__all__ == ["__version__"]


def test_cli_import_does_not_read_or_validate_user_config(tmp_path):
    config_path = tmp_path / "invalid.json"
    config_path.write_text("{not valid json", encoding="utf-8")
    env = os.environ.copy()
    env["GRAB2MD_CONFIG_PATH"] = str(config_path)

    result = subprocess.run(
        [sys.executable, "-c", "import grab2md.cli.cli"],
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
    command_runtime_source = (
        Path(cli.__file__).with_name("command_runtime.py").read_text(encoding="utf-8")
    )

    assert source.count("build_header_config(") == 0
    assert command_runtime_source.count("build_header_config(") == 1
    assert command_runtime_source.count("build_header_manager(") == 1
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
        assert header_config.user_agent_name == "grab2md"
        assert header_config.contact_email == "crawler@example.com"
