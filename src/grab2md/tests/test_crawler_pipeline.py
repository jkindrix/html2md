"""End-to-end unit tests for crawler request orchestration."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from grab2md.markdown.converter import html_to_markdown
from grab2md.markdown.archive import ArtifactManifest, ArtifactStore, OutputPlanner
from grab2md.markdown.content_extractor import ContentMode
from grab2md.markdown.crawl_engine import (
    CrawlFrontier,
    CrawlOptions,
    CrawlScope,
    FrontierItem,
    SequentialCrawlEngine,
)
from grab2md.markdown.crawler import crawl_website
from grab2md.markdown.pipeline import PagePipeline
from grab2md.network.request_handler import FetchResult
from grab2md.network.safe_http import UnsafeNetworkTarget
from grab2md.utils.state_manager import StateManager

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
    options = {
        "max_pages": 1,
        "max_depth": 0,
        "respect_robots": False,
    }
    options.update(kwargs)
    return crawl_website(
        "https://example.com",
        tmp_path / "output",
        state_manager=StateManager(state_dir=tmp_path / "states"),
        **options,
    )


def test_each_page_is_fetched_once_and_same_body_is_converted(tmp_path):
    result = fetch_result()
    with patch("grab2md.markdown.crawler.fetch_html", return_value=result) as fetch:
        crawl_result = crawl(tmp_path)

    assert crawl_result.success is True
    fetch.assert_called_once()
    output = Path(crawl_result.url_mapping["https://example.com"])
    assert output.read_text(encoding="utf-8").strip() == "# Fetched once"
    assert fetch.call_args.kwargs["request_scheduler"] is not None


def test_crawl_decodes_charsetless_utf8_from_raw_response_bytes(tmp_path):
    html = "<html><body><h1>café ☕</h1></body></html>"
    fetched = FetchResult(
        requested_url="https://example.com",
        final_url="https://example.com",
        status_code=200,
        headers={"Content-Type": "text/html"},
        content=html.encode("utf-8"),
    )
    with patch("grab2md.markdown.crawler.fetch_html", return_value=fetched):
        result = crawl(tmp_path)

    output = Path(result.url_mapping["https://example.com"])
    assert output.read_text(encoding="utf-8").strip() == "# café ☕"


def test_acquired_page_rejects_success_without_status_under_optimized_python():
    result = FetchResult(
        requested_url="https://example.com",
        final_url="https://example.com",
        content=b"<h1>Missing status</h1>",
    )

    with pytest.raises(RuntimeError, match="missing an HTTP status"):
        SequentialCrawlEngine._acquired_page(
            FrontierItem("https://example.com", 0), result
        )


def test_discovery_failure_does_not_persist_or_double_count_page(tmp_path):
    manager = StateManager(state_dir=tmp_path / "states")
    with (
        patch("grab2md.markdown.crawler.fetch_html", return_value=fetch_result()),
        patch(
            "grab2md.markdown.crawl_engine.extract_links_from_html",
            side_effect=ValueError("malformed discovery fixture"),
        ),
    ):
        result = crawl_website(
            "https://example.com",
            tmp_path / "output",
            max_pages=1,
            max_depth=1,
            respect_robots=False,
            state_manager=manager,
        )

    assert result.processed_count == 0
    assert result.failed_count == 1
    assert result.url_mapping == {}
    assert not list((tmp_path / "output").rglob("*.md"))
    assert manager.current_state is not None
    assert manager.current_state.urls_visited == {}
    assert manager.current_state.urls_failed == {
        "https://example.com": "malformed discovery fixture"
    }


def test_frontier_deduplicates_fragments_but_preserves_query_resources():
    frontier = CrawlFrontier([("https://example.com/page#top", 0)])

    assert frontier.enqueue("https://example.com/page#details", 0) is False
    assert frontier.enqueue("https://example.com/page?view=one#top", 0) is True
    assert frontier.enqueue("https://example.com/page?view=two", 0) is True
    assert frontier.snapshot() == [
        ("https://example.com/page#top", 0),
        ("https://example.com/page?view=one#top", 0),
        ("https://example.com/page?view=two", 0),
    ]


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
        patch("grab2md.markdown.crawler.fetch_html", return_value=fetched),
        patch("grab2md.markdown.crawler.RobotsChecker", return_value=checker),
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
        patch("grab2md.markdown.crawler.RobotsChecker", return_value=checker),
        patch(
            "grab2md.markdown.crawler.fetch_html", return_value=fetch_result()
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
        "grab2md.markdown.crawler.fetch_html", side_effect=[first, second]
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

    with patch("grab2md.markdown.pipeline.guarded_request", side_effect=guarded):
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
        "grab2md.markdown.crawler.fetch_html",
        side_effect=[throttled, fetch_result()],
    ) as fetch:
        result = crawl(tmp_path, max_pages=2)

    assert result.processed_count == 1
    assert fetch.call_count == 2


def test_resumed_retry_cannot_exceed_cumulative_max_pages(tmp_path):
    manager = StateManager(state_dir=tmp_path / "states")
    throttled = fetch_result(429, "slow down", {"Retry-After": "7"})
    with patch(
        "grab2md.markdown.crawler.fetch_html",
        side_effect=[throttled, fetch_result()],
    ) as fetch:
        first = crawl_website(
            "https://example.com",
            tmp_path / "output",
            max_pages=1,
            max_depth=0,
            respect_robots=False,
            state_manager=manager,
        )
        resumed = crawl_website(
            "https://example.com",
            tmp_path / "output",
            max_pages=1,
            max_depth=0,
            respect_robots=False,
            state_manager=manager,
            resume_crawl_id=first.crawl_id,
        )

    assert fetch.call_count == 1
    assert resumed.processed_count == 0
    assert manager.current_state is not None
    assert manager.current_state.attempted_count == 1
    assert manager.current_state.retry_attempts == {"https://example.com/": 1}
    assert manager.current_state.urls_queued == [("https://example.com", 0)]


def test_retry_ceiling_survives_repeated_resumes(tmp_path):
    manager = StateManager(state_dir=tmp_path / "states")
    throttled = fetch_result(429, "slow down", {"Retry-After": "7"})
    crawl_id = None

    with patch("grab2md.markdown.crawler.fetch_html", return_value=throttled) as fetch:
        for cumulative_budget in (1, 2, 3):
            result = crawl_website(
                "https://example.com",
                tmp_path / "output",
                max_pages=cumulative_budget,
                max_depth=0,
                respect_robots=False,
                state_manager=manager,
                resume_crawl_id=crawl_id,
            )
            crawl_id = result.crawl_id

    assert fetch.call_count == 3
    assert manager.current_state is not None
    assert manager.current_state.attempted_count == 3
    assert manager.current_state.retry_attempts == {}
    assert manager.current_state.urls_queued == []
    assert manager.current_state.urls_failed == {"https://example.com": "HTTP 429"}


def test_max_pages_is_a_hard_attempt_budget_including_failures(tmp_path):
    manager = StateManager(state_dir=tmp_path / "states")
    state = manager.create_new_state(
        "https://example.com/one",
        str(tmp_path / "output"),
        {"scope_url": "https://example.com/one"},
    )
    state.urls_queued = [
        ("https://example.com/one", 0),
        ("https://example.com/two", 0),
        ("https://example.com/three", 0),
    ]
    manager.save_state()
    failure = FetchResult(
        requested_url="https://example.com/one",
        final_url="https://example.com/one",
        error="offline",
    )

    with patch("grab2md.markdown.crawler.fetch_html", return_value=failure) as fetch:
        result = crawl_website(
            state.start_url,
            tmp_path / "output",
            max_pages=1,
            respect_robots=False,
            state_manager=manager,
            resume_crawl_id=state.crawl_id,
        )

    assert fetch.call_count == 1
    assert result.processed_count == 0
    assert result.failed_count == 1
    assert manager.current_state is not None
    assert manager.current_state.urls_queued == [
        ("https://example.com/two", 0),
        ("https://example.com/three", 0),
    ]


def test_disabled_checkpoints_do_not_mutate_resume_scope(tmp_path):
    redirected = FetchResult(
        requested_url="https://example.com",
        final_url="https://www.example.com/final",
        status_code=200,
        body=HTML,
    )
    manager = StateManager(state_dir=tmp_path / "states")
    with patch("grab2md.markdown.crawler.fetch_html", return_value=redirected):
        result = crawl_website(
            "https://example.com",
            tmp_path / "output",
            max_pages=1,
            respect_robots=False,
            enable_checkpoints=False,
            state_manager=manager,
        )

    assert result.success is True
    assert manager.current_state is not None
    assert manager.current_state.config["scope_url"] == "https://example.com"
    assert [item.message for item in manager.current_state.checkpoints] == [
        "Initial state"
    ]


def test_no_progress_suppresses_callbacks_without_suppressing_the_crawl(tmp_path):
    progress = Mock()
    with patch("grab2md.markdown.crawler.fetch_html", return_value=fetch_result()):
        result = crawl(tmp_path, show_progress=False, progress_callback=progress)

    assert result.success is True
    progress.assert_not_called()


def test_partial_failure_checkpoint_describes_the_terminal_state(tmp_path):
    manager = StateManager(state_dir=tmp_path / "states")
    failed = FetchResult(
        requested_url="https://example.com",
        final_url="https://example.com",
        status_code=500,
        error="HTTP 500",
    )
    with patch("grab2md.markdown.crawler.fetch_html", return_value=failed):
        result = crawl_website(
            "https://example.com",
            tmp_path / "output",
            max_pages=1,
            respect_robots=False,
            state_manager=manager,
        )

    assert result.failed_count == 1
    assert manager.current_state is not None
    assert manager.current_state.checkpoints[-1].message == (
        "Crawl completed with 1 failed URLs"
    )


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
    headers.get_headers.return_value = {"User-Agent": "grab2md"}

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


def test_success_checkpoint_contains_links_discovered_from_completed_page(tmp_path):
    url = "https://example.com/page"
    child = "https://example.com/child"
    frontier = CrawlFrontier([(url, 0)])
    checkpoint = Mock()
    snapshots = []
    checkpoint.succeeded.side_effect = lambda _url, _output, current: snapshots.append(
        current.snapshot()
    )
    headers = Mock()
    headers.get_headers.return_value = {"User-Agent": "grab2md"}
    fetch = Mock(
        return_value=FetchResult(
            url,
            url,
            status_code=200,
            body=f'<html><a href="{child}">Child</a></html>',
        )
    )
    store = Mock()
    store.write_text.side_effect = ArtifactStore.write_text
    engine = SequentialCrawlEngine(
        frontier=frontier,
        scope=CrawlScope(url, "domain-only"),
        robots=None,
        scheduler=Mock(),
        page_pipeline=PagePipeline(),
        artifact_store=store,
        checkpoint_store=checkpoint,
        event_sink=Mock(),
        session=Mock(),
        network_policy=Mock(),
        header_manager=headers,
        manifest=ArtifactManifest(),
        output_planner=OutputPlanner(tmp_path),
        url_mapping={},
        fetch_page=fetch,
        options=CrawlOptions(
            max_depth=1,
            max_pages=1,
            content_mode=ContentMode.FULL,
            selector=None,
            download_images=False,
            images_dir="images",
            include_metadata=False,
            allow_private_network=False,
        ),
    )

    engine.run()

    assert snapshots == [[(child, 1)]]
