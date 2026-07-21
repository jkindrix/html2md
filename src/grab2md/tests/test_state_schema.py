"""Compatibility fixtures for versioned crawl-state persistence."""

import json

import pytest

from grab2md.utils.state_manager import StateManager
from grab2md.utils.state_schema import (
    CURRENT_STATE_VERSION,
    CrawlState,
    migrate_state_document,
)
from grab2md.utils.state_store import CrawlStateStore


def test_unversioned_legacy_fixture_migrates_to_current_schema():
    legacy = {
        "crawl_id": "legacy-id",
        "start_url": "https://example.com",
        "output_dir": "/tmp/output",
        "progress": {
            "urls_queued": [["https://example.com/next", 1]],
            "urls_visited": {"https://example.com": "index.md"},
            "urls_failed": {"https://example.com/missing": "HTTP 404"},
        },
    }

    state = CrawlState.from_dict(legacy)

    assert state.version == CURRENT_STATE_VERSION
    assert state.urls_queued == [("https://example.com/next", 1)]
    assert state.urls_visited == {"https://example.com": "index.md"}
    assert state.urls_failed == {"https://example.com/missing": "HTTP 404"}
    assert state.attempted_count == 2
    assert state.retry_attempts == {}


def test_version_1_state_migrates_attempt_accounting():
    state = CrawlState.from_dict(
        {
            "version": "1.0",
            "progress": {
                "urls_visited": {"https://example.com": "index.md"},
                "urls_failed": {},
            },
        }
    )

    assert state.version == CURRENT_STATE_VERSION
    assert state.attempted_count == 1
    assert state.retry_attempts == {}


def test_future_state_version_fails_closed():
    with pytest.raises(ValueError, match="Unsupported crawl-state version"):
        migrate_state_document({"version": "99.0"})


def test_store_round_trip_is_independent_of_checkpoint_or_signal_policy(tmp_path):
    store = CrawlStateStore(tmp_path)
    state = CrawlState(
        crawl_id="fixture",
        start_url="https://example.com",
        output_dir=str(tmp_path / "output"),
    )
    state.attempted_count = 3
    state.retry_attempts = {"https://example.com/retry": 2}

    store.save(state)
    loaded = store.load("fixture")

    assert loaded is not None
    assert loaded.start_url == state.start_url
    assert loaded.attempted_count == 3
    assert loaded.retry_attempts == {"https://example.com/retry": 2}
    assert not hasattr(store, "checkpoint_interval")
    assert not hasattr(store, "install_signal_handlers")


def test_manager_loads_legacy_fixture_through_store_migration(tmp_path):
    document = {
        "crawl_id": "legacy",
        "start_url": "https://example.com",
        "output_dir": str(tmp_path / "output"),
        "progress": {"urls_visited": {"https://example.com": "page.md"}},
    }
    (tmp_path / "legacy.json").write_text(json.dumps(document), encoding="utf-8")

    manager = StateManager(state_dir=tmp_path)
    state = manager.load_state("legacy")

    assert state is not None
    assert state.version == CURRENT_STATE_VERSION
    assert state.urls_visited == {"https://example.com": "page.md"}


def test_store_rejects_traversal_and_external_state_symlinks(tmp_path):
    state_dir = tmp_path / "states"
    state_dir.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            CrawlState(
                crawl_id="outside", start_url="https://outside.example"
            ).to_dict()
        ),
        encoding="utf-8",
    )
    store = CrawlStateStore(state_dir)

    with pytest.raises(ValueError, match="Invalid crawl ID"):
        store.load("../outside")

    linked = state_dir / "linked.json"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks are unavailable on this platform")
    with pytest.raises(ValueError, match="escapes configured root"):
        store.load("linked")


def test_store_resolves_only_unambiguous_displayed_id_prefixes(tmp_path):
    store = CrawlStateStore(tmp_path)
    first_id = "12345678-1111-4111-8111-111111111111"
    second_id = "12345678-2222-4222-8222-222222222222"
    unique_id = "abcdef12-3333-4333-8333-333333333333"
    for crawl_id in (first_id, second_id, unique_id):
        store.save(CrawlState(crawl_id=crawl_id, start_url="https://example.com"))

    loaded = store.load("abcdef12")

    assert loaded is not None
    assert loaded.crawl_id == unique_id
    with pytest.raises(ValueError, match="ambiguous"):
        store.load("12345678")
