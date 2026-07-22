"""Direct tests for presentation-neutral network command boundaries."""

from contextlib import nullcontext
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest

from grab2md.cli.command_runtime import (
    BatchCommandOptions,
    Browser,
    CommandUsageError,
    ConvertCommandOptions,
    CrawlCommandOptions,
    classify_command_failure,
    execute_batch,
    execute_crawls,
    prepare_convert_options,
)
from grab2md.markdown.batch_processor import BatchItemResult, BatchResult
from grab2md.markdown.content_extractor import ContentMode
from grab2md.markdown.crawler import CrawlResult


def convert_options(**changes) -> ConvertCommandOptions:
    values = {
        "sources": ["page.html"],
        "content_mode": ContentMode.FULL,
        "selector": None,
        "output": None,
        "no_cookies": False,
        "browser_cookies": False,
        "browser": None,
        "cookie_path": None,
        "cookie_json": None,
        "headers_file": None,
        "storage_state": None,
        "local": True,
        "enhanced_headers": True,
        "user_agent_contact": None,
        "insecure": False,
        "allow_private_network": False,
        "download_images": False,
        "images_dir": "images",
        "include_metadata": False,
        "render_js": False,
        "fancy": False,
    }
    values.update(changes)
    return ConvertCommandOptions(**cast(Any, values))


def batch_options(tmp_path: Path, **changes) -> BatchCommandOptions:
    source = tmp_path / "links.md"
    source.write_text("https://example.com\n", encoding="utf-8")
    values = {
        "input_patterns": [str(source)],
        "output_dir": tmp_path / "output",
        "content_mode": ContentMode.FULL,
        "selector": None,
        "include_metadata": False,
        "enhanced_headers": True,
        "user_agent_contact": None,
        "flatten_output": False,
        "flatten_all": False,
        "hierarchical": False,
        "visualize": False,
        "report": None,
        "insecure": False,
        "allow_private_network": False,
        "quiet": True,
    }
    values.update(changes)
    return BatchCommandOptions(**cast(Any, values))


def crawl_options(tmp_path: Path, **changes) -> CrawlCommandOptions:
    values = {
        "start_urls": ["https://example.com"],
        "output_dir": tmp_path / "output",
        "follow_option": "domain-only",
        "max_depth": 1,
        "max_pages": 2,
        "delay": 0.0,
        "respect_robots": True,
        "rate_limit": None,
        "enhanced_headers": True,
        "user_agent_contact": None,
        "insecure": False,
        "allow_private_network": False,
        "polite": False,
        "show_progress": True,
        "content_mode": ContentMode.FULL,
        "selector": None,
        "include_metadata": False,
        "flatten_output": False,
        "hierarchical": False,
        "visualize": False,
        "quiet": True,
    }
    values.update(changes)
    return CrawlCommandOptions(**cast(Any, values))


def test_convert_preparation_keeps_cookie_path_one_shot(tmp_path):
    options = convert_options(browser=Browser.CHROME, cookie_path=tmp_path / "Cookies")

    with pytest.raises(CommandUsageError, match="requires --browser-cookies"):
        prepare_convert_options(options)

    prepare_convert_options(
        convert_options(
            browser=Browser.CHROME,
            browser_cookies=True,
            cookie_path=tmp_path / "Cookies",
        )
    )

    with pytest.raises(CommandUsageError, match="cannot be combined"):
        prepare_convert_options(
            convert_options(
                browser_cookies=True,
                cookie_path=tmp_path / "Cookies",
                cookie_json=tmp_path / "cookies.json",
            )
        )


def test_convert_preparation_rejects_multiple_sources_with_one_output(tmp_path):
    with pytest.raises(CommandUsageError, match="exactly one source"):
        prepare_convert_options(
            convert_options(
                sources=["first.html", "second.html"],
                output=tmp_path / "combined.md",
            )
        )

    prepare_convert_options(
        convert_options(sources=["first.html", "second.html"], output=None)
    )


def test_command_failure_classifier_distinguishes_usage_from_runtime():
    usage = classify_command_failure("Batch processing", CommandUsageError("bad input"))
    runtime = classify_command_failure("Crawling", OSError("disk full"))

    assert usage.exit_code == 2
    assert usage.message == "Batch processing options are invalid: bad input"
    assert runtime.exit_code == 1
    assert runtime.message == "Crawling failed: disk full"


def test_batch_layout_validation_happens_before_processing(tmp_path):
    processor = Mock()
    options = batch_options(tmp_path, flatten_output=True, flatten_all=True)

    with pytest.raises(CommandUsageError, match="flatten"):
        execute_batch(options, processor=processor, config={})

    processor.assert_not_called()


def test_batch_execution_expands_inputs_and_returns_typed_result(tmp_path):
    expected = BatchResult(
        items=[BatchItemResult("https://example.com", output_file="page.md")],
        url_mapping={"https://example.com": "page.md"},
    )
    processor = Mock(return_value=expected)

    execution = execute_batch(batch_options(tmp_path), processor=processor, config={})

    assert execution.result is expected
    assert execution.unmatched_patterns == ()
    assert execution.expanded_files[0].endswith("links.md")
    assert processor.call_args.kwargs["header_manager"] is not None


def test_crawl_execution_reports_invalid_and_failed_starts_without_typer(tmp_path):
    manager = Mock()
    manager.signal_handling.return_value = nullcontext(manager)
    crawler = Mock(return_value=CrawlResult(success=False, error="offline"))
    options = crawl_options(tmp_path, start_urls=["not-a-url", "https://example.com"])

    execution = execute_crawls(
        options,
        crawler=crawler,
        config={},
        state_factory=lambda: manager,
    )

    assert execution.invalid_urls == ["not-a-url"]
    assert execution.failed_count == 2
    assert execution.processed_page_count == 0
    crawler.assert_called_once()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"follow_option": "["}, "Invalid --follow regex pattern"),
        ({"max_depth": -1}, "--max-depth must be non-negative"),
        ({"max_pages": 0}, "--max-pages must be positive"),
        ({"delay": -0.1}, "--delay must be"),
        ({"rate_limit": 0}, "--rate-limit must be positive"),
    ],
)
def test_crawl_policy_validation_precedes_side_effects(tmp_path, changes, message):
    crawler = Mock()
    output = tmp_path / "output"

    with pytest.raises(CommandUsageError, match=message):
        execute_crawls(
            crawl_options(tmp_path, **changes),
            crawler=crawler,
            config={},
        )

    crawler.assert_not_called()
    assert not output.exists()
