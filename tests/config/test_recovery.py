"""
Unit tests for configuration recovery handler.
"""

import json
from unittest import mock

import pytest

from html2md.config.backup import ConfigBackupManager
from html2md.config.recovery import ConfigRecoveryHandler, RecoveryAction


class TestConfigRecoveryHandler:
    """Test suite for ConfigRecoveryHandler class."""

    @pytest.fixture
    def setup_recovery(self, tmp_path):
        """Setup recovery handler with backup manager and config file."""
        config_file = tmp_path / "config.json"
        backup_manager = ConfigBackupManager(config_file, max_backups=5)
        default_config = {"default": True, "version": 1}

        handler = ConfigRecoveryHandler(config_file, backup_manager, default_config)

        return {
            "handler": handler,
            "config_file": config_file,
            "backup_manager": backup_manager,
            "default_config": default_config,
            "tmp_path": tmp_path
        }

    def test_init_detects_interactive_mode(self, setup_recovery):
        """Test handler correctly detects interactive vs non-interactive mode."""
        handler = setup_recovery["handler"]

        # is_interactive depends on actual terminal, so just check it's a boolean
        assert isinstance(handler.is_interactive, bool)

    @mock.patch('sys.stdin.isatty', return_value=False)
    @mock.patch('sys.stdout.isatty', return_value=False)
    def test_non_interactive_mode_detection(self, mock_stdout, mock_stdin, setup_recovery):
        """Test handler detects non-interactive mode correctly."""
        config_file = setup_recovery["config_file"]
        backup_manager = setup_recovery["backup_manager"]
        default_config = setup_recovery["default_config"]

        handler = ConfigRecoveryHandler(config_file, backup_manager, default_config)
        assert handler.is_interactive is False

    @mock.patch('sys.stdin.isatty', return_value=True)
    @mock.patch('sys.stdout.isatty', return_value=True)
    def test_interactive_mode_detection(self, mock_stdout, mock_stdin, setup_recovery):
        """Test handler detects interactive mode correctly."""
        config_file = setup_recovery["config_file"]
        backup_manager = setup_recovery["backup_manager"]
        default_config = setup_recovery["default_config"]

        handler = ConfigRecoveryHandler(config_file, backup_manager, default_config)
        assert handler.is_interactive is True

    def test_non_interactive_recovery_with_backups(self, setup_recovery):
        """Test non-interactive mode attempts backup restoration when available."""
        handler = setup_recovery["handler"]
        config_file = setup_recovery["config_file"]
        backup_manager = setup_recovery["backup_manager"]

        # Create a backup
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({"backup": "data"}, f)
        backup_manager.create_backup(reason="test")

        # Force non-interactive mode
        handler.is_interactive = False

        action = handler._non_interactive_recovery()
        assert action == RecoveryAction.RESTORE_BACKUP

    def test_non_interactive_recovery_without_backups(self, setup_recovery):
        """Test non-interactive mode uses defaults when no backups available."""
        handler = setup_recovery["handler"]
        handler.is_interactive = False

        action = handler._non_interactive_recovery()
        assert action == RecoveryAction.USE_DEFAULTS

    @mock.patch('html2md.config.recovery.Prompt.ask', return_value='r')
    def test_interactive_recovery_restore_backup(self, mock_prompt, setup_recovery):
        """Test interactive mode allows selecting backup restoration."""
        handler = setup_recovery["handler"]
        config_file = setup_recovery["config_file"]
        backup_manager = setup_recovery["backup_manager"]

        # Create a backup
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({"backup": "data"}, f)
        backup_manager.create_backup(reason="test")

        handler.is_interactive = True
        action = handler._prompt_user_recovery()

        assert action == RecoveryAction.RESTORE_BACKUP

    @mock.patch('html2md.config.recovery.Confirm.ask', return_value=True)
    @mock.patch('html2md.config.recovery.Prompt.ask', return_value='d')
    def test_interactive_recovery_use_defaults_confirmed(
        self, mock_prompt, mock_confirm, setup_recovery
    ):
        """Test interactive mode allows using defaults with confirmation."""
        handler = setup_recovery["handler"]
        handler.is_interactive = True

        action = handler._prompt_user_recovery()
        assert action == RecoveryAction.USE_DEFAULTS

    @mock.patch('html2md.config.recovery.Prompt.ask', return_value='m')
    def test_interactive_recovery_manual_fix(self, mock_prompt, setup_recovery):
        """Test interactive mode allows choosing manual fix."""
        handler = setup_recovery["handler"]
        handler.is_interactive = True

        action = handler._prompt_user_recovery()
        assert action == RecoveryAction.MANUAL_FIX

    @mock.patch('html2md.config.recovery.Prompt.ask', return_value='q')
    def test_interactive_recovery_quit(self, mock_prompt, setup_recovery):
        """Test interactive mode allows choosing to quit."""
        handler = setup_recovery["handler"]
        handler.is_interactive = True

        action = handler._prompt_user_recovery()
        assert action == RecoveryAction.EXIT

    def test_execute_restore_backup_success(self, setup_recovery):
        """Test executing backup restoration successfully."""
        handler = setup_recovery["handler"]
        config_file = setup_recovery["config_file"]
        backup_manager = setup_recovery["backup_manager"]

        # Create original config and backup
        original_data = {"original": True, "version": 1}
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(original_data, f)
        backup_manager.create_backup(reason="test")

        # Corrupt the config
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{"invalid": json}')

        # Execute restoration
        handler.is_interactive = False
        result = handler._execute_restore_backup()

        # Should return original data
        assert result == original_data

    def test_execute_restore_backup_falls_back_to_defaults(self, setup_recovery):
        """Test restore backup falls back to defaults if no backups exist."""
        handler = setup_recovery["handler"]
        default_config = setup_recovery["default_config"]

        handler.is_interactive = False
        result = handler._execute_restore_backup()

        # Should return defaults
        assert result == default_config

    def test_execute_use_defaults_non_interactive(self, setup_recovery):
        """Test use defaults in non-interactive mode doesn't write to disk."""
        handler = setup_recovery["handler"]
        config_file = setup_recovery["config_file"]
        default_config = setup_recovery["default_config"]

        # Create corrupt config
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{"corrupt": json}')

        handler.is_interactive = False
        result = handler._execute_use_defaults()

        # Should return defaults
        assert result == default_config

        # Config file should still contain corrupt data (NOT overwritten)
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '{"corrupt": json}' in content

    def test_execute_use_defaults_interactive_writes_to_disk(self, setup_recovery):
        """Test use defaults in interactive mode writes to disk."""
        handler = setup_recovery["handler"]
        config_file = setup_recovery["config_file"]
        default_config = setup_recovery["default_config"]

        # Create corrupt config
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{"corrupt": json}')

        handler.is_interactive = True
        result = handler._execute_use_defaults()

        # Should return defaults
        assert result == default_config

        # Config file should now contain defaults (overwritten)
        with open(config_file, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
        assert saved_data == default_config

    def test_execute_manual_fix_exits(self, setup_recovery):
        """Test manual fix action exits the program."""
        handler = setup_recovery["handler"]
        handler.is_interactive = True

        with pytest.raises(SystemExit) as exc_info:
            handler._execute_recovery(RecoveryAction.MANUAL_FIX)

        assert exc_info.value.code == 1

    def test_execute_exit_action_exits(self, setup_recovery):
        """Test exit action exits the program."""
        handler = setup_recovery["handler"]
        handler.is_interactive = True

        with pytest.raises(SystemExit) as exc_info:
            handler._execute_recovery(RecoveryAction.EXIT)

        assert exc_info.value.code == 0

    def test_handle_corrupt_config_saves_corrupt_file(self, setup_recovery):
        """Test handle_corrupt_config saves the corrupt file for debugging."""
        handler = setup_recovery["handler"]
        config_file = setup_recovery["config_file"]

        # Create corrupt config
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{"corrupt": json}')

        # Force non-interactive mode to avoid prompts
        handler.is_interactive = False

        error = json.JSONDecodeError("test error", "doc", 0)
        handler.handle_corrupt_config(error)

        # Check corrupt file was saved
        corrupt_path = config_file.with_suffix('.json.corrupt')
        assert corrupt_path.exists()

    def test_handle_corrupt_config_returns_valid_config(self, setup_recovery):
        """Test handle_corrupt_config returns valid config dict."""
        handler = setup_recovery["handler"]
        config_file = setup_recovery["config_file"]
        default_config = setup_recovery["default_config"]

        # Create corrupt config
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{"corrupt": json}')

        handler.is_interactive = False

        error = json.JSONDecodeError("test error", "doc", 0)
        result = handler.handle_corrupt_config(error)

        # Should return valid config (defaults in this case)
        assert isinstance(result, dict)
        assert result == default_config

    def test_handle_corrupt_config_with_backup_available(self, setup_recovery):
        """Test handle_corrupt_config restores from backup in non-interactive mode."""
        handler = setup_recovery["handler"]
        config_file = setup_recovery["config_file"]
        backup_manager = setup_recovery["backup_manager"]

        # Create original config and backup
        original_data = {"original": True, "restored": True}
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(original_data, f)
        backup_manager.create_backup(reason="test")

        # Corrupt the config
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{"corrupt": json}')

        handler.is_interactive = False

        error = json.JSONDecodeError("test error", "doc", 0)
        result = handler.handle_corrupt_config(error)

        # Should restore from backup
        assert result == original_data

    @mock.patch('html2md.config.recovery.Confirm.ask', side_effect=[False, True])
    @mock.patch('html2md.config.recovery.Prompt.ask', side_effect=['d', 'd'])
    def test_interactive_recovery_retry_on_cancelled_confirmation(
        self, mock_prompt, mock_confirm, setup_recovery
    ):
        """Test interactive mode loops back when user cancels confirmation."""
        handler = setup_recovery["handler"]
        handler.is_interactive = True

        action = handler._prompt_user_recovery()

        # Should eventually get USE_DEFAULTS after confirmation
        assert action == RecoveryAction.USE_DEFAULTS
        # Confirm should have been called twice (first cancelled, second confirmed)
        assert mock_confirm.call_count == 2

    def test_execute_use_defaults_creates_backup_before_overwrite(self, setup_recovery):
        """Test use defaults creates backup before overwriting in interactive mode."""
        handler = setup_recovery["handler"]
        config_file = setup_recovery["config_file"]
        backup_manager = setup_recovery["backup_manager"]

        # Create corrupt config
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{"corrupt": json}')

        handler.is_interactive = True
        handler._execute_use_defaults()

        # Check backup was created
        backups = backup_manager.list_backups()
        assert len(backups) > 0
        assert "pre-reset" in backups[0].name
