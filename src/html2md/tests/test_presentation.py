"""Behavior tests for reusable CLI presentation helpers."""

from io import StringIO
from pathlib import Path
from unittest.mock import patch

from rich.console import Console
from rich.text import Text
from rich.tree import Tree

from html2md.cli.presentation import (
    EnhancedProgress,
    display_directory_tree,
    show_welcome_banner,
)


def test_welcome_banner_reports_runtime_and_help():
    stream = StringIO()
    console = Console(file=stream, force_terminal=False, width=120)

    show_welcome_banner(console)

    rendered = stream.getvalue()
    assert "HTML2MD" in rendered
    assert "Version:" in rendered
    assert "Python:" in rendered
    assert "Use --help" in rendered


def test_enhanced_progress_has_standard_columns():
    progress = EnhancedProgress()

    assert len(progress.columns) == 6


def test_directory_tree_labels_files_and_limits_depth(tmp_path):
    (tmp_path / "page.md").write_text("# page", encoding="utf-8")
    (tmp_path / "source.html").write_text("<p>source</p>", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("notes", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "child.md").write_text("# child", encoding="utf-8")

    tree = display_directory_tree(tmp_path, max_depth=1)

    assert isinstance(tree, Tree)
    assert str(tmp_path) in str(tree.label)
    labels = [str(child.label) for child in tree.children]
    assert any("page.md" in label for label in labels)
    assert any("source.html" in label for label in labels)
    assert any("notes.txt" in label for label in labels)
    assert any("nested" in label for label in labels)


def test_directory_tree_returns_styled_error_for_unreadable_path(tmp_path):
    missing = Path(tmp_path / "missing")
    with patch("html2md.cli.presentation.os.listdir", side_effect=OSError("denied")):
        result = display_directory_tree(missing)

    assert isinstance(result, Text)
    assert "denied" in result.plain
