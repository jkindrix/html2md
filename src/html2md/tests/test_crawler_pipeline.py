"""End-to-end unit tests for crawler request orchestration."""

from unittest.mock import Mock, patch

import pytest

from html2md.markdown.converter import html_to_markdown
from html2md.markdown.crawler import crawl_website
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


def limiter_mock(acquire=True):
    limiter = Mock()
    limiter.acquire_slot.side_effect = acquire if isinstance(acquire, list) else None
    if not isinstance(acquire, list):
        limiter.acquire_slot.return_value = acquire
    limiter.should_wait.return_value = None
    limiter.get_progress.return_value = {"total_completed": 0}
    return limiter


def test_each_page_is_fetched_once_and_same_body_is_converted(tmp_path):
    result = fetch_result()
    with (
        patch("html2md.markdown.crawler.fetch_html", return_value=result) as fetch,
        patch(
            "html2md.markdown.crawler.html_content_to_markdown",
            return_value="# Converted",
        ) as convert,
    ):
        crawl_result = crawl(tmp_path)

    assert crawl_result.success is True
    fetch.assert_called_once()
    assert convert.call_args.args[:2] == (HTML, "https://example.com/final")


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


def test_concurrency_deferred_url_is_requeued_not_dropped(tmp_path):
    limiter = limiter_mock(acquire=[False, True])
    with (
        patch("html2md.markdown.crawler.ConcurrentLimiter", return_value=limiter),
        patch(
            "html2md.markdown.crawler.fetch_html", return_value=fetch_result()
        ) as fetch,
    ):
        result = crawl(tmp_path)

    assert result.processed_count == 1
    assert limiter.acquire_slot.call_count == 2
    fetch.assert_called_once()


def test_adaptive_delay_is_applied_before_fetch(tmp_path):
    rate_limiter = Mock()
    rate_limiter.can_make_request.return_value = (True, 2.5)
    rate_limiter.get_all_stats.return_value = {}
    with (
        patch("html2md.markdown.crawler.GlobalRateLimiter", return_value=rate_limiter),
        patch("html2md.markdown.crawler.fetch_html", return_value=fetch_result()),
        patch("html2md.markdown.crawler.time.sleep") as sleep,
    ):
        result = crawl(tmp_path, rate_limit=30)

    assert result.processed_count == 1
    sleep.assert_called_once_with(2.5)
    rate_limiter.record_request_start.assert_called_once_with("https://example.com")
    assert rate_limiter.record_request_end.call_args.args[2] is True
    assert rate_limiter.record_request_end.call_args.kwargs["response_time"] == 0.25


def test_429_retry_after_requeues_and_reaches_concurrency_policy(tmp_path):
    limiter = limiter_mock()
    throttled = fetch_result(429, "slow down", {"Retry-After": "7"})
    with (
        patch("html2md.markdown.crawler.ConcurrentLimiter", return_value=limiter),
        patch(
            "html2md.markdown.crawler.fetch_html",
            side_effect=[throttled, fetch_result()],
        ) as fetch,
    ):
        result = crawl(tmp_path)

    assert result.processed_count == 1
    assert fetch.call_count == 2
    assert limiter.release_slot.call_args_list[0].kwargs == {
        "success": False,
        "status_code": 429,
        "retry_after": 7,
    }
