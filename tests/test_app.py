import unittest
from unittest.mock import patch

import app


class AppTests(unittest.TestCase):
    def test_extract_page_removes_non_content_and_resolves_links(self):
        text, links = app.extract_page(
            '<script>alert(1)</script><h1>Title</h1><a href="/next#part">Next</a>',
            "https://example.com/start",
        )
        self.assertEqual(text, "Title Next")
        self.assertEqual(links, ["https://example.com/next"])

    def test_public_url_rejects_private_addresses(self):
        with patch("app.socket.getaddrinfo", return_value=[(0, 0, 0, "", ("127.0.0.1", 0))]):
            with self.assertRaises(ValueError):
                app._public_url("http://localhost")

    def test_build_prompt_contains_urls_and_requirements(self):
        prompt = app.build_prompt(
            [("https://example.com", "Example content")], "find prices", "lowest price"
        )
        self.assertIn("https://example.com", prompt)
        self.assertIn("find prices", prompt)
        self.assertIn("Do not invent facts", prompt)

    @patch("app._fetch_document")
    @patch("app.socket.getaddrinfo")
    def test_crawl_is_bounded_to_same_domain(self, getaddrinfo, fetch_document):
        getaddrinfo.return_value = [(0, 0, 0, "", ("93.184.216.34", 0))]
        fetch_document.side_effect = [
            ("Home", ["https://example.com/about", "https://other.example/about"]),
            ("About", ["https://example.com"]),
        ]
        pages = app.crawl_site("https://example.com", max_pages=2)
        self.assertEqual([url for url, _ in pages], ["https://example.com", "https://example.com/about"])
        self.assertEqual(fetch_document.call_count, 2)


if __name__ == "__main__":
    unittest.main()
