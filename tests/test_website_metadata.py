"""Validate website head metadata and analytics without browser dependencies."""
from html.parser import HTMLParser
from pathlib import Path
import struct
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "website" / "dist"


class Head(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.meta = {}
        self.canonical = []
        self.scripts = []
        self.in_head = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "head":
            self.in_head = True
        if not self.in_head:
            return
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            self.meta.setdefault(key, []).append(attrs.get("content"))
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical.append(attrs.get("href"))
        if tag == "script":
            self.scripts.append(attrs)

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False


class WebsiteMetadataTest(unittest.TestCase):
    def setUp(self):
        self.head = Head((DIST / "index.html").read_text())

    def value(self, key):
        values = self.head.meta.get(key, [])
        self.assertEqual(len(values), 1, f"Expected one {key} tag in the head")
        self.assertTrue(values[0], f"Empty {key} tag")
        return values[0]

    def test_canonical_and_open_graph(self):
        self.assertEqual(self.head.canonical, ["https://aisocialcreditscore.com/"])
        self.assertEqual(self.value("og:url"), self.head.canonical[0])
        self.assertEqual(self.value("og:type"), "website")
        self.assertEqual(self.value("og:site_name"), "AI Social Credit Score")
        for key in ("og:title", "og:description", "og:image:alt"):
            self.value(key)

    def test_fathom_embed_is_deferred_and_uses_correct_site(self):
        fathom = [script for script in self.head.scripts
                  if script.get("src") == "https://cdn.usefathom.com/script.js"]
        self.assertEqual(len(fathom), 1)
        self.assertEqual(fathom[0].get("data-site"), "MLTKIADE")
        self.assertIn("defer", fathom[0])

    def test_x_card_matches_open_graph(self):
        self.assertEqual(self.value("twitter:card"), "summary_large_image")
        for field in ("title", "description", "image", "image:alt"):
            self.assertEqual(self.value(f"twitter:{field}"), self.value(f"og:{field}"))

    def test_social_preview_uses_current_headline(self):
        headline = "Track how nice you are to AI"
        self.assertEqual(self.value("og:title"), headline)
        self.assertIn(headline, self.value("og:image:alt"))

    def test_image_is_real_png_with_declared_dimensions(self):
        image_url = urlparse(self.value("og:image"))
        self.assertEqual(image_url.scheme, "https")
        self.assertEqual(image_url.netloc, "aisocialcreditscore.com")
        image = (DIST / image_url.path.lstrip("/")).read_bytes()
        self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(image[12:16], b"IHDR")
        dimensions = struct.unpack(">II", image[16:24])
        self.assertEqual(dimensions, (1200, 630))
        self.assertEqual(dimensions, tuple(int(self.value(f"og:image:{axis}"))
                                          for axis in ("width", "height")))
        self.assertEqual(self.value("og:image:type"), "image/png")
        self.assertLess(len(image), 5_000_000)


if __name__ == "__main__":
    unittest.main()
