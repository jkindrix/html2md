"""
Unit tests for atomic configuration writer.
"""

import json
import os

import pytest

from html2md.config.writer import atomic_write_json


class TestAtomicWriteJson:
    """Test suite for atomic_write_json function."""

    def test_atomic_write_success(self, tmp_path):
        """Test successful atomic write creates file with correct content."""
        config_file = tmp_path / "config.json"
        test_data = {"domains": {}, "logging": {"level": "INFO"}}

        atomic_write_json(config_file, test_data)

        # Verify file exists and contains correct data
        assert config_file.exists()
        with open(config_file, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
        assert loaded_data == test_data

    def test_atomic_write_creates_parent_directory(self, tmp_path):
        """Test atomic write creates parent directories if they don't exist."""
        config_file = tmp_path / "subdir" / "nested" / "config.json"
        test_data = {"test": "data"}

        atomic_write_json(config_file, test_data)

        assert config_file.exists()
        assert config_file.parent.exists()

    def test_atomic_write_overwrites_existing_file(self, tmp_path):
        """Test atomic write correctly overwrites existing file."""
        config_file = tmp_path / "config.json"

        # Write initial data
        initial_data = {"version": 1}
        atomic_write_json(config_file, initial_data)

        # Overwrite with new data
        new_data = {"version": 2, "updated": True}
        atomic_write_json(config_file, new_data)

        # Verify new data is present
        with open(config_file, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
        assert loaded_data == new_data
        assert loaded_data != initial_data

    def test_atomic_write_with_custom_indent(self, tmp_path):
        """Test atomic write respects custom indentation."""
        config_file = tmp_path / "config.json"
        test_data = {"nested": {"data": [1, 2, 3]}}

        atomic_write_json(config_file, test_data, indent=2)

        # Verify indentation in raw file
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 2-space indent should produce specific spacing
        assert '"nested"' in content
        assert '  "data"' in content  # 2-space indent

    def test_atomic_write_preserves_unicode(self, tmp_path):
        """Test atomic write correctly handles unicode characters."""
        config_file = tmp_path / "config.json"
        test_data = {
            "unicode": "Hello 世界 🌍",
            "special": "Ñoño Müller"
        }

        atomic_write_json(config_file, test_data)

        with open(config_file, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)

        assert loaded_data == test_data
        assert loaded_data["unicode"] == "Hello 世界 🌍"

    def test_atomic_write_cleanup_on_json_error(self, tmp_path):
        """Test temp file is cleaned up when JSON serialization fails."""
        config_file = tmp_path / "config.json"

        # Object that can't be serialized to JSON
        class NonSerializable:
            pass

        test_data = {"object": NonSerializable()}

        # Should raise TypeError
        with pytest.raises(TypeError):
            atomic_write_json(config_file, test_data)

        # Verify no .tmp files left behind
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_atomic_write_cleanup_on_permission_error(self, tmp_path):
        """Test temp file cleanup when permissions prevent final rename."""
        config_file = tmp_path / "config.json"
        test_data = {"test": "data"}

        # Create read-only directory (will cause os.replace to fail)
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        config_file = readonly_dir / "config.json"

        # Make directory read-only
        os.chmod(readonly_dir, 0o444)

        try:
            with pytest.raises(OSError):
                atomic_write_json(config_file, test_data)

            # Verify no .tmp files left behind (cleanup worked)
            tmp_files = list(readonly_dir.glob("*.tmp"))
            assert len(tmp_files) == 0

        finally:
            # Restore permissions for cleanup
            os.chmod(readonly_dir, 0o755)

    def test_atomic_write_invalid_path_type(self):
        """Test atomic write raises ValueError for non-Path argument."""
        with pytest.raises(ValueError, match="must be a Path object"):
            atomic_write_json("/string/path.json", {})

    def test_atomic_write_preserves_original_on_error(self, tmp_path):
        """Test original file is preserved if write fails partway through."""
        config_file = tmp_path / "config.json"

        # Write initial valid data
        original_data = {"original": True, "version": 1}
        atomic_write_json(config_file, original_data)

        # Record original modification time
        original_mtime = config_file.stat().st_mtime

        # Attempt to write non-serializable data (will fail)
        class NonSerializable:
            pass

        bad_data = {"object": NonSerializable()}

        with pytest.raises(TypeError):
            atomic_write_json(config_file, bad_data)

        # Verify original file is unchanged
        assert config_file.exists()
        with open(config_file, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
        assert loaded_data == original_data

        # Modification time should be unchanged (or very close)
        current_mtime = config_file.stat().st_mtime
        assert abs(current_mtime - original_mtime) < 0.1

    def test_atomic_write_fsync_called(self, tmp_path, monkeypatch):
        """Test that fsync is called to ensure durability."""
        config_file = tmp_path / "config.json"
        test_data = {"test": "data"}

        fsync_called = []

        original_fsync = os.fsync

        def mock_fsync(fd):
            fsync_called.append(fd)
            return original_fsync(fd)

        monkeypatch.setattr(os, 'fsync', mock_fsync)

        atomic_write_json(config_file, test_data)

        # Verify fsync was called at least once
        assert len(fsync_called) > 0
