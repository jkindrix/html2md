"""Subprocess coverage for checkpointing and conventional signal exits."""

import json
import os
import signal
import subprocess
import sys
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

import pytest

from html2md.markdown.crawler import crawl_website
from html2md.network.request_handler import FetchResult
from html2md.utils.state_manager import StateManager


def test_signal_handler_restores_and_delegates_to_prior_handler(tmp_path):
    manager = StateManager(state_dir=tmp_path / "states")
    state = manager.create_new_state("https://example.com", tmp_path / "output", {})
    previous_int = Mock()
    previous_term = Mock()

    with (
        patch(
            "html2md.utils.state_manager.signal.getsignal",
            side_effect=[previous_int, previous_term],
        ),
        patch("html2md.utils.state_manager.signal.signal") as set_handler,
    ):
        assert manager.install_signal_handlers() is True
        manager._handle_signal(signal.SIGINT, None)

    previous_int.assert_called_once_with(signal.SIGINT, None)
    set_handler.assert_any_call(signal.SIGINT, previous_int)
    set_handler.assert_any_call(signal.SIGTERM, previous_term)
    assert manager._previous_signal_handlers == {}
    assert len([item for item in state.checkpoints if item.trigger == "signal"]) == 1


@pytest.mark.parametrize("signum", [signal.SIGINT, signal.SIGTERM])
def test_signal_saves_one_valid_resumable_checkpoint_and_terminates(tmp_path, signum):
    state_dir = tmp_path / "states"
    output_dir = tmp_path / "output"
    queued_url = "https://example.com/interrupted"
    script = textwrap.dedent(
        f"""
        import time
        from html2md.utils.state_manager import StateManager

        manager = StateManager(state_dir={str(state_dir)!r})
        state = manager.create_new_state(
            {queued_url!r}, {str(output_dir)!r}, {{"max_pages": 1}}
        )
        state.urls_queued = [({queued_url!r}, 0)]
        manager.save_state()
        with manager.signal_handling():
            print(state.crawl_id, flush=True)
            while True:
                time.sleep(1)
        """
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    crawl_id = process.stdout.readline().strip()
    assert crawl_id

    process.send_signal(signum)
    _, stderr = process.communicate(timeout=10)

    assert process.returncode in {-signum, 128 + signum}, stderr
    state_file = state_dir / f"{crawl_id}.json"
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    signal_checkpoints = [
        checkpoint
        for checkpoint in state_data["checkpoints"]
        if checkpoint["trigger"] == "signal"
    ]
    assert len(signal_checkpoints) == 1
    assert state_data["progress"]["urls_queued"] == [[queued_url, 0]]

    manager = StateManager(state_dir=state_dir)
    fetched = FetchResult(
        queued_url, queued_url, status_code=200, body="<h1>Resumed</h1>"
    )
    with (
        patch("html2md.markdown.crawler.fetch_html", return_value=fetched),
        patch(
            "html2md.markdown.crawler.html_content_to_markdown",
            return_value="# Resumed",
        ),
    ):
        result = crawl_website(
            queued_url,
            output_dir,
            max_pages=1,
            respect_robots=False,
            state_manager=manager,
            resume_crawl_id=crawl_id,
        )

    assert result.success is True
    assert result.processed_count == 1
    assert queued_url in result.url_mapping


class BlockingHandler(BaseHTTPRequestHandler):
    entered = threading.Event()
    release = threading.Event()

    def do_GET(self):
        self.entered.set()
        self.release.wait(timeout=10)
        self.send_response(200)
        self.end_headers()
        try:
            self.wfile.write(b"<html><body>late response</body></html>")
        except BrokenPipeError:
            pass

    def log_message(self, format, *args):
        pass


def test_cli_ctrl_c_checkpoints_in_flight_url(tmp_path):
    BlockingHandler.entered.clear()
    BlockingHandler.release.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), BlockingHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/page"
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    command = [
        sys.executable,
        "-c",
        "from html2md.cli.cli import entry_point; entry_point()",
        "crawl",
        url,
        "--output-dir",
        str(tmp_path / "output"),
        "--max-pages",
        "1",
        "--max-depth",
        "0",
        "--ignore-robots",
        "--quiet",
        "--allow-private-network",
    ]
    process = subprocess.Popen(
        command,
        cwd=tmp_path,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert BlockingHandler.entered.wait(timeout=10)
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
    finally:
        BlockingHandler.release.set()
        server.shutdown()
        server.server_close()

    assert process.returncode in {-signal.SIGINT, 128 + signal.SIGINT}, stdout + stderr
    state_files = list((home / ".html2md" / "states").glob("*.json"))
    assert len(state_files) == 1
    state_data = json.loads(state_files[0].read_text(encoding="utf-8"))
    assert state_data["progress"]["urls_queued"] == [[url, 0]]
    assert (
        len([item for item in state_data["checkpoints"] if item["trigger"] == "signal"])
        == 1
    )
