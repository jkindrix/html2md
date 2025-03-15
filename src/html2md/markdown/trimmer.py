import logging
from urllib.parse import urlparse
from html2md.utils.parser import find_nth_occurrence
from html2md.config.loader import load_config


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
    if "path_rules" in domain_rules:
        for rule_path, rule in domain_rules["path_rules"].items():
            if path.startswith(rule_path):
                logging.info(
                    f"Applying path-based trimming rule for {domain}{rule_path}: {rule}"
                )
                if "h1_occurrence" in rule:
                    h1_index = find_nth_occurrence(
                        markdown_content, "# ", rule["h1_occurrence"]
                    )
                if "footer_marker" in rule:
                    footer_index = markdown_content.find(rule["footer_marker"])
                break  # Stop checking after the first matching rule

    # Handle domain-wide footer markers if no path-specific rule matched
    elif "footer_marker" in domain_rules:
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

    logging.info("Trimming markdown content based on detected indices.")
    return markdown_content[h1_index:footer_index].strip()
