from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from email.utils import format_datetime

import requests

from typer.testing import CliRunner

from grab2md.cli.cli import app
from grab2md.network.request_scheduler import SequentialRequestScheduler


def test_crawl_help_exposes_sequential_policy_not_concurrency_controls():
    result = CliRunner().invoke(app, ["crawl", "--help"])

    assert result.exit_code == 0
    assert "--max-concurrent" not in result.stdout
    assert "sequential" in result.stdout
    assert "destination" in result.stdout
    assert "origin" in result.stdout


def test_polite_mode_has_a_nonzero_floor_and_doubles_larger_delays():
    floor = SequentialRequestScheduler(minimum_delay=0.0, polite=True)
    doubled = SequentialRequestScheduler(minimum_delay=1.5, polite=True)

    assert floor.minimum_delay == 1.0
    assert doubled.minimum_delay == 3.0


def test_adaptive_rate_delay_is_applied_before_request():
    limiter = MagicMock()
    limiter.can_make_request.return_value = (True, 2.5)
    limiter.record_request_start.return_value = 0.0
    sleep = MagicMock()
    with patch(
        "grab2md.network.request_scheduler.GlobalRateLimiter", return_value=limiter
    ):
        scheduler = SequentialRequestScheduler(
            requests_per_minute=30, sleep=sleep, clock=lambda: 0.0
        )

    request = scheduler.before_request("https://example.com/page")
    scheduler.after_request(request, success=True, response_time=0.25)

    sleep.assert_called_once_with(2.5)
    limiter.record_request_start.assert_called_once_with("https://example.com/page")
    assert limiter.record_request_end.call_args.args[2] is True
    assert limiter.record_request_end.call_args.kwargs["response_time"] == 0.25


def test_retry_after_defers_the_next_request_to_the_same_origin():
    sleep = MagicMock()
    scheduler = SequentialRequestScheduler(sleep=sleep, clock=lambda: 0.0)
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "7"

    first = scheduler.before_request("https://example.com/one")
    scheduler.after_response(first, response)
    scheduler.before_request("https://example.com/two")

    sleep.assert_called_once_with(7.0)


def test_http_date_retry_after_uses_the_scheduler_clock():
    now = datetime(2026, 7, 19, tzinfo=timezone.utc).timestamp()
    sleep = MagicMock()
    scheduler = SequentialRequestScheduler(sleep=sleep, clock=lambda: now)
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = format_datetime(
        datetime(2026, 7, 19, 0, 0, 11, tzinfo=timezone.utc), usegmt=True
    )

    first = scheduler.before_request("https://example.com/one")
    scheduler.after_response(first, response)
    scheduler.before_request("https://example.com/two")

    sleep.assert_called_once_with(11.0)
