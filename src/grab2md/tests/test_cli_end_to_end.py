"""Black-box CLI tests across process, HTTP, filesystem, and state boundaries."""

import gzip
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest


class CliContractHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/robots.txt":
            self._send(200, b"User-agent: *\nDisallow: /blocked\n", "text/plain")
        elif path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
        elif path == "/gzip":
            body = gzip.compress(b"<html><h1>Compressed</h1><p>decoded body</p></html>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/not-found":
            self._send(404, b"missing")
        elif path == "/limited":
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()
        elif path == "/server-error":
            self._send(500, b"server error")
        elif path == "/authenticated-article":
            authenticated = (
                self.headers.get("Authorization") == "Bearer integration-secret"
                and self.headers.get("X-Tenant") == "docs"
            )
            if not authenticated:
                self._send(401, b"authentication required", "text/plain")
                return
            body = (
                "<html><body><nav>PRIVATE NAVIGATION</nav>"
                "<article><h1>Authenticated article</h1>"
                f"<p>{'Evidence-backed authenticated content. ' * 10}</p>"
                "</article><footer>PRIVATE FOOTER</footer></body></html>"
            ).encode()
            self._send(200, body)
        elif path in {"/ok", "/blocked"} or path.endswith("/escape"):
            body = (
                f"<html><h1>Page {path}</h1><p>body</p>"
                '<a href="/second">second</a></html>'
            ).encode()
            self._send(200, body)
        elif path == "/second":
            self._send(200, b"<html><h1>Second</h1><p>body</p></html>")
        else:
            self._send(404, b"missing")

    def _send(self, status, body, content_type="text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


@pytest.fixture(scope="module")
def cli_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), CliContractHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run_cli(
    tmp_path: Path,
    *arguments: str,
    timeout: int = 30,
    output_encoding: str | None = None,
):
    home = tmp_path / "home"
    config = home / ".config" / "grab2md" / "config.json"
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "GRAB2MD_CONFIG_PATH": str(config),
            "PYTHONPATH": str(Path(__file__).parents[3] / "src"),
            "NO_COLOR": "1",
        }
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from grab2md.cli.cli import entry_point; entry_point()",
            *map(str, arguments),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        encoding=output_encoding,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def test_local_conversion_subprocess_writes_markdown(tmp_path):
    source = tmp_path / "source.html"
    output = tmp_path / "result.md"
    source.write_text("<h1>Local page</h1><p>converted body</p>", encoding="utf-8")

    result = run_cli(tmp_path, "convert", source, "--local", "--output", output)

    assert result.returncode == 0, result.stderr
    assert "# Local page" in output.read_text(encoding="utf-8")


def test_multiple_sources_cannot_share_one_output_file(tmp_path):
    first = tmp_path / "first.html"
    second = tmp_path / "second.html"
    output = tmp_path / "result.md"
    first.write_text("<h1>First marker</h1>", encoding="utf-8")
    second.write_text("<h1>Second marker</h1>", encoding="utf-8")

    result = run_cli(
        tmp_path,
        "convert",
        first,
        second,
        "--local",
        "--output",
        output,
    )

    assert result.returncode == 2
    assert "--output accepts exactly one source" in result.stdout
    assert not output.exists()


def test_direct_source_is_primary_and_accepts_root_options(tmp_path):
    source = tmp_path / "direct.html"
    output = tmp_path / "direct.md"
    source.write_text("<h1>Direct source</h1><p>converted body</p>", encoding="utf-8")

    result = run_cli(
        tmp_path,
        "--log-level",
        "INFO",
        source,
        "--local",
        "--output",
        output,
    )

    assert result.returncode == 0, result.stderr
    assert "# Direct source" in output.read_text(encoding="utf-8")


