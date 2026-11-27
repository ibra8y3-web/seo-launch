import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import seo_launch as sl

BASE = "https://example.github.io/site/"

FULL = """<!DOCTYPE html><html><head>
<title>Full page</title>
<meta name="description" content="A complete page.">
<link rel="canonical" href="https://example.github.io/site/">
<meta property="og:title" content="Full page">
<meta property="og:description" content="A complete page.">
<meta property="og:url" content="https://example.github.io/site/">
<meta property="og:type" content="website">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage","url":"https://example.github.io/site/"}</script>
</head><body><h1>Full</h1><p>text</p></body></html>"""

TITLE_ONLY = "<html><head><title>About us</title></head><body><p>We build things for everyone everywhere.</p></body></html>"
BARE = "<html><body><h1>Contact</h1><p>Reach us anytime.</p></body></html>"


def make_site(root):
    (Path(root) / "index.html").write_text(FULL, encoding="utf-8")
    (Path(root) / "about.html").write_text(TITLE_ONLY, encoding="utf-8")
    sub = Path(root) / "blog"
    sub.mkdir()
    (sub / "index.html").write_text(BARE, encoding="utf-8")
    (Path(root) / "404.html").write_text("<html><body>not found</body></html>", encoding="utf-8")


class Args:
    def __init__(self, site_dir, base_url=None, **kw):
        self.site_dir = site_dir
        self.base_url = base_url
        self.dry_run = kw.get("dry_run", False)
        self.google = kw.get("google")
        self.key = kw.get("key")
        self.urls = kw.get("urls")
        self.all_engines = kw.get("all_engines", False)


class ScanTest(unittest.TestCase):
    def test_scan_reports_issues(self):
        with tempfile.TemporaryDirectory() as d:
            make_site(d)
            self.assertEqual(sl.cmd_scan(Args(d)), 2)  # 2 of 3 pages need fixes
            info, issues = sl.scan_page(Path(d) / "index.html")
            self.assertEqual(issues, [])
            info, issues = sl.scan_page(Path(d) / "about.html")
            self.assertIn("missing meta description", issues)
            self.assertIn("no JSON-LD structured data", issues)


class FixTest(unittest.TestCase):
    def test_fix_injects_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            make_site(d)
            self.assertEqual(sl.cmd_fix(Args(d, BASE)), 0)
            html = (Path(d) / "about.html").read_text(encoding="utf-8")
            self.assertIn('name="description"', html)
            self.assertIn('rel="canonical" href="https://example.github.io/site/about.html"', html)
            self.assertIn('property="og:url"', html)
            self.assertIn("application/ld+json", html)
            # idempotent: second run changes nothing
            self.assertEqual(sl.cmd_fix(Args(d, BASE)), 0)
            # existing content preserved
            self.assertIn("<title>About us</title>", html)

    def test_page_url_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            make_site(d)
            self.assertEqual(sl.page_url(BASE, d, Path(d) / "index.html"), BASE)
            self.assertEqual(sl.page_url(BASE, d, Path(d) / "about.html"), BASE + "about.html")
            self.assertEqual(sl.page_url(BASE, d, Path(d) / "blog" / "index.html"), BASE + "blog/")


class SitemapRobotsTest(unittest.TestCase):
    def test_sitemap_and_robots(self):
        with tempfile.TemporaryDirectory() as d:
            make_site(d)
            self.assertEqual(sl.cmd_sitemap(Args(d, BASE)), 0)
            xml = (Path(d) / "sitemap.xml").read_text(encoding="utf-8")
            self.assertEqual(xml.count("<url>"), 3)
            self.assertIn("<loc>%s</loc>" % BASE, xml)
            self.assertIn("<loc>%sblog/</loc>" % BASE, xml)
            self.assertNotIn("404", xml)
            urls = sl.sitemap_urls(d)
            self.assertEqual(len(urls), 3)
            self.assertEqual(sl.cmd_robots(Args(d, BASE)), 0)
            robots = (Path(d) / "robots.txt").read_text(encoding="utf-8")
            self.assertIn("Sitemap: %ssitemap.xml" % BASE, robots)


class VerifyKeySubmitTest(unittest.TestCase):
    def test_verify_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sl.cmd_verify(Args(d, google="abc123")), 0)
            f = Path(d) / "googleabc123.html"
            self.assertEqual(f.read_text(encoding="utf-8").strip(),
                             "google-site-verification: googleabc123.html")

    def test_key_creation_and_payload(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sl.cmd_key(Args(d, BASE)), 0)
            cfg = json.loads((Path(d) / "seo-launch.json").read_text(encoding="utf-8"))
            key = cfg["indexnow_key"]
            self.assertEqual(len(key), 32)
            self.assertEqual((Path(d) / (key + ".txt")).read_text(encoding="utf-8").strip(), key)
            payload = sl.build_payload(BASE, key, [BASE])
            self.assertEqual(payload["host"], "example.github.io")
            self.assertEqual(payload["keyLocation"], BASE + key + ".txt")
            self.assertEqual(payload["urlList"], [BASE])

    def test_submit_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            make_site(d)
            sl.cmd_sitemap(Args(d, BASE))
            sl.cmd_key(Args(d, BASE))
            code = sl.cmd_submit(Args(d, BASE, dry_run=True))
            self.assertEqual(code, 0)

    def test_action_written(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sl.cmd_action(Args(d)), 0)
            wf = Path(d) / ".github" / "workflows" / "seo-launch.yml"
            text = wf.read_text(encoding="utf-8")
            self.assertIn("seo_launch.py", text)
            self.assertIn("SEO_BASE_URL", text)


if __name__ == "__main__":
    unittest.main()
