"""Atomic persistence for versioned crawl-state documents."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from html2md.config.writer import atomic_write_json
from html2md.utils.state_schema import CrawlState


logger = logging.getLogger(__name__)


class CrawlStateStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def load(self, crawl_id: str) -> Optional[CrawlState]:
        state_file = self.state_dir / f"{crawl_id}.json"
        if not state_file.exists():
            logger.error("State file not found: %s", state_file)
            return None
        for candidate in (state_file, state_file.with_suffix(".bak")):
            if not candidate.exists():
                continue
            try:
                return CrawlState.from_dict(
                    json.loads(candidate.read_text(encoding="utf-8"))
                )
            except Exception as error:
                logger.error("Failed to load state from %s: %s", candidate, error)
        return None

    def save(self, state: CrawlState) -> None:
        state_file = self.state_dir / f"{state.crawl_id}.json"
        state.last_checkpoint = datetime.now().isoformat()
        if state_file.exists():
            backup_file = state_file.with_suffix(".bak")
            shutil.copy2(state_file, backup_file)
            if os.name == "posix":
                os.chmod(backup_file, 0o600)
        atomic_write_json(state_file, state.to_dict(), indent=2, private=True)

    def list_resumable(self) -> list[Dict[str, Any]]:
        crawls: list[Dict[str, Any]] = []
        for state_file in self.state_dir.glob("*.json"):
            try:
                state = CrawlState.from_dict(
                    json.loads(state_file.read_text(encoding="utf-8"))
                )
                crawls.append(
                    {
                        "crawl_id": state.crawl_id,
                        "start_url": state.start_url,
                        "created_at": state.created_at,
                        "last_checkpoint": state.last_checkpoint,
                        "urls_processed": len(state.urls_visited),
                        "urls_queued": len(state.urls_queued),
                        "state_file": str(state_file),
                    }
                )
            except Exception as error:
                logger.error("Failed to read state file %s: %s", state_file, error)
        crawls.sort(key=lambda item: str(item["last_checkpoint"]), reverse=True)
        return crawls

    def clean_older_than(self, days: int) -> int:
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        cleaned = 0
        for state_file in self.state_dir.glob("*.json"):
            if state_file.stat().st_mtime >= cutoff_time:
                continue
            state_file.unlink()
            state_file.with_suffix(".bak").unlink(missing_ok=True)
            cleaned += 1
        return cleaned

    def export(self, crawl_id: str, output_file: Path) -> None:
        state = self.load(crawl_id)
        if state is None:
            raise ValueError(f"Crawl {crawl_id} not found")
        atomic_write_json(output_file, state.to_dict(), indent=2, private=True)

    def import_file(self, input_file: Path) -> CrawlState:
        state = CrawlState.from_dict(
            json.loads(Path(input_file).read_text(encoding="utf-8"))
        )
        state.crawl_id = str(uuid.uuid4())
        self.save(state)
        return state
