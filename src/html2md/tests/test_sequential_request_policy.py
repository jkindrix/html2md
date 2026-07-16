import threading

from typer.testing import CliRunner

from html2md.cli.cli import app
from html2md.network.concurrent_limiter import ConcurrentConfig, ConcurrentLimiter


def test_crawl_help_exposes_sequential_policy_not_concurrency_controls():
    result = CliRunner().invoke(app, ["crawl", "--help"])

    assert result.exit_code == 0
    assert "--max-concurrent" not in result.stdout
    assert "sequential" in result.stdout


def test_only_one_request_slot_can_be_active_across_threads():
    limiter = ConcurrentLimiter(ConcurrentConfig())
    acquired = threading.Event()
    release = threading.Event()
    outcomes = []

    def first_request():
        outcomes.append(limiter.acquire_slot("https://example.com/first"))
        acquired.set()
        release.wait(timeout=2)
        limiter.release_slot("https://example.com/first")

    def competing_request():
        assert acquired.wait(timeout=2)
        outcomes.append(limiter.acquire_slot("https://other.example/second"))
        release.set()

    threads = [threading.Thread(target=first_request), threading.Thread(target=competing_request)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert all(not thread.is_alive() for thread in threads)
    assert outcomes == [True, False]
    assert limiter.get_progress()["currently_active"] == 0


def test_request_state_methods_share_one_reentrant_lock_without_deadlock():
    limiter = ConcurrentLimiter()
    url = "https://example.com/page"

    assert limiter.acquire_slot(url)
    limiter.release_slot(url, success=False, status_code=500)
    limiter.reset_domain("example.com")

    assert limiter.get_domain_stats("example.com")["active_connections"] == 0
