"""End-to-end unit tests for crawler request orchestration."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from html2md.markdown.converter import html_to_markdown
from html2md.markdown.archive import ArtifactManifest, ArtifactStore, OutputPlanner
from html2md.markdown.content_extractor import ContentMode
from html2md.markdown.crawl_engine import (
    CrawlFrontier,
    CrawlOptions,
    CrawlScope,
    SequentialCrawlEngine,
)
from html2md.markdown.crawler import crawl_website
from html2md.markdown.pipeline import PagePipeline
from html2md.network.request_handler import FetchResult
from html2md.network.safe_http import UnsafeNetworkTarget
from html2md.utils.state_manager import StateManager


HTML = "<html><body><h1>Fetched once</h1></body></html>"


def fetch_result(status=200, body=HTML, headers=None):
    return FetchResult(
        requested_url="https://example.com",
        final_url="https://example.com/final",
        status_code=status,
        headers=headers or {},
        body=body,
        error=None if status < 400 else f"HTTP {status}",
        elapsed=0.25,
    )


def crawl(tmp_path, **kwargs):
    return crawl_website(
        "https://example.com",
        tmp_path / "output",
        max_pages=1,
        max_depth=0,
        respect_robots=False,
        state_manager=StateManager(state_dir=tmp_path / "states"),
        **kwargs,
    )


def test_each_page_is_fetched_once_and_same_body_is_converted(tmp_path):
    result = fetch_result()
    with patch("html2md.markdown.crawler.fetch_html", return_value=result) as fetch:
        crawl_result = crawl(tmp_path)

    assert crawl_result.success is True
    fetch.assert_called_once()
    output = Path(crawl_result.url_mapping["https://example.com"])
    assert output.read_text(encoding="utf-8").strip() == "# Fetched once"
    assert fetch.call_args.kwargs["request_scheduler"] is not None


def test_redirect_final_url_sets_discovery_scope_before_robots_checks(tmp_path):
    body = """<html><body>
    <a href="next">Next</a>
    <a href="https://evilexample.com/trap">Trap</a>
    </body></html>"""
    fetched = FetchResult(
        requested_url="https://example.com/start",
        final_url="https://www.example.com/docs/start",
        status_code=200,
        body=body,
    )
    state_manager = StateManager(state_dir=tmp_path / "states")
    checker = Mock()
    checker.can_fetch.return_value = True
    checker.get_crawl_delay.return_value = None
    checker.filter_urls.side_effect = lambda links: links

    with (
        patch("html2md.markdown.crawler.fetch_html", return_value=fetched),
        patch("html2md.markdown.crawler.RobotsChecker", return_value=checker),
    ):
        result = crawl_website(
            "https://example.com/start",
            tmp_path / "output",
            max_pages=1,
            max_depth=1,
            state_manager=state_manager,
        )

    assert result.success is True
    checker.filter_urls.assert_called_once_with(["https://www.example.com/docs/next"])
    assert state_manager.current_state.urls_queued == [
        ("https://www.example.com/docs/next", 1)
    ]
    assert (
        state_manager.current_state.config["scope_url"]
        == "https://www.example.com/docs/start"
    )


def test_crawl_redirect_callback_applies_scope_and_robots_before_hop(tmp_path):
    checker = Mock()
    checker.can_fetch.return_value = True
    checker.get_crawl_delay.return_value = None
    with (
        patch("html2md.markdown.crawler.RobotsChecker", return_value=checker),
        patch(
            "html2md.markdown.crawler.fetch_html", return_value=fetch_result()
        ) as fetch,
    ):
        result = crawl_website(
            "https://example.com",
            tmp_path / "output",
            max_pages=1,
            max_depth=0,
            state_manager=StateManager(state_dir=tmp_path / "states"),
        )

    assert result.success is True
    validator = fetch.call_args.kwargs["redirect_validator"]
    validator("https://example.com", "https://www.example.com/final")
    checker.can_fetch.assert_any_call("https://www.example.com/final")


def test_nonstarting_crawl_redirect_cannot_leave_the_established_scope(tmp_path):
    first = FetchResult(
        requested_url="https://example.com",
        final_url="https://example.com",
        status_code=200,
        body='<html><a href="/next">Next</a></html>',
    )
    second = FetchResult(
        requested_url="https://example.com/next",
        final_url="https://example.com/next",
        status_code=200,
        body=HTML,
    )
    with patch(
        "html2md.markdown.crawler.fetch_html", side_effect=[first, second]
    ) as fetch:
        result = crawl_website(
            "https://example.com",
            tmp_path / "output",
            max_pages=2,
            max_depth=1,
            respect_robots=False,
            state_manager=StateManager(state_dir=tmp_path / "states"),
        )

    assert result.success is True
    validator = fetch.call_args_list[1].kwargs["redirect_validator"]
    with pytest.raises(UnsafeNetworkTarget, match="scope"):
        validator("https://example.com/next", "https://outside.example/final")


def test_request_headers_do_not_leak_into_shared_session():
    session = Mock()
    session.headers = {"User-Agent": "shared"}
    response = Mock(
        status_code=200,
        text=HTML,
        content=HTML.encode(),
        encoding="utf-8",
        headers={},
    )
    response.raise_for_status.return_value = None
    session.get.return_value = response

    def guarded(source_session, _method, url, **kwargs):
        return source_session.get(
            url,
            headers=kwargs.get("headers"),
            timeout=kwargs.get("timeout"),
        )

    with patch("html2md.markdown.pipeline.guarded_request", side_effect=guarded):
        html_to_markdown(
            "https://other.example/page",
            session=session,
            headers={"Referer": "https://source.example/"},
        )

    assert session.headers == {"User-Agent": "shared"}
    session.get.assert_called_once_with(
        "https://other.example/page",
        headers={"Referer": "https://source.example/"},
        timeout=30,
    )


def test_429_response_is_requeued_and_retried(tmp_path):
    throttled = fetch_result(429, "slow down", {"Retry-After": "7"})
    with patch(
        "html2md.markdown.crawler.fetch_html",
        side_effect=[throttled, fetch_result()],
    ) as fetch:
        result = crawl(tmp_path)

    assert result.processed_count == 1
    assert fetch.call_count == 2


def test_engine_uses_injected_pipeline_store_checkpoint_and_event_sink(tmp_path):
    url = "https://example.com/page"
    frontier = CrawlFrontier([(url, 0)])
    checkpoint = Mock()
    events = Mock()
    store = Mock()
    store.write_text.side_effect = ArtifactStore.write_text
    fetch = Mock(
        return_value=FetchResult(url, url, status_code=200, body="<h1>Page</h1>")
    )
    headers = Mock()
    headers.get_headers.return_value = {"User-Agent": "html2md"}

    engine = SequentialCrawlEngine(
        frontier=frontier,
        scope=CrawlScope(url, "domain-only"),
        robots=None,
        scheduler=Mock(),
        page_pipeline=PagePipeline(),
        artifact_store=store,
        checkpoint_store=checkpoint,
        event_sink=events,
        session=Mock(),
        network_policy=Mock(),
        header_manager=headers,
        manifest=ArtifactManifest(),
        output_planner=OutputPlanner(tmp_path),
        url_mapping={},
        fetch_page=fetch,
        options=CrawlOptions(
            max_depth=0,
            max_pages=1,
            content_mode=ContentMode.FULL,
            selector=None,
            download_images=False,
            images_dir="images",
            include_metadata=False,
            allow_private_network=False,
        ),
    )

    run = engine.run()

    assert run.processed_count == 1
    store.write_text.assert_called_once()
    checkpoint.succeeded.assert_called_once()
    assert any(call.args[2] == "saved" for call in events.call_args_list)
