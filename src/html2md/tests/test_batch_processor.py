import unittest
from unittest import mock

from html2md.markdown.batch_processor import create_directory_structure, rewrite_links
from html2md.utils.parser import extract_urls_from_markdown, generate_safe_filename


class TestBatchProcessor(unittest.TestCase):
    """Tests for the batch processor module."""

    def test_extract_urls_from_markdown(self):
        """Test extracting URLs from markdown."""
        markdown = """
        # Test Markdown

        [Link 1](https://example.com/page1)
        [Link 2](https://example.com/page2)
        [Link with query](https://example.com/page?query=value)

        Plain text without links.

        [Link with fragment](https://example.com/page#section)
        """

        expected_urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page?query=value",
            "https://example.com/page#section",
        ]

        urls = extract_urls_from_markdown(markdown)
        self.assertEqual(urls, expected_urls)

    def test_generate_safe_filename(self):
        """Test generating safe filenames from URLs."""
        test_cases = [
            ("https://example.com/page", "example.com_page.md"),
            ("https://example.com/path/to/page", "example.com_path_to_page.md"),
            ("https://example.com/page?query=value", "example.com_page_query_value.md"),
            ("https://example.com/page#section", "example.com_page_section.md"),
            ("https://example.com/page with spaces", "example.com_page_with_spaces.md"),
        ]

        for url, expected in test_cases:
            self.assertEqual(generate_safe_filename(url), expected)

    @mock.patch("os.makedirs")
    def test_create_directory_structure(self, mock_makedirs):
        """Test creating directory structure from URLs."""
        output_dir = "/output"
        test_cases = [
            ("https://example.com/page", "/output/example.com"),
            ("https://example.com/path/to/page", "/output/example.com/path/to"),
            ("https://subdomain.example.com/page", "/output/subdomain.example.com"),
        ]

        for url, expected in test_cases:
            result = create_directory_structure(output_dir, url)
            self.assertEqual(result, expected)
            mock_makedirs.assert_called_with(expected, exist_ok=True)

    def test_rewrite_links(self):
        """Test rewriting links in markdown content."""
        content = """
        # Test Content

        [Link 1](https://example.com/page1)
        [Link 2](https://example.org/page2)
        """

        url_mapping = {
            "https://example.com/page1": "/output/example.com/page1.md",
            "https://example.org/page2": "/output/example.org/page2.md",
        }

        base_output_dir = "/output"

        expected_content = """
        # Test Content

        [Link 1](example.com/page1.md)
        [Link 2](example.org/page2.md)
        """

        result = rewrite_links(content, url_mapping, base_output_dir)
        self.assertEqual(result, expected_content)


if __name__ == "__main__":
    unittest.main()
