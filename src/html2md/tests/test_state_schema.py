"""Compatibility fixtures for versioned crawl-state persistence."""

import json

import pytest

from html2md.utils.state_manager import StateManager
from html2md.utils.state_schema import (
    CURRENT_STATE_VERSION,
    CrawlState,
    migrate_state_document,
)
from html2md.utils.state_store import CrawlStateStore


def test_unversioned_legacy_fixture_migrates_to_current_schema():
    legacy = {
        "crawl_id": "legacy-id",
        "start_url": "https://example.com",
        "output_dir": "/tmp/output",
        "progress": {"urls_queued": [["https://example.com/next", 1]]},
    }

    state = CrawlState.from_dict(legacy)

    assert state.version == CURRENT_STATE_VERSION
    assert state.urls_queued == [("https://example.com/next", 1)]
    assert state.urls_visited == {}
    assert state.urls_failed == {}


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

    store.save(state)
    loaded = store.load("fixture")

    assert loaded is not None
    assert loaded.start_url == state.start_url
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
