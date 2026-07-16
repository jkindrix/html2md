"""
State persistence and resume capability for html2md crawler.

This module provides functionality to save crawler state to disk,
enabling interruption and resumption of long-running crawl operations.
"""

import json
import signal
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
import logging
import shutil

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    """Normalize supported state values to JSON-compatible primitives."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


@dataclass
class CrawlStatistics:
    """Statistics for a crawl session."""
    total_urls: int = 0
    urls_processed: int = 0
    urls_failed: int = 0
    bytes_downloaded: int = 0
    start_time: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CrawlStatistics':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class CheckpointInfo:
    """Information about a checkpoint."""
    timestamp: str
    trigger: str  # manual, auto, signal, error
    stats_snapshot: Dict[str, Any]
    message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CheckpointInfo':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class CrawlState:
    """Persistent state for a crawl operation."""
    version: str = "1.0"
    crawl_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_checkpoint: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Configuration
    start_url: str = ""
    output_dir: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Progress tracking
    urls_queued: List[Tuple[str, int]] = field(default_factory=list)  # (url, depth)
    urls_visited: Dict[str, str] = field(default_factory=dict)  # url -> output_file
    urls_failed: Dict[str, str] = field(default_factory=dict)  # url -> error_message
    
    # Statistics
    statistics: CrawlStatistics = field(default_factory=CrawlStatistics)
    
    # Checkpoint history
    checkpoints: List[CheckpointInfo] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "crawl_id": self.crawl_id,
            "created_at": self.created_at,
            "last_checkpoint": self.last_checkpoint,
            "start_url": self.start_url,
            "output_dir": str(self.output_dir),
            "config": _json_safe(self.config),
            "progress": {
                "urls_queued": _json_safe(self.urls_queued),
                "urls_visited": _json_safe(self.urls_visited),
                "urls_failed": _json_safe(self.urls_failed),
                "statistics": self.statistics.to_dict()
            },
            "checkpoints": [cp.to_dict() for cp in self.checkpoints]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CrawlState':
        """Create CrawlState from dictionary."""
        state = cls(
            version=data.get("version", "1.0"),
            crawl_id=data.get("crawl_id", str(uuid.uuid4())),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_checkpoint=data.get("last_checkpoint", datetime.now().isoformat()),
            start_url=data.get("start_url", ""),
            output_dir=str(data.get("output_dir", "")),
            config=data.get("config", {})
        )
        
        # Load progress data
        progress = data.get("progress", {})
        state.urls_queued = progress.get("urls_queued", [])
        state.urls_visited = progress.get("urls_visited", {})
        state.urls_failed = progress.get("urls_failed", {})
        
        # Load statistics
        if "statistics" in progress:
            state.statistics = CrawlStatistics.from_dict(progress["statistics"])
        
        # Load checkpoints
        state.checkpoints = [
            CheckpointInfo.from_dict(cp) 
            for cp in data.get("checkpoints", [])
        ]
        
        return state


class StateManager:
    """Manages crawler state persistence and recovery."""
    
    def __init__(self, state_dir: Optional[Path] = None):
        """Initialize state manager.
        
        Args:
            state_dir: Directory to store state files. 
                      Defaults to ~/.html2md/states
        """
        if state_dir is None:
            self.state_dir = Path.home() / ".html2md" / "states"
        else:
            self.state_dir = Path(state_dir)
        
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._setup_signal_handlers()
        
        # Checkpoint configuration
        self.checkpoint_interval = 300  # 5 minutes
        self.checkpoint_page_count = 100  # Every 100 pages
        self.last_checkpoint_time = time.time()
        self.pages_since_checkpoint = 0
        
        # Current state
        self.current_state: Optional[CrawlState] = None
        self._checkpoint_callback: Optional[Callable] = None
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, creating checkpoint...")
            if self.current_state:
                self.save_checkpoint("signal", f"Interrupted by signal {signum}")
        
        # Handle common interruption signals
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def create_new_state(self, start_url: str, output_dir: str, 
                        config: Dict[str, Any]) -> CrawlState:
        """Create a new crawl state.
        
        Args:
            start_url: Starting URL for the crawl
            output_dir: Output directory for results
            config: Crawl configuration
            
        Returns:
            New CrawlState instance
        """
        self.current_state = CrawlState(
            start_url=start_url,
            output_dir=str(output_dir),
            config=_json_safe(config)
        )
        
        # Save initial state
        self.save_checkpoint("manual", "Initial state")
        
        return self.current_state
    
    def load_state(self, crawl_id: str) -> Optional[CrawlState]:
        """Load existing crawl state.
        
        Args:
            crawl_id: ID of the crawl to load
            
        Returns:
            Loaded CrawlState or None if not found
        """
        state_file = self.state_dir / f"{crawl_id}.json"
        
        if not state_file.exists():
            logger.error(f"State file not found: {state_file}")
            return None
        
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
            
            self.current_state = CrawlState.from_dict(data)
            logger.info(f"Loaded state for crawl {crawl_id}")
            return self.current_state
            
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            
            # Try backup file
            backup_file = state_file.with_suffix('.bak')
            if backup_file.exists():
                logger.info("Attempting to load from backup...")
                try:
                    with open(backup_file, 'r') as f:
                        data = json.load(f)
                    self.current_state = CrawlState.from_dict(data)
                    return self.current_state
                except Exception as e2:
                    logger.error(f"Backup load also failed: {e2}")
            
            return None
    
    def save_state(self, state: Optional[CrawlState] = None):
        """Save current state to disk atomically.
        
        Args:
            state: State to save (uses current_state if None)
        """
        if state is None:
            state = self.current_state
        
        if state is None:
            logger.warning("No state to save")
            return
        
        state_file = self.state_dir / f"{state.crawl_id}.json"
        
        # Update last checkpoint time
        state.last_checkpoint = datetime.now().isoformat()
        
        # Atomic write: write to temp file then rename
        temp_file = state_file.with_suffix('.tmp')
        
        try:
            # Write to temporary file
            with open(temp_file, 'w') as f:
                json.dump(state.to_dict(), f, indent=2)
            
            # Create backup of existing file
            if state_file.exists():
                backup_file = state_file.with_suffix('.bak')
                shutil.copy2(state_file, backup_file)
            
            # Atomic rename
            temp_file.rename(state_file)
            
            logger.debug(f"Saved state to {state_file}")
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            # Clean up temp file if it exists
            if temp_file.exists():
                temp_file.unlink()
            raise
    
    def save_checkpoint(self, trigger: str = "auto", message: Optional[str] = None):
        """Save a checkpoint of current state.
        
        Args:
            trigger: What triggered the checkpoint
            message: Optional message about the checkpoint
        """
        if not self.current_state:
            return
        
        # Create checkpoint info
        checkpoint = CheckpointInfo(
            timestamp=datetime.now().isoformat(),
            trigger=trigger,
            stats_snapshot=self.current_state.statistics.to_dict(),
            message=message
        )
        
        # Add to checkpoint history
        self.current_state.checkpoints.append(checkpoint)
        
        # Keep only last 10 checkpoints
        if len(self.current_state.checkpoints) > 10:
            self.current_state.checkpoints = self.current_state.checkpoints[-10:]
        
        # Save state
        self.save_state()
        
        # Reset counters
        self.last_checkpoint_time = time.time()
        self.pages_since_checkpoint = 0
        
        # Call callback if registered
        if self._checkpoint_callback:
            self._checkpoint_callback(checkpoint)
        
        logger.info(f"Checkpoint saved: {trigger} - {message or 'No message'}")
    
    def should_checkpoint(self) -> bool:
        """Check if a checkpoint should be created."""
        if not self.current_state:
            return False
        
        # Time-based checkpoint
        if time.time() - self.last_checkpoint_time > self.checkpoint_interval:
            return True
        
        # Page count based checkpoint
        if self.pages_since_checkpoint >= self.checkpoint_page_count:
            return True
        
        return False
    
    def update_progress(self, url: str, success: bool, 
                       output_file: Optional[str] = None,
                       error_message: Optional[str] = None):
        """Update crawl progress.
        
        Args:
            url: URL that was processed
            success: Whether processing was successful
            output_file: Output file path if successful
            error_message: Error message if failed
        """
        if not self.current_state:
            return
        
        # Update statistics
        self.current_state.statistics.urls_processed += 1
        self.current_state.statistics.last_update = time.time()
        
        # Update URL tracking
        if success and output_file:
            self.current_state.urls_visited[url] = output_file
        elif not success and error_message:
            self.current_state.urls_failed[url] = error_message
            self.current_state.statistics.urls_failed += 1
        
        # Increment page counter
        self.pages_since_checkpoint += 1
        
        # Check if we should checkpoint
        if self.should_checkpoint():
            self.save_checkpoint("auto", f"After processing {url}")
    
    def add_urls_to_queue(self, urls: List[Tuple[str, int]]):
        """Add URLs to the queue.
        
        Args:
            urls: List of (url, depth) tuples
        """
        if not self.current_state:
            return
        
        self.current_state.urls_queued.extend(urls)
        self.current_state.statistics.total_urls = len(self.current_state.urls_queued)
    
    def get_next_url(self) -> Optional[Tuple[str, int]]:
        """Get next URL from queue.
        
        Returns:
            (url, depth) tuple or None if queue is empty
        """
        if not self.current_state or not self.current_state.urls_queued:
            return None
        
        return self.current_state.urls_queued.pop(0)
    
    def list_resumable_crawls(self) -> List[Dict[str, Any]]:
        """List all resumable crawls.
        
        Returns:
            List of crawl summaries
        """
        crawls = []
        
        for state_file in self.state_dir.glob("*.json"):
            if state_file.suffix == '.json' and not state_file.stem.endswith('.bak'):
                try:
                    with open(state_file, 'r') as f:
                        data = json.load(f)
                    
                    crawls.append({
                        "crawl_id": data.get("crawl_id"),
                        "start_url": data.get("start_url"),
                        "created_at": data.get("created_at"),
                        "last_checkpoint": data.get("last_checkpoint"),
                        "urls_processed": len(data.get("progress", {}).get("urls_visited", {})),
                        "urls_queued": len(data.get("progress", {}).get("urls_queued", [])),
                        "state_file": str(state_file)
                    })
                except Exception as e:
                    logger.error(f"Failed to read state file {state_file}: {e}")
        
        # Sort by last checkpoint time
        crawls.sort(key=lambda x: x["last_checkpoint"], reverse=True)
        
        return crawls
    
    def clean_old_states(self, days: int = 30):
        """Clean up old state files.
        
        Args:
            days: Remove states older than this many days
        """
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        cleaned = 0
        
        for state_file in self.state_dir.glob("*.json"):
            if state_file.stat().st_mtime < cutoff_time:
                try:
                    state_file.unlink()
                    # Also remove backup
                    backup_file = state_file.with_suffix('.bak')
                    if backup_file.exists():
                        backup_file.unlink()
                    cleaned += 1
                except Exception as e:
                    logger.error(f"Failed to remove {state_file}: {e}")
        
        logger.info(f"Cleaned {cleaned} old state files")
        return cleaned
    
    def export_state(self, crawl_id: str, output_file: Path):
        """Export a crawl state to a file.
        
        Args:
            crawl_id: ID of crawl to export
            output_file: Where to save the export
        """
        state = self.load_state(crawl_id)
        if not state:
            raise ValueError(f"Crawl {crawl_id} not found")
        
        with open(output_file, 'w') as f:
            json.dump(state.to_dict(), f, indent=2)
        
        logger.info(f"Exported state to {output_file}")
    
    def import_state(self, input_file: Path) -> str:
        """Import a crawl state from a file.
        
        Args:
            input_file: File to import from
            
        Returns:
            Crawl ID of imported state
        """
        with open(input_file, 'r') as f:
            data = json.load(f)
        
        state = CrawlState.from_dict(data)
        
        # Generate new ID to avoid conflicts
        state.crawl_id = str(uuid.uuid4())
        
        # Save to state directory
        self.current_state = state
        self.save_state()
        
        logger.info(f"Imported state with new ID: {state.crawl_id}")
        return state.crawl_id
    
    def register_checkpoint_callback(self, callback: Callable[[CheckpointInfo], None]):
        """Register a callback to be called on checkpoint.
        
        Args:
            callback: Function to call with checkpoint info
        """
        self._checkpoint_callback = callback
