import logging
import re


def format_markdown(markdown_content):
    """
    Format Markdown for improved readability.

    Args:
        markdown_content (str): Raw markdown content.

    Returns:
        str: Formatted markdown content.
    """
    if not isinstance(markdown_content, str):
        raise ValueError("Expected markdown_content to be a string")

    logging.info("Applying markdown formatting...")

    # Fix improperly formatted headers with links
    markdown_content = re.sub(
        r"(#{1,6} )([^\[]+)\[\]\((#[^\)]+)\)", r"\1[\2](\3)", markdown_content
    )
    logging.info("Fixed markdown headers with links")

    # Convert <pre><code> blocks to Markdown-style code blocks
    markdown_content = markdown_content.replace("<pre><code>", "```\n").replace(
        "</code></pre>", "\n```"
    )
    logging.info("Converted HTML <pre><code> to markdown code blocks")

    # Collapse excessive newlines
    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content)
    logging.info("Collapsed excessive newlines")

    return markdown_content
