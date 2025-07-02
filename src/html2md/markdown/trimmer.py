import logging
from urllib.parse import urlparse

from html2md.config.loader import load_config
from html2md.utils.parser import find_nth_occurrence


def trim_markdown(markdown_content, url):
    """Trim content dynamically based on domain-specific rules loaded from configuration."""
    # Load configuration dynamically
    config = load_config(force_reload=True)

    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    path = parsed_url.path

    if domain not in config["domains"]:
        logging.warning(
            f"No trimming rules found for {domain}. Returning unmodified content."
        )
        return markdown_content

    domain_rules = config["domains"][domain]

    h1_index = markdown_content.find("# ")
    footer_index = -1  # Default value

    # Handle path-specific rules if available
    path_matched = False
    if "path_rules" in domain_rules:
        for rule_path, rule in domain_rules["path_rules"].items():
            if path.startswith(rule_path):
                logging.info(
                    f"Applying path-based trimming rule for {domain}{rule_path}: {rule}"
                )
                path_matched = True
                if "h1_occurrence" in rule:
                    h1_index = find_nth_occurrence(
                        markdown_content, "# ", rule["h1_occurrence"]
                    )
                if "footer_marker" in rule:
                    footer_index = markdown_content.find(rule["footer_marker"])
                break  # Stop checking after the first matching rule

    # Handle domain-wide footer markers if no path-specific footer was found
    if "footer_marker" in domain_rules and footer_index == -1:
        logging.info(
            f"Applying domain-wide footer marker for {domain}: {domain_rules['footer_marker']}"
        )
        footer_index = markdown_content.find(domain_rules["footer_marker"])

    logging.info(f"URL: {url}, H1 index: {h1_index}, Footer index: {footer_index}")

    # Validate indices before slicing
    if h1_index == -1:
        logging.warning(
            f"No H1 header found in content for {domain}. Returning full content."
        )
        return markdown_content.strip()

    if footer_index == -1:
        logging.warning(
            f"No footer marker found for {domain}. Returning content from detected H1 onwards."
        )
        return markdown_content[h1_index:].strip()

    # If footer comes before H1, search for footer after H1
    if footer_index <= h1_index:
        logging.warning(
            f"Footer marker appears before H1 for {domain}. Searching for footer after H1."
        )
        # Search for footer marker after the H1
        footer_marker = None
        if "path_rules" in domain_rules:
            for rule_path, rule in domain_rules["path_rules"].items():
                if path.startswith(rule_path) and "footer_marker" in rule:
                    footer_marker = rule["footer_marker"]
                    break
        elif "footer_marker" in domain_rules:
            footer_marker = domain_rules["footer_marker"]
        
        if footer_marker:
            footer_index = markdown_content.find(footer_marker, h1_index)
        
        if footer_index == -1:
            logging.warning(
                f"No footer marker found after H1 for {domain}. Returning content from H1 onwards."
            )
            return markdown_content[h1_index:].strip()

    logging.info("Trimming markdown content based on detected indices.")
    return markdown_content[h1_index:footer_index].strip()


def trim_markdown_local(markdown_content, file_name):
    """
    Simplified trimmer for local files.
    Uses basic heuristics rather than domain-specific rules.

    Args:
        markdown_content (str): The markdown content to trim.
        file_name (str): The name of the source file.

    Returns:
        str: Trimmed markdown content.
    """
    # Basic approach: find the first heading and keep everything after it
    h1_index = markdown_content.find("# ")

    if h1_index == -1:
        logging.warning(f"No H1 header found in {file_name}. Returning full content.")
        return markdown_content.strip()

    # Look for common footer patterns that might indicate the end of main content
    footer_markers = [
        "## Further reading",
        "## See Also",
        "## References",
        "## Credits",
        "## Copyright",
        "## License",
    ]

    footer_index = -1
    for marker in footer_markers:
        index = markdown_content.find(marker)
        if index != -1:
            if footer_index == -1 or index < footer_index:
                footer_index = index

    if footer_index == -1:
        logging.info(
            f"No footer marker found in {file_name}. Returning content from detected H1 onwards."
        )
        return markdown_content[h1_index:].strip()

    logging.info(f"Trimming local file {file_name} content based on detected indices.")
    return markdown_content[h1_index:footer_index].strip()
