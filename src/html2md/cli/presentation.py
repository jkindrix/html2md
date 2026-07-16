"""Reusable Rich presentation components for CLI commands."""

import os
import platform

from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

from html2md import __version__

HTML2MD_THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "command": "bold magenta",
        "url": "underline blue",
        "filename": "bold cyan",
        "directory": "bold blue",
        "count": "bold yellow",
        "header": "bold white on blue",
        "subheader": "bold cyan",
    }
)

STATUS_EMOJI = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "processing": "🔄",
    "download": "📥",
    "upload": "📤",
    "config": "⚙️",
    "markdown": "📝",
    "html": "🌐",
    "batch": "📚",
    "convert": "🔄",
    "crawl": "🕸️",
    "file": "📄",
    "directory": "📁",
    "link": "🔗",
    "queued": "⏳",
    "visited": "👁️",
}


class EnhancedProgress(Progress):
    """Progress display with consistent CLI styling."""

    def __init__(self):
        super().__init__(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(bar_width=40, style="cyan", complete_style="green"),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
        )


def show_welcome_banner(console: Console) -> None:
    """Display the welcome banner with runtime information."""
    system = platform.system()
    release = platform.release()
    version_info = Table.grid(padding=(0, 1))
    version_info.add_row("Version:", __version__)
    version_info.add_row("Python:", platform.python_version())
    version_info.add_row("System:", f"{system} {release}")
    content = Group(
        Text("HTML2MD", style="bold white on blue"),
        Text("Convert HTML to Markdown with Style", style="italic cyan"),
        Text(),
        version_info,
        Text("\nUse --help with any command for more information", style="dim"),
    )
    console.print(
        Panel(
            content,
            border_style="blue",
            padding=(1, 2),
            title="Welcome to HTML2MD",
            subtitle="https://github.com/jkindrix/html2md",
        )
    )


def display_directory_tree(path, max_depth=3):
    """Build a Rich tree for an output directory."""
    root = Tree(f"📁 {path}", style="bold blue")

    def add_directory(tree, directory, depth=0):
        if depth >= max_depth:
            tree.add("...")
            return
        for item in sorted(os.listdir(directory)):
            item_path = os.path.join(directory, item)
            if os.path.isdir(item_path):
                branch = tree.add(f"📁 {item}", style="bold blue")
                if depth < max_depth - 1:
                    add_directory(branch, item_path, depth + 1)
            else:
                icon = (
                    "📝"
                    if item.endswith(".md")
                    else "🌐" if item.endswith(".html") else "📄"
                )
                tree.add(f"{icon} {item}", style="green")

    try:
        add_directory(root, path)
        return root
    except OSError as error:
        return Text(f"Error displaying directory tree: {error}", style="bold red")
