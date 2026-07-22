"""Command-level tests for schema-backed CLI defaults."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from grab2md.cli.cli import app
from grab2md.config.loader import DEFAULT_CONFIG

runner = CliRunner()


def test_config_help_exposes_supported_command_surface():
    result = runner.invoke(app, ["config", "--help"])

    assert result.exit_code == 0
    for command in (
        "show",
        "path",
        "set",
        "get",
        "delete",
        "reset",
        "set-cli-default",
        "list-cli-defaults",
        "show-options",
        "backup",
        "list-backups",
        "restore",
    ):
        assert command in result.output


def test_config_show_renders_loaded_configuration():
    with patch(
        "grab2md.cli.config_commands.load_config",
        return_value={"browser": {"preferred": "firefox"}},
    ):
        result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "Configuration file" in result.output
    assert "firefox" in result.output


def test_config_set_updates_nested_value():
    config = {"browser": {"preferred": "chrome"}}
    save = Mock()
    with (
        patch("grab2md.cli.config_commands.load_config", return_value=config),
        patch("grab2md.cli.config_commands.save_config", save),
    ):
        result = runner.invoke(
            app,
            ["config", "set", "browser.preferred", '"firefox"'],
        )

    assert result.exit_code == 0
    assert save.call_args.args[0]["browser"]["preferred"] == "firefox"


def test_config_set_uses_schema_types_and_rejects_invalid_known_values():
    save = Mock()
    with (
        patch(
            "grab2md.cli.config_commands.load_config",
            side_effect=[deepcopy(DEFAULT_CONFIG), deepcopy(DEFAULT_CONFIG)],
        ),
        patch("grab2md.cli.config_commands.save_config", save),
    ):
        typed = runner.invoke(
            app,
            ["config", "set", "headers.enhanced_user_agent", "false"],
        )
        invalid = runner.invoke(
            app,
            ["config", "set", "browser.preferred", "opera"],
        )

    assert typed.exit_code == 0
    assert save.call_args.args[0]["headers"]["enhanced_user_agent"] is False
    assert invalid.exit_code == 1
    assert "must be one of" in invalid.output
    assert save.call_count == 1


def test_config_backup_reports_created_path(tmp_path):
    manager = Mock()
    manager.create_backup.return_value = tmp_path / "config.backup.json"
    with patch("grab2md.cli.config_commands.get_backup_manager", return_value=manager):
        result = runner.invoke(app, ["config", "backup"])

    assert result.exit_code == 0
    assert "Backup created" in result.output
    manager.create_backup.assert_called_once_with(reason="manual")


def test_config_restore_uses_explicit_backup(tmp_path):
    backup = tmp_path / "config.backup.json"
    backup.write_text("{}", encoding="utf-8")
    manager = Mock()
    manager.create_backup.return_value = Path("pre-restore.json")
    manager.restore_backup.return_value = True
    with patch("grab2md.cli.config_commands.get_backup_manager", return_value=manager):
        result = runner.invoke(app, ["config", "restore", str(backup)], input="y\n")

    assert result.exit_code == 0
    assert "restored successfully" in result.output
    manager.restore_backup.assert_called_once_with(backup)


def test_config_path_and_options_render_without_loading_state():
    path_result = runner.invoke(app, ["config", "path"])
    options_result = runner.invoke(app, ["config", "show-options"])

    assert path_result.exit_code == 0
    assert "Configuration file" in path_result.output
    assert options_result.exit_code == 0
    assert "CLI Defaults" in options_result.output
    assert "content_mode" in options_result.output
    assert "Browser Configuration" in options_result.output


def test_show_options_is_derived_from_every_cli_default():
    result = runner.invoke(app, ["config", "show-options"])

    assert result.exit_code == 0
    for options in DEFAULT_CONFIG["cli_defaults"].values():
        for option in options:
            assert option in result.output


def test_config_get_handles_values_and_invalid_paths():
    config = {"browser": {"preferred": "firefox"}, "scalar": 3}
    with patch("grab2md.cli.config_commands.load_config", return_value=config):
        found = runner.invoke(app, ["config", "get", "browser.preferred"])
        missing = runner.invoke(app, ["config", "get", "browser.missing"])
        blocked = runner.invoke(app, ["config", "get", "scalar.child"])

    assert found.exit_code == 0
    assert "firefox" in found.output
    assert "not found" in missing.output
    assert "not a dictionary" in blocked.output


def test_config_set_handles_plain_strings_and_invalid_parent():
    save = Mock()
    with (
        patch(
            "grab2md.cli.config_commands.load_config",
            side_effect=[{"custom": {}}, {"custom": "scalar"}],
        ),
        patch("grab2md.cli.config_commands.save_config", save),
    ):
        plain = runner.invoke(app, ["config", "set", "custom.label", "plain"])
        blocked = runner.invoke(app, ["config", "set", "custom.label", "plain"])

    assert plain.exit_code == 0
    assert save.call_args.args[0]["custom"]["label"] == "plain"
    assert "not a dictionary" in blocked.output


@pytest.mark.parametrize("path", ["", ".browser", "browser.", "browser..preferred"])
def test_config_commands_reject_empty_path_components(path):
    save = Mock()
    with (
        patch("grab2md.cli.config_commands.load_config", return_value={}),
        patch("grab2md.cli.config_commands.save_config", save),
    ):
        result = runner.invoke(app, ["config", "set", path, "value"])

    assert result.exit_code == 1
    assert "empty components" in result.output
    save.assert_not_called()


def test_config_delete_confirms_or_preserves_value():
    save = Mock()
    with (
        patch(
            "grab2md.cli.config_commands.load_config",
            side_effect=[
                {"custom": {"label": "value"}},
                {"custom": {"label": "value"}},
            ],
        ),
        patch("grab2md.cli.config_commands.save_config", save),
    ):
        deleted = runner.invoke(app, ["config", "delete", "custom.label"], input="y\n")
        cancelled = runner.invoke(
            app, ["config", "delete", "custom.label"], input="n\n"
        )

    assert deleted.exit_code == 0
    assert "Deleted" in deleted.output
    assert cancelled.exit_code == 0
    save.assert_called_once()


def test_config_reset_cancellation_and_success():
    manager = Mock()
    manager.create_backup.return_value = Path("reset-backup.json")
    save = Mock()
    with (
        patch("grab2md.cli.config_commands.get_backup_manager", return_value=manager),
        patch("grab2md.cli.config_commands.save_config", save),
    ):
        cancelled = runner.invoke(app, ["config", "reset"], input="n\n")
        reset = runner.invoke(app, ["config", "reset"], input="y\n")

    assert "Reset cancelled" in cancelled.output
    assert "reset to default" in reset.output
    save.assert_called_once_with(DEFAULT_CONFIG)


def test_config_cli_default_listing_handles_empty_and_populated_state():
    with patch(
        "grab2md.cli.config_commands.load_config",
        side_effect=[
            {"cli_defaults": {}},
            {"cli_defaults": {"convert": {"content_mode": "main"}}},
        ],
    ):
        empty = runner.invoke(app, ["config", "list-cli-defaults"])
        populated = runner.invoke(app, ["config", "list-cli-defaults"])

    assert "No CLI defaults" in empty.output
    assert "Direct Conversion Defaults (`convert` namespace)" in populated.output
    assert "--content-mode" in populated.output


def test_config_backup_and_restore_failure_contracts():
    manager = Mock()
    manager.create_backup.return_value = None
    manager.list_backups.return_value = []
    with patch("grab2md.cli.config_commands.get_backup_manager", return_value=manager):
        backup = runner.invoke(app, ["config", "backup"])
        listing = runner.invoke(app, ["config", "list-backups"])
        restore = runner.invoke(app, ["config", "restore"])

    assert backup.exit_code == 1
    assert "Failed to create backup" in backup.output
    assert "No backups found" in listing.output
    assert restore.exit_code == 1
    assert "No backups available" in restore.output


@pytest.mark.parametrize(
    "command, option, raw, expected",
    [
        ("convert", "content_mode", "main", "main"),
        ("crawl", "max_pages", "250", 250),
        ("crawl", "delay", "1.5", 1.5),
        ("crawl", "rate_limit", "30", 30),
        ("crawl", "rate_limit", "null", None),
        ("convert", "browser", "firefox", "firefox"),
        ("convert", "images_dir", "page-assets", "page-assets"),
    ],
)
def test_set_cli_default_parses_and_saves_schema_type(command, option, raw, expected):
    config = deepcopy(DEFAULT_CONFIG)
    save = Mock()

    with (
        patch("grab2md.cli.config_commands.load_config", return_value=config),
        patch("grab2md.cli.config_commands.save_config", save),
    ):
        result = runner.invoke(app, ["config", "set-cli-default", command, option, raw])

    assert result.exit_code == 0
    if command == "convert":
        assert "when using 'grab2md SOURCE'" in " ".join(result.output.split())
    saved = save.call_args.args[0]
    assert saved["cli_defaults"][command][option] == expected
    assert type(saved["cli_defaults"][command][option]) is type(expected)


def test_set_cli_default_reset_restores_builtin_value():
    config = deepcopy(DEFAULT_CONFIG)
    config["cli_defaults"]["crawl"]["max_pages"] = 999
    save = Mock()

    with (
        patch("grab2md.cli.config_commands.load_config", return_value=config),
        patch("grab2md.cli.config_commands.save_config", save),
    ):
        result = runner.invoke(
            app, ["config", "set-cli-default", "crawl", "max_pages", "--reset"]
        )

    assert result.exit_code == 0
    assert save.call_args.args[0]["cli_defaults"]["crawl"]["max_pages"] == 100


@pytest.mark.parametrize(
    "arguments",
    [
        ["convert", "content_mode", "sometimes"],
        ["crawl", "max_pages", "1.5"],
        ["crawl", "rate_limit", "fast"],
        ["convert", "browser", "opera"],
        ["crawl", "missing", "1"],
        ["missing", "content_mode", "main"],
        ["crawl", "max_pages"],
        ["crawl", "max_pages", "10", "--reset"],
    ],
)
def test_set_cli_default_rejects_invalid_input_without_saving(arguments):
    save = Mock()
    with (
        patch(
            "grab2md.cli.config_commands.load_config",
            return_value=deepcopy(DEFAULT_CONFIG),
        ),
        patch("grab2md.cli.config_commands.save_config", save),
    ):
        result = runner.invoke(app, ["config", "set-cli-default", *arguments])

    assert result.exit_code == 1
    assert "Error" in result.output
    save.assert_not_called()
