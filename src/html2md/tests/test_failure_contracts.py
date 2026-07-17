"""Regression tests for command and retrieval failure contracts."""

from unittest.mock import patch

import requests
from typer.testing import CliRunner

from html2md.cli.cli import app
from html2md.markdown.batch_processor import BatchItemResult, BatchResult
from html2md.markdown.crawler import CrawlResult, crawl_website
from html2md.network.request_handler import FetchResult
from html2md.utils.state_manager import StateManager


runner = CliRunner()


class FailingSession:
    class Cookies:
        @staticmethod
        def get_dict():
            return {}

    cookies = Cookies()

    def get(self, *args, **kwargs):
        raise requests.ConnectionError("offline")


def test_convert_failure_exits_nonzero():
    with patch("html2md.cli.cli.process_single_quiet", return_value=False):
        result = runner.invoke(app, ["convert", "https://example.com"])

    assert result.exit_code == 1


def test_batch_total_failure_exits_nonzero_without_completion(tmp_path):
    source = tmp_path / "links.md"
    source.write_text("[fixture](https://example.com)", encoding="utf-8")
    failed = BatchResult(
        items=[BatchItemResult("https://example.com", error="offline")]
    )
    with patch("html2md.cli.cli.process_markdown_links", return_value=failed):
        result = runner.invoke(
            app,
            ["batch", str(source), "--output-dir", str(tmp_path / "output"), "--quiet"],
        )

    assert result.exit_code == 1
    assert "1 URL(s) failed" in result.output
    assert "Batch processing complete" not in result.output


def test_batch_partial_failure_exits_nonzero_and_reports_durable_output(tmp_path):
    source = tmp_path / "links.md"
    source.write_text("fixture", encoding="utf-8")
    output = tmp_path / "output" / "good.md"
    output.parent.mkdir()
    output.write_text("good", encoding="utf-8")
    partial = BatchResult(
        items=[
            BatchItemResult("https://example.com/good", output_file=str(output)),
            BatchItemResult("https://example.com/bad", error="offline"),
        ],
        url_mapping={"https://example.com/good": str(output)},
    )
    with patch("html2md.cli.cli.process_markdown_links", return_value=partial):
        result = runner.invoke(
            app,
            ["batch", str(source), "--output-dir", str(output.parent), "--quiet"],
        )

    assert result.exit_code == 1
    assert "1 URL(s) failed; 1 succeeded" in result.output


def test_state_export_import_and_missing_info_fail_nonzero(tmp_path):
    with patch(
        "html2md.cli.state_commands.StateManager.export_state",
        side_effect=OSError("read-only"),
    ):
        exported = runner.invoke(
            app, ["state", "export", "missing", str(tmp_path / "state.json")]
        )
    with patch(
        "html2md.cli.state_commands.StateManager.import_state",
        side_effect=ValueError("invalid state"),
    ):
        imported = runner.invoke(app, ["state", "import", str(tmp_path / "bad.json")])
    with patch("html2md.cli.state_commands.StateManager.load_state", return_value=None):
        info = runner.invoke(app, ["state", "info", "missing"])

    assert exported.exit_code == 1
    assert "read-only" in exported.output
    assert imported.exit_code == 1
    assert "invalid state" in imported.output
    assert info.exit_code == 1
    assert "not found" in info.output


def test_crawler_fetch_failure_uses_typed_failure_result(tmp_path):
    state_manager = StateManager(state_dir=tmp_path / "states")
    failure = FetchResult(
        requested_url="https://example.com",
        final_url="https://example.com",
        error="ConnectionError: offline",
    )
    with patch("html2md.markdown.crawler.fetch_html", return_value=failure):
        result = crawl_website(
            "https://example.com",
            tmp_path / "output",
            max_pages=1,
            respect_robots=False,
            state_manager=state_manager,
        )

    assert isinstance(result, CrawlResult)
    assert result.success is False
    assert result.processed_count == 0
    assert result.failed_count == 1
    assert result.url_mapping == {}
    assert result.crawl_id == state_manager.current_state.crawl_id


def test_crawler_robots_denial_uses_same_result_contract(tmp_path):
    state_manager = StateManager(state_dir=tmp_path / "states")
    with patch("html2md.markdown.crawler.RobotsChecker") as checker_type:
        checker_type.return_value.can_fetch.return_value = False
        result = crawl_website(
            "https://example.com",
            tmp_path / "output",
            state_manager=state_manager,
        )

    assert isinstance(result, CrawlResult)
    assert result.success is False
    assert "robots.txt" in result.error


def test_crawl_failure_exits_nonzero_without_success_message(tmp_path):
    failed = CrawlResult(success=False, error="fixture failure")
    with patch("html2md.cli.cli.crawl_website", return_value=failed):
        result = runner.invoke(
            app,
            ["crawl", "https://example.com", "--output-dir", str(tmp_path), "--quiet"],
        )

    assert result.exit_code == 1
    assert "fixture failure" in result.output
    assert "Website crawling complete" not in result.output


def test_crawl_success_reports_completion(tmp_path):
    succeeded = CrawlResult(
        processed_count=1,
        url_mapping={"https://example.com": str(tmp_path / "index.md")},
        crawl_id="fixture",
    )
    with patch("html2md.cli.cli.crawl_website", return_value=succeeded):
        result = runner.invoke(
            app,
            ["crawl", "https://example.com", "--output-dir", str(tmp_path), "--quiet"],
        )

    assert result.exit_code == 0
    assert "Website crawling complete" in result.output
