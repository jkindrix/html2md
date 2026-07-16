"""
html2md - A Python package to convert HTML content to Markdown
with a beautiful UI using Typer and Rich.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("html2md")
except PackageNotFoundError:  # Source tree imported without installation metadata.
    __version__ = "0+unknown"
