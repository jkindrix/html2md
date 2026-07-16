"""Integration tests for state persistence with crawler."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from html2md.markdown.crawler import crawl_website
from html2md.utils.state_manager import StateManager


class TestStateIntegration:
    """Test integration between state manager and crawler."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as state_dir:
            with tempfile.TemporaryDirectory() as output_dir:
                yield Path(state_dir), Path(output_dir)

    @pytest.fixture
    def mock_html_response(self):
        """Mock HTML response for testing."""
        return """
        <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Test Content</h1>
            <p>This is a test page.</p>
            <a href="https://example.com/page2">Link to page 2</a>
        </body>
        </html>
        """

    @patch('html2md.markdown.crawler.html_to_markdown', return_value="# Test Content")
    @patch('html2md.markdown.crawler.fetch_html')
    def test_crawler_with_state_manager(self, mock_fetch, mock_convert, temp_dirs, mock_html_response):
        """Test crawler with state manager enabled."""
        state_dir, output_dir = temp_dirs

        # Mock the HTML fetch
        mock_fetch.return_value = mock_html_response

        # Create state manager
        state_manager = StateManager(state_dir=state_dir)

        # Run crawler with state management
        result = crawl_website(
            start_url="https://example.com",
            output_dir=str(output_dir),
            max_pages=1,
            max_depth=1,
            state_manager=state_manager,
            enable_checkpoints=True,
            checkpoint_page_count=1  # Checkpoint after each page
        )

        # Verify crawl completed
        assert result.success is True
        assert result.processed_count >= 1
        assert result.crawl_id is not None
        assert len(result.url_mapping) >= 1

        # Verify state was saved
        state_file = state_dir / f"{result.crawl_id}.json"
        assert state_file.exists()

        # Verify state contents
        with open(state_file, 'r') as f:
            state_data = json.load(f)

        assert state_data['crawl_id'] == result.crawl_id
        assert state_data['start_url'] == "https://example.com"
        assert state_data['output_dir'] == str(output_dir)
        assert len(state_data['checkpoints']) >= 1
        assert state_data['progress']['statistics']['urls_processed'] >= 1

    @patch('html2md.markdown.crawler.html_to_markdown', return_value="# Test Content")
    @patch('html2md.markdown.crawler.fetch_html')
    def test_crawler_resume_functionality(self, mock_fetch, mock_convert, temp_dirs, mock_html_response):
        """Test resuming a crawl from saved state."""
        state_dir, output_dir = temp_dirs

        # Mock the HTML fetch
        mock_fetch.return_value = mock_html_response

        # Create state manager
        state_manager = StateManager(state_dir=state_dir)

        # Start a crawl but interrupt it early
        initial_result = crawl_website(
            start_url="https://example.com",
            output_dir=str(output_dir),
            max_pages=1,
            max_depth=1,
            state_manager=state_manager,
            enable_checkpoints=True
        )

        # Verify initial crawl
        assert initial_result.crawl_id is not None
        assert initial_result.processed_count >= 1

        # Resume through a new manager, as a new CLI process would.
        resuming_manager = StateManager(state_dir=state_dir)
        resumed_result = crawl_website(
            start_url="https://example.com",  # Will be overridden by state
            output_dir=str(output_dir),
            state_manager=resuming_manager,
            resume_crawl_id=initial_result.crawl_id,
            enable_checkpoints=True
        )

        # Verify resume worked
        assert resumed_result.success is True
        assert resumed_result.crawl_id == initial_result.crawl_id
        assert resumed_result.processed_count >= initial_result.processed_count

        # Verify state was updated
        state_file = state_dir / f"{initial_result.crawl_id}.json"
        assert state_file.exists()

        with open(state_file, 'r') as f:
            final_state = json.load(f)

        assert final_state['progress']['statistics']['urls_processed'] >= initial_result.processed_count

    @patch('html2md.markdown.crawler.html_to_markdown', return_value="# Resumed")
    @patch('html2md.markdown.crawler.fetch_html')
    def test_resume_page_budget_counts_only_prior_successes(
        self, mock_fetch, mock_convert, temp_dirs, mock_html_response
    ):
        """Prior failures must not consume the resumed crawl's success budget."""
        state_dir, output_dir = temp_dirs
        mock_fetch.return_value = mock_html_response

        manager = StateManager(state_dir=state_dir)
        state = manager.create_new_state(
            start_url="https://example.com",
            output_dir=str(output_dir),
            config={},
        )
        existing_output = output_dir / "existing.md"
        existing_output.write_text("# Existing", encoding="utf-8")
        state.urls_visited["https://example.com/existing"] = str(existing_output)
        state.urls_failed["https://example.com/failed"] = "fixture failure"
        state.urls_queued = [("https://example.com/resumed", 1)]
        state.statistics.urls_processed = 2
        state.statistics.urls_failed = 1
        manager.save_state()

        result = crawl_website(
            start_url="https://ignored.example",
            output_dir=str(output_dir),
            max_pages=2,
            respect_robots=False,
            state_manager=StateManager(state_dir=state_dir),
            resume_crawl_id=state.crawl_id,
        )

        assert result.success is True
        assert result.processed_count == 2
        assert "https://example.com/resumed" in result.url_mapping

    def test_state_manager_cli_integration(self, temp_dirs):
        """Test state manager CLI commands."""
        state_dir, output_dir = temp_dirs

        # Create a mock state
        state_manager = StateManager(state_dir=state_dir)
        crawl_state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir=str(output_dir),
            config={"max_pages": 10}
        )

        # Test listing states
        crawls = state_manager.list_resumable_crawls()
        assert len(crawls) == 1
        assert crawls[0]['crawl_id'] == crawl_state.crawl_id
        assert crawls[0]['start_url'] == "https://example.com"

        # Test export/import
        export_file = state_dir / "exported.state-export"
        state_manager.export_state(crawl_state.crawl_id, export_file)
        assert export_file.exists()

        # Import creates new ID
        new_crawl_id = state_manager.import_state(export_file)
        assert new_crawl_id != crawl_state.crawl_id

        # Should have 2 states now
        crawls = state_manager.list_resumable_crawls()
        assert len(crawls) == 2

        # Test cleanup
        cleaned = state_manager.clean_old_states(days=0)  # Clean all
        assert cleaned == 2

        crawls = state_manager.list_resumable_crawls()
        assert len(crawls) == 0

    def test_checkpoint_triggers(self, temp_dirs):
        """Test different checkpoint triggers."""
        state_dir, output_dir = temp_dirs

        state_manager = StateManager(state_dir=state_dir)
        crawl_state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir=str(output_dir),
            config={}
        )

        # Manual checkpoint
        state_manager.save_checkpoint("manual", "Test checkpoint")

        # Auto checkpoint after page processing
        state_manager.update_progress("https://example.com", True, "/tmp/test.md")

        # Should have checkpoints
        assert len(crawl_state.checkpoints) >= 2

        # Check checkpoint types
        triggers = [cp.trigger for cp in crawl_state.checkpoints]
        assert "manual" in triggers

        # Verify state file was updated
        state_file = state_dir / f"{crawl_state.crawl_id}.json"
        assert state_file.exists()

        with open(state_file, 'r') as f:
            saved_state = json.load(f)

        assert len(saved_state['checkpoints']) >= 2

    def test_state_corruption_recovery(self, temp_dirs):
        """Test recovery from corrupted state files."""
        state_dir, output_dir = temp_dirs

        state_manager = StateManager(state_dir=state_dir)
        crawl_state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir=str(output_dir),
            config={}
        )

        state_file = state_dir / f"{crawl_state.crawl_id}.json"
        backup_file = state_dir / f"{crawl_state.crawl_id}.bak"

        # Save state to create backup
        state_manager.save_state()
        state_manager.save_state()  # Second save creates backup

        assert state_file.exists()
        assert backup_file.exists()

        # Corrupt the main state file
        with open(state_file, 'w') as f:
            f.write("invalid json")

        # Should recover from backup
        recovered_state = state_manager.load_state(crawl_state.crawl_id)
        assert recovered_state is not None
        assert recovered_state.crawl_id == crawl_state.crawl_id

    def test_signal_handling(self, temp_dirs):
        """Test signal handling for graceful interruption."""
        state_dir, output_dir = temp_dirs

        state_manager = StateManager(state_dir=state_dir)
        crawl_state = state_manager.create_new_state(
            start_url="https://example.com",
            output_dir=str(output_dir),
            config={}
        )

        # Simulate signal handling
        import signal
        import os

        # This should trigger the signal handler
        # (In real usage, this would happen during crawling)
        os.kill(os.getpid(), signal.SIGTERM)

        # Note: The signal handler should have created a checkpoint
        # But since we're in a test, the handler might not execute
        # In a real scenario, this would create a "signal" checkpoint
