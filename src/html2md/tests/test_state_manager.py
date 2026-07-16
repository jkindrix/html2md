"""Tests for state persistence and resume functionality."""

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from html2md.utils.state_manager import (
    CrawlState, CrawlStatistics, StateManager
)


class TestCrawlStatistics:
    """Test CrawlStatistics dataclass."""

    def test_statistics_creation(self):
        """Test creating statistics."""
        stats = CrawlStatistics()
        assert stats.total_urls == 0
        assert stats.urls_processed == 0
        assert stats.urls_failed == 0
        assert stats.bytes_downloaded == 0
        assert stats.start_time > 0
        assert stats.last_update > 0

    def test_statistics_serialization(self):
        """Test serializing statistics."""
        stats = CrawlStatistics(
            total_urls=100,
            urls_processed=50,
            urls_failed=5
        )

        data = stats.to_dict()
        assert data["total_urls"] == 100
        assert data["urls_processed"] == 50
        assert data["urls_failed"] == 5

        # Test deserialization
        stats2 = CrawlStatistics.from_dict(data)
        assert stats2.total_urls == stats.total_urls
        assert stats2.urls_processed == stats.urls_processed


class TestCrawlState:
    """Test CrawlState dataclass."""

    def test_state_creation(self):
        """Test creating crawl state."""
        state = CrawlState(
            start_url="https://example.com",
            output_dir="/tmp/output"
        )

        assert state.version == "1.0"
        assert state.crawl_id  # Should have UUID
        assert state.start_url == "https://example.com"
        assert state.output_dir == "/tmp/output"
        assert len(state.urls_queued) == 0
        assert len(state.urls_visited) == 0
        assert len(state.urls_failed) == 0

    def test_state_serialization(self):
        """Test serializing state."""
        state = CrawlState(
            start_url="https://example.com",
            output_dir="/tmp/output",
            config={"max_depth": 3}
        )

        # Add some data
        state.urls_queued.append(("https://example.com/page1", 1))
        state.urls_visited["https://example.com"] = "/tmp/output/index.md"
        state.urls_failed["https://example.com/404"] = "404 Not Found"

        # Serialize
        data = state.to_dict()
        assert data["version"] == "1.0"
        assert data["start_url"] == "https://example.com"
        assert len(data["progress"]["urls_queued"]) == 1
        assert len(data["progress"]["urls_visited"]) == 1
        assert len(data["progress"]["urls_failed"]) == 1

        # Deserialize
        state2 = CrawlState.from_dict(data)
        assert state2.crawl_id == state.crawl_id
        assert state2.start_url == state.start_url
        assert len(state2.urls_queued) == 1
        assert state2.urls_visited["https://example.com"] == "/tmp/output/index.md"

    def test_state_serialization_normalizes_paths(self, tmp_path):
        """Path values at persistence boundaries become JSON-safe strings."""
        state = CrawlState(
            start_url="https://example.com",
            output_dir=tmp_path / "output",
            config={"nested": {"state_dir": tmp_path / "states"}},
        )

        data = state.to_dict()

        assert data["output_dir"] == str(tmp_path / "output")
        assert data["config"]["nested"]["state_dir"] == str(tmp_path / "states")
        json.dumps(data)


