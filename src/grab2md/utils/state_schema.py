"""Versioned crawl-state schema and migrations."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_STATE_VERSION = "1.1"
LEGACY_STATE_VERSION = "1.0"


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return value


def migrate_state_document(document: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize supported historical documents without mutating caller data."""
    migrated = json_safe(document)
    version = str(migrated.get("version", LEGACY_STATE_VERSION))
    if version not in {LEGACY_STATE_VERSION, CURRENT_STATE_VERSION}:
        raise ValueError(f"Unsupported crawl-state version: {version}")
    migrated.setdefault("progress", {})
    progress = migrated["progress"]
    progress.setdefault("urls_queued", [])
    progress.setdefault("urls_visited", {})
    progress.setdefault("urls_failed", {})
    if version == LEGACY_STATE_VERSION:
        terminal_urls = set(progress["urls_visited"]) | set(progress["urls_failed"])
        progress.setdefault("attempted_count", len(terminal_urls))
        progress.setdefault("retry_attempts", {})
    else:
        progress.setdefault("attempted_count", 0)
        progress.setdefault("retry_attempts", {})
    migrated["version"] = CURRENT_STATE_VERSION
    migrated.setdefault("checkpoints", [])
    return migrated


@dataclass
class CrawlStatistics:
    total_urls: int = 0
    urls_processed: int = 0
    urls_failed: int = 0
    bytes_downloaded: int = 0
    start_time: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrawlStatistics":
        return cls(**data)


@dataclass
class CheckpointInfo:
    timestamp: str
    trigger: str
    stats_snapshot: Dict[str, Any]
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointInfo":
        return cls(**data)


@dataclass
class CrawlState:
    version: str = CURRENT_STATE_VERSION
    crawl_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_checkpoint: str = field(default_factory=lambda: datetime.now().isoformat())
    start_url: str = ""
    output_dir: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    urls_queued: List[Tuple[str, int]] = field(default_factory=list)
    urls_visited: Dict[str, str] = field(default_factory=dict)
    urls_failed: Dict[str, str] = field(default_factory=dict)
    attempted_count: int = 0
    retry_attempts: Dict[str, int] = field(default_factory=dict)
    statistics: CrawlStatistics = field(default_factory=CrawlStatistics)
    checkpoints: List[CheckpointInfo] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "crawl_id": self.crawl_id,
            "created_at": self.created_at,
            "last_checkpoint": self.last_checkpoint,
            "start_url": self.start_url,
            "output_dir": str(self.output_dir),
            "config": json_safe(self.config),
            "progress": {
                "urls_queued": json_safe(self.urls_queued),
                "urls_visited": json_safe(self.urls_visited),
                "urls_failed": json_safe(self.urls_failed),
                "attempted_count": self.attempted_count,
                "retry_attempts": json_safe(self.retry_attempts),
                "statistics": self.statistics.to_dict(),
            },
            "checkpoints": [checkpoint.to_dict() for checkpoint in self.checkpoints],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrawlState":
        data = migrate_state_document(data)
        state = cls(
            version=data["version"],
            crawl_id=data.get("crawl_id", str(uuid.uuid4())),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_checkpoint=data.get("last_checkpoint", datetime.now().isoformat()),
            start_url=data.get("start_url", ""),
            output_dir=str(data.get("output_dir", "")),
            config=data.get("config", {}),
        )
        progress = data["progress"]
        state.urls_queued = [tuple(item) for item in progress["urls_queued"]]
        state.urls_visited = progress["urls_visited"]
        state.urls_failed = progress["urls_failed"]
        state.attempted_count = int(progress["attempted_count"])
        state.retry_attempts = {
            str(url): int(count) for url, count in progress["retry_attempts"].items()
        }
        if state.attempted_count < 0 or any(
            count < 0 for count in state.retry_attempts.values()
        ):
            raise ValueError("Crawl-state attempt counts cannot be negative")
        if "statistics" in progress:
            state.statistics = CrawlStatistics.from_dict(progress["statistics"])
        state.checkpoints = [
            CheckpointInfo.from_dict(checkpoint)
            for checkpoint in data.get("checkpoints", [])
        ]
        return state