def test_local_content_modes_are_explicit_lossless_and_fail_honestly(tmp_path):
    fixtures = Path(__file__).parents[3] / "tests" / "fixtures" / "extraction"
    article = tmp_path / "article.html"
    article.write_text(
        (fixtures / "article.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    full_output = tmp_path / "full.md"
    main_output = tmp_path / "main.md"
    selector_output = tmp_path / "selector.md"

    full = run_cli(tmp_path, "convert", article, "--local", "--output", full_output)
    main = run_cli(
        tmp_path,
        "convert",
        article,
        "--local",
        "--content",
        "main",
        "--output",
        main_output,
    )
    selected = run_cli(
        tmp_path,
        "convert",
        article,
        "--local",
        "--content",
        "selector",
        "--selector",
        ".byline",
        "--output",
        selector_output,
    )

    assert full.returncode == main.returncode == selected.returncode == 0
    assert "GLOBAL NAVIGATION" in full_output.read_text(encoding="utf-8")
    assert "GLOBAL NAVIGATION" not in main_output.read_text(encoding="utf-8")
    assert selector_output.read_text(encoding="utf-8").strip() == "By A. Writer"

    ambiguous = tmp_path / "ambiguous.html"
    ambiguous.write_text(
        (fixtures / "ambiguous.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    failed = run_cli(
        tmp_path,
        "convert",
        ambiguous,
        "--local",
        "--content",
        "main",
        "--output",
        tmp_path / "ambiguous.md",
    )
    assert failed.returncode == 1
    assert "No confident main-content region" in failed.stderr

    invalid = run_cli(
        tmp_path,
        "convert",
        article,
        "--local",
        "--content",
        "selector",
    )
    assert invalid.returncode == 1
    assert "Selector mode requires --selector" in invalid.stderr


@pytest.mark.parametrize(
    ("path", "heading"),
    [("/ok", "Page /ok"), ("/redirect", "Page /ok"), ("/gzip", "Compressed")],
)
def test_url_conversion_handles_plain_redirected_and_compressed_responses(
    tmp_path, cli_server, path, heading
):
    output = tmp_path / f"{path.strip('/')}.md"

    result = run_cli(
        tmp_path,
        "convert",
        f"{cli_server}{path}",
        "--allow-private-network",
        "--output",
        output,
    )

    assert result.returncode == 0, result.stderr
    assert f"# {heading}" in output.read_text(encoding="utf-8")


def test_url_metadata_uses_final_redirect_url(tmp_path, cli_server):
    output = tmp_path / "metadata.md"

    result = run_cli(
        tmp_path,
        "convert",
        f"{cli_server}/redirect",
        "--allow-private-network",
        "--metadata",
        "--output",
        output,
    )

    assert result.returncode == 0, result.stderr
    content = output.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert f'canonical_url: "{cli_server}/ok"' in content
    assert "# Page /ok" in content


def test_authenticated_url_applies_explicit_content_selection(tmp_path, cli_server):
    headers = tmp_path / "headers.json"
    headers.write_text(
        json.dumps(
            {
                "Authorization": "Bearer integration-secret",
                "X-Tenant": "docs",
            }
        ),
        encoding="utf-8",
    )
    if os.name == "posix":
        headers.chmod(0o600)
    output = tmp_path / "authenticated.md"

    result = run_cli(
        tmp_path,
        "convert",
        f"{cli_server}/authenticated-article",
        "--headers-file",
        headers,
        "--content",
        "selector",
        "--selector",
        "article",
        "--allow-private-network",
        "--output",
        output,
    )

    assert result.returncode == 0, result.stderr
    markdown = output.read_text(encoding="utf-8")
    assert "# Authenticated article" in markdown
    assert "Evidence-backed authenticated content" in markdown
    assert "PRIVATE NAVIGATION" not in markdown
    assert "PRIVATE FOOTER" not in markdown


def test_private_network_is_rejected_without_explicit_opt_in(tmp_path, cli_server):
    output = tmp_path / "blocked.md"
    result = run_cli(
        tmp_path,
        "convert",
        f"{cli_server}/ok",
        "--output",
        output,
    )

    assert result.returncode == 1
    assert "--allow-private-network" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("path", ["/not-found", "/limited", "/server-error"])
def test_url_http_failures_exit_nonzero_without_output(tmp_path, cli_server, path):
    output = tmp_path / "failure.md"

    result = run_cli(
        tmp_path,
        "convert",
        f"{cli_server}{path}",
        "--allow-private-network",
        "--output",
        output,
    )

    assert result.returncode == 1
    assert not output.exists()
    assert "Unable to retrieve content" in result.stderr


def test_batch_subprocess_fetches_and_writes_url(tmp_path, cli_server, monkeypatch):
    source = tmp_path / "links.md"
    output_dir = tmp_path / "batch-output"
    source.write_text(f"- [fixture]({cli_server}/ok)\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252")

    result = run_cli(
        tmp_path,
        "batch",
        source,
        "--output-dir",
        output_dir,
        "--content",
        "selector",
        "--selector",
        "html",
        "--quiet",
        "--allow-private-network",
        output_encoding="cp1252",
    )

    assert result.returncode == 0, result.stderr
    markdown_files = list(output_dir.rglob("*.md"))
    assert markdown_files
    assert any(
        "# Page /ok" in path.read_text(encoding="utf-8") for path in markdown_files
    )


def test_invalid_crawl_policy_is_a_usage_error_without_side_effects(tmp_path):
    output_dir = tmp_path / "crawl-output"

    result = run_cli(
        tmp_path,
        "crawl",
        "https://example.com",
        "--output-dir",
        output_dir,
        "--follow",
        "[",
    )

    assert result.returncode == 2
    assert "Invalid --follow regex pattern" in result.stdout
    assert not output_dir.exists()


def test_crawl_state_resume_and_traversal_containment_in_subprocess(
    tmp_path, cli_server
):
    output_dir = tmp_path / "crawl-output"
    url = f"{cli_server}/docs/%2e%2e/escape"

    crawl = run_cli(
        tmp_path,
        "crawl",
        url,
        "--output-dir",
        output_dir,
        "--max-depth",
        "0",
        "--max-pages",
        "1",
        "--ignore-robots",
        "--content",
        "selector",
        "--selector",
        "html",
        "--quiet",
        "--no-progress",
        "--allow-private-network",
    )

    assert crawl.returncode == 0, f"stdout:\n{crawl.stdout}\nstderr:\n{crawl.stderr}"
    assert "Website crawling complete" in crawl.stdout
    outputs = list(output_dir.rglob("*.md"))
    assert outputs
    assert all(path.resolve().is_relative_to(output_dir.resolve()) for path in outputs)
    assert not (tmp_path / "escape.md").exists()

    state_files = list((tmp_path / "home" / ".grab2md" / "states").glob("*.json"))
    assert len(state_files) == 1
    crawl_id = state_files[0].stem

    listed = run_cli(tmp_path, "state", "list")
    assert listed.returncode == 0
    assert crawl_id in listed.stdout

    resumed = run_cli(tmp_path, "state", "resume", crawl_id[:8])
    assert resumed.returncode == 0, resumed.stderr
    assert "resumed successfully" in resumed.stdout


def test_robots_denial_is_a_nonzero_crawl_failure(tmp_path, cli_server):
    output_dir = tmp_path / "blocked-output"

    result = run_cli(
        tmp_path,
        "crawl",
        f"{cli_server}/blocked",
        "--output-dir",
        output_dir,
        "--max-pages",
        "1",
        "--quiet",
        "--no-progress",
    )

    assert result.returncode == 1
    assert "robots.txt" in result.stdout
    assert "Website crawling complete" not in result.stdout