class TestStateManager:
    """Test StateManager class."""

    @pytest.fixture
    def temp_state_dir(self):
        """Create temporary state directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def state_manager(self, temp_state_dir):
        """Create StateManager instance."""
        return StateManager(state_dir=temp_state_dir)

    def test_create_new_state(self, state_manager):
        """Test creating new state."""
        state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir="/tmp/output",
            config={"max_depth": 3}
        )

        assert state.start_url == "https://example.com"
        assert state.output_dir == "/tmp/output"
        assert state.config["max_depth"] == 3
        assert len(state.checkpoints) == 1  # Initial checkpoint
        assert state.checkpoints[0].trigger == "manual"

    def test_save_and_load_state(self, state_manager, temp_state_dir):
        """Test saving and loading state."""
        # Create state
        state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir="/tmp/output",
            config={}
        )
        crawl_id = state.crawl_id

        # Add some data
        state.urls_queued.append(("https://example.com/page1", 1))
        state.urls_visited["https://example.com"] = "/tmp/output/index.md"

        # Save
        state_manager.save_state()

        # Verify file exists
        state_file = temp_state_dir / f"{crawl_id}.json"
        assert state_file.exists()

        # Load in new manager
        new_manager = StateManager(state_dir=temp_state_dir)
        loaded_state = new_manager.load_state(crawl_id)

        assert loaded_state is not None
        assert loaded_state.crawl_id == crawl_id
        assert loaded_state.start_url == "https://example.com"
        assert len(loaded_state.urls_queued) == 1
        assert loaded_state.urls_visited["https://example.com"] == "/tmp/output/index.md"

    def test_checkpoint_saving(self, state_manager):
        """Test checkpoint functionality."""
        state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir="/tmp/output",
            config={}
        )

        # Save manual checkpoint
        state_manager.save_checkpoint("manual", "Test checkpoint")

        assert len(state.checkpoints) == 2  # Initial + manual
        assert state.checkpoints[-1].trigger == "manual"
        assert state.checkpoints[-1].message == "Test checkpoint"

    def test_should_checkpoint(self, state_manager):
        """Test checkpoint triggers."""
        state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir="/tmp/output",
            config={}
        )

        # Initially should not checkpoint
        assert not state_manager.should_checkpoint()

        # Test page count trigger
        state_manager.pages_since_checkpoint = 100
        assert state_manager.should_checkpoint()

        # Test time trigger
        state_manager.pages_since_checkpoint = 0
        state_manager.last_checkpoint_time = time.time() - 400  # > 5 minutes
        assert state_manager.should_checkpoint()

    def test_update_progress(self, state_manager):
        """Test progress updates."""
        state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir="/tmp/output",
            config={}
        )

        # Update successful URL
        state_manager.update_progress(
            url="https://example.com",
            success=True,
            output_file="/tmp/output/index.md"
        )

        assert state.statistics.urls_processed == 1
        assert "https://example.com" in state.urls_visited
        assert state.urls_visited["https://example.com"] == "/tmp/output/index.md"

        # Update failed URL
        state_manager.update_progress(
            url="https://example.com/404",
            success=False,
            error_message="404 Not Found"
        )

        assert state.statistics.urls_processed == 2
        assert state.statistics.urls_failed == 1
        assert "https://example.com/404" in state.urls_failed

    def test_queue_management(self, state_manager):
        """Test URL queue management."""
        state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir="/tmp/output",
            config={}
        )

        # Add URLs
        urls = [
            ("https://example.com/page1", 1),
            ("https://example.com/page2", 1),
            ("https://example.com/page3", 2)
        ]
        state_manager.add_urls_to_queue(urls)

        assert len(state.urls_queued) == 3
        assert state.statistics.total_urls == 3

        # Get next URL
        next_url = state_manager.get_next_url()
        assert next_url == ("https://example.com/page1", 1)
        assert len(state.urls_queued) == 2

    def test_list_resumable_crawls(self, state_manager):
        """Test listing resumable crawls."""
        # Create multiple crawls
        crawl_ids = []
        for i in range(3):
            state = state_manager.create_new_state(
                start_url=f"https://example{i}.com",
                output_dir=f"/tmp/output{i}",
                config={}
            )
            crawl_ids.append(state.crawl_id)
            time.sleep(0.1)  # Ensure different timestamps

        # List crawls
        crawls = state_manager.list_resumable_crawls()

        assert len(crawls) == 3
        # Should be sorted by last checkpoint (newest first)
        assert crawls[0]["crawl_id"] == crawl_ids[-1]
        assert crawls[0]["start_url"] == "https://example2.com"

    def test_clean_old_states(self, state_manager, temp_state_dir):
        """Test cleaning old states."""
        # Create a state
        state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir="/tmp/output",
            config={}
        )
        crawl_id = state.crawl_id

        # Make the file appear old
        state_file = temp_state_dir / f"{crawl_id}.json"
        old_time = time.time() - (40 * 24 * 60 * 60)  # 40 days ago
        os.utime(state_file, (old_time, old_time))

        # Clean old states
        cleaned = state_manager.clean_old_states(days=30)

        assert cleaned == 1
        assert not state_file.exists()

    def test_atomic_writes(self, state_manager, temp_state_dir):
        """Test atomic write functionality."""
        state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir="/tmp/output",
            config={}
        )
        crawl_id = state.crawl_id

        # Save state
        state_manager.save_state()

        # Check backup was created
        state_file = temp_state_dir / f"{crawl_id}.json"
        backup_file = temp_state_dir / f"{crawl_id}.bak"

        # Make another save
        state.urls_visited["https://example.com/new"] = "/tmp/output/new.md"
        state_manager.save_state()

        assert state_file.exists()
        assert backup_file.exists()

        # Verify backup has old data
        with open(backup_file, 'r') as f:
            backup_data = json.load(f)
        assert "https://example.com/new" not in backup_data["progress"]["urls_visited"]

    def test_export_import_state(self, state_manager, temp_state_dir):
        """Test exporting and importing state."""
        # Create state with data
        state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir="/tmp/output",
            config={"test": True}
        )
        original_id = state.crawl_id
        state.urls_visited["https://example.com"] = "/tmp/output/index.md"
        state_manager.save_state()

        # Export
        export_file = temp_state_dir / "export.json"
        state_manager.export_state(original_id, export_file)
        assert export_file.exists()

        # Import in new manager
        new_manager = StateManager(state_dir=temp_state_dir)
        new_id = new_manager.import_state(export_file)

        assert new_id != original_id  # Should have new ID

        # Load imported state
        imported_state = new_manager.load_state(new_id)
        assert imported_state.start_url == "https://example.com"
        assert imported_state.config["test"] is True
        assert "https://example.com" in imported_state.urls_visited
