"""
Unit tests for configuration backup manager.
"""

import json
import time

import pytest

from html2md.config.backup import ConfigBackupManager


class TestConfigBackupManager:
    """Test suite for ConfigBackupManager class."""

    def test_init_validates_max_backups(self, tmp_path):
        """Test initialization validates max_backups parameter."""
        config_file = tmp_path / "config.json"

        # Valid max_backups
        manager = ConfigBackupManager(config_file, max_backups=3)
        assert manager.max_backups == 3

        # Invalid max_backups
        with pytest.raises(ValueError, match="max_backups must be >= 1"):
            ConfigBackupManager(config_file, max_backups=0)

        with pytest.raises(ValueError):
            ConfigBackupManager(config_file, max_backups=-1)

    def test_create_backup_success(self, tmp_path):
        """Test successful backup creation."""
        config_file = tmp_path / "config.json"
        test_data = {"test": "data", "version": 1}

        # Create config file
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f)

        manager = ConfigBackupManager(config_file)
        backup_path = manager.create_backup(reason="test")

        # Verify backup was created
        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.parent == manager.backup_dir
        assert "test" in backup_path.name

        # Verify backup contains correct data
        with open(backup_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        assert backup_data == test_data

    def test_create_backup_nonexistent_source(self, tmp_path):
        """Test create_backup returns None when source doesn't exist."""
        config_file = tmp_path / "nonexistent.json"

        manager = ConfigBackupManager(config_file)
        backup_path = manager.create_backup(reason="test")

        assert backup_path is None

    def test_create_backup_creates_backup_directory(self, tmp_path):
        """Test backup directory is created automatically."""
        config_file = tmp_path / "config.json"

        # Create config file
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({"test": "data"}, f)

        manager = ConfigBackupManager(config_file)

        # Backup directory shouldn't exist yet
        assert not manager.backup_dir.exists()

        # Create backup
        backup_path = manager.create_backup(reason="test")

        # Now backup directory should exist
        assert manager.backup_dir.exists()
        assert backup_path.parent == manager.backup_dir

    def test_create_backup_with_different_reasons(self, tmp_path):
        """Test backups created with different reasons have distinct names."""
        config_file = tmp_path / "config.json"

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({"test": "data"}, f)

        manager = ConfigBackupManager(config_file)

        backup1 = manager.create_backup(reason="pre-save")
        time.sleep(0.01)  # Ensure different timestamps
        backup2 = manager.create_backup(reason="manual")
        time.sleep(0.01)
        backup3 = manager.create_backup(reason="pre-reset")

        assert "pre-save" in backup1.name
        assert "manual" in backup2.name
        assert "pre-reset" in backup3.name
        assert backup1 != backup2 != backup3

    def test_cleanup_old_backups(self, tmp_path):
        """Test old backups are cleaned up when limit is exceeded."""
        config_file = tmp_path / "config.json"

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({"test": "data"}, f)

        # Set max_backups to 3
        manager = ConfigBackupManager(config_file, max_backups=3)

        # Create 5 backups
        backups = []
        for i in range(5):
            backup = manager.create_backup(reason=f"backup-{i}")
            backups.append(backup)
            time.sleep(0.01)  # Ensure different timestamps

        # List backups - should only have 3 (newest)
        remaining_backups = manager.list_backups()
        assert len(remaining_backups) == 3

        # Verify oldest backups were removed
        assert not backups[0].exists()  # Oldest
        assert not backups[1].exists()  # Second oldest
        assert backups[2].exists()      # Should still exist
        assert backups[3].exists()      # Should still exist
        assert backups[4].exists()      # Newest - should exist

    def test_list_backups_sorted_newest_first(self, tmp_path):
        """Test list_backups returns backups sorted by timestamp (newest first)."""
        config_file = tmp_path / "config.json"

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({"test": "data"}, f)

        manager = ConfigBackupManager(config_file, max_backups=10)

        # Create several backups with delays
        backup_paths = []
        for i in range(3):
            backup = manager.create_backup(reason=f"test-{i}")
            backup_paths.append(backup)
            time.sleep(0.01)

        backups = manager.list_backups()

        # Should be sorted newest first
        assert len(backups) == 3
        assert backups[0] == backup_paths[2]  # Newest
        assert backups[1] == backup_paths[1]
        assert backups[2] == backup_paths[0]  # Oldest

    def test_list_backups_empty_directory(self, tmp_path):
        """Test list_backups returns empty list when no backups exist."""
        config_file = tmp_path / "config.json"
        manager = ConfigBackupManager(config_file)

        backups = manager.list_backups()
        assert backups == []

    def test_save_corrupted_config(self, tmp_path):
        """Test corrupted config is saved for debugging."""
        config_file = tmp_path / "config.json"

        # Create corrupt config file (invalid JSON)
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{"invalid": json}')

        manager = ConfigBackupManager(config_file)
        corrupt_path = manager.save_corrupted_config()

        # Verify corrupt file was saved
        assert corrupt_path is not None
        assert corrupt_path.exists()
        assert corrupt_path.name == "config.json.corrupt"

        # Verify content matches original
        with open(corrupt_path, 'r', encoding='utf-8') as f:
            corrupt_content = f.read()
        assert corrupt_content == '{"invalid": json}'

    def test_save_corrupted_config_overwrites_previous(self, tmp_path):
        """Test save_corrupted_config overwrites previous corrupt file."""
        config_file = tmp_path / "config.json"

        # Create first corrupt file
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{"corrupt": 1}')

        manager = ConfigBackupManager(config_file)
        corrupt_path1 = manager.save_corrupted_config()

        # Create second corrupt file
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('{"corrupt": 2}')

        corrupt_path2 = manager.save_corrupted_config()

        # Should be same path
        assert corrupt_path1 == corrupt_path2

        # Content should be from second file
        with open(corrupt_path2, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '{"corrupt": 2}' in content

    def test_restore_backup_success(self, tmp_path):
        """Test successful backup restoration."""
        config_file = tmp_path / "config.json"

        # Create original config
        original_data = {"version": 1, "original": True}
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(original_data, f)

        manager = ConfigBackupManager(config_file)
        backup_path = manager.create_backup(reason="test")

        # Modify config
        new_data = {"version": 2, "modified": True}
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(new_data, f)

        # Restore backup
        success = manager.restore_backup(backup_path)

        assert success is True

        # Verify config was restored
        with open(config_file, 'r', encoding='utf-8') as f:
            restored_data = json.load(f)
        assert restored_data == original_data

    def test_restore_backup_nonexistent_file(self, tmp_path):
        """Test restore_backup fails gracefully for nonexistent backup."""
        config_file = tmp_path / "config.json"
        manager = ConfigBackupManager(config_file)

        nonexistent_backup = tmp_path / "nonexistent.json"
        success = manager.restore_backup(nonexistent_backup)

        assert success is False

    def test_restore_backup_validates_json(self, tmp_path):
        """Test restore_backup validates JSON before restoring."""
        config_file = tmp_path / "config.json"

        # Create valid config
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({"valid": True}, f)

        # Create invalid "backup" file
        invalid_backup = tmp_path / "invalid.json"
        with open(invalid_backup, 'w', encoding='utf-8') as f:
            f.write('{"invalid": json}')

        manager = ConfigBackupManager(config_file)
        success = manager.restore_backup(invalid_backup)

        # Should fail validation
        assert success is False

        # Original config should be unchanged
        with open(config_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data == {"valid": True}

    def test_backup_preserves_metadata(self, tmp_path):
        """Test backup preserves file metadata (using copy2)."""
        config_file = tmp_path / "config.json"

        # Create config with specific content
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({"test": "data"}, f)

        # Get original modification time
        original_mtime = config_file.stat().st_mtime

        manager = ConfigBackupManager(config_file)
        backup_path = manager.create_backup(reason="test")

        # Backup should have same modification time
        backup_mtime = backup_path.stat().st_mtime
        assert abs(backup_mtime - original_mtime) < 0.01

    def test_concurrent_backup_creation(self, tmp_path):
        """Test multiple backups can be created in quick succession."""
        config_file = tmp_path / "config.json"

        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump({"test": "data"}, f)

        manager = ConfigBackupManager(config_file, max_backups=10)

        # Create multiple backups quickly
        backups = []
        for i in range(5):
            backup = manager.create_backup(reason=f"concurrent-{i}")
            backups.append(backup)
            time.sleep(0.01)  # Small delay to ensure unique timestamps

        # All should exist and be distinct
        assert len(backups) == 5
        assert len(set(backups)) == 5  # All unique
        assert all(b.exists() for b in backups)
