"""Regression tests for command and retrieval failure contracts."""

from unittest.mock import patch

import requests
from typer.testing import CliRunner

from html2md.cli.cli import app
from html2md.markdown.crawler import CrawlResult, crawl_website
from html2md.network.chatgpt_handler import get_conversation_html
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


def test_chatgpt_retrieval_failure_is_not_convertible_html():
    def fixture_get(session, _method, url, **kwargs):
        return session.get(
            url,
            headers=kwargs.get("headers"),
            timeout=kwargs.get("timeout"),
        )

    with patch("html2md.network.chatgpt_handler.guarded_request", fixture_get):
        result = get_conversation_html(
            "https://chatgpt.com/c/00000000-0000-0000-0000-000000000000",
            FailingSession(),
            {},
        )

    assert result is None


def test_convert_failure_exits_nonzero():
    with patch("html2md.cli.cli.process_single_quiet", return_value=False):
        result = runner.invoke(app, ["convert", "https://example.com"])

    assert result.exit_code == 1


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
