#!/usr/bin/env python3
"""seo-launch: push any static site to search engines, instantly.

One command prepares a static site for search engines and pushes every
change live instead of waiting for crawlers:

  - audit and fix titles, meta descriptions, canonical, Open Graph, JSON-LD
  - generate sitemap.xml and robots.txt
  - generate the Google Search Console verification file
  - create an IndexNow key and submit URLs the moment they change
    (Bing, Yandex, Naver, Seznam, Yep - they all share IndexNow)
  - install a GitHub Action that re-submits on every push

Honest note: no tool can force Google to index or rank a page. seo-launch
removes every technical blocker and notifies the engines that accept live
notification, so discovery takes minutes instead of weeks.

Requires Python 3.8+. Standard library only.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

VERSION = "0.1.0"
CONFIG_NAME = "seo-launch.json"
CHUNK = 10000  # IndexNow protocol maximum URLs per POST

INDEXNOW_ENDPOINTS = {
    "hub": "https://api.indexnow.org/indexnow",  # shares with every member engine
    "bing": "https://www.bing.com/indexnow",
    "yandex": "https://search.yandex.com/indexnow",
    "naver": "https://searchadvisor.naver.com/indexnow",
    "seznam": "https://search.seznam.cz/indexnow",
    "yep": "https://indexnow.yep.com",
}

# ---------------------------------------------------------------- config

def load_config(site_dir):
    cfg_path = Path(site_dir) / CONFIG_NAME
    if cfg_path.is_file():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print("warning: ignoring unreadable %s: %s" % (cfg_path, e), file=sys.stderr)
    return {}


def save_config(site_dir, cfg):
    cfg_path = Path(site_dir) / CONFIG_NAME
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return cfg_path


def get_base_url(args, cfg):
    base = args.base_url or cfg.get("base_url") or ""
    if not base:
        raise SystemExit("error: pass --base-url https://user.github.io/site/ (or set base_url in %s)" % CONFIG_NAME)
    if not base.startswith(("http://", "https://")):
        raise SystemExit("error: base URL must start with https://")
    return base if base.endswith("/") else base + "/"

# ------------------------------------------------------------ html scan

class PageInfo(HTMLParser):
    """Extract the metadata search engines care about from one HTML file."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self.description = None
        self.canonical = None
        self.h1 = None
        self.og = {}
        self.jsonld_types = []
        self.first_para = None
        self._capture = None  # "title" | "h1" | "p"
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title" and self.title is None:
            self._capture, self._buf = "title", []
        elif tag == "h1" and self.h1 is None:
            self._capture, self._buf = "h1", []
        elif tag == "p" and self.first_para is None:
            self._capture, self._buf = "p", []
        elif tag == "meta":
            name = (a.get("name") or "").lower()
            prop = (a.get("property") or "").lower()
            if name == "description" and self.description is None:
                self.description = (a.get("content") or "").strip() or None
            elif prop.startswith("og:"):
                self.og.setdefault(prop, (a.get("content") or "").strip())
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = (a.get("href") or "").strip() or None
        elif tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._capture, self._buf = "ld", []

    def handle_data(self, data):
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if not self._capture:
            return
        text = " ".join("".join(self._buf).split())
        if self._capture == "title" and tag == "title":
            self.title = text or None
            self._capture = None
        elif self._capture == "h1" and tag == "h1":
            self.h1 = text or None
            self._capture = None
        elif self._capture == "p" and tag == "p":
            self.first_para = text or None
            self._capture = None
        elif self._capture == "ld" and tag == "script":
            try:
                data = json.loads(text)
                items = data if isinstance(data, list) else [data]
                for it in items:
                    if isinstance(it, dict) and it.get("@type"):
                        self.jsonld_types.append(it["@type"])
            except json.JSONDecodeError:
                self.jsonld_types.append("(invalid JSON-LD)")
            self._capture = None


def html_files(site_dir, exclude):
    site = Path(site_dir)
    out = []
    for p in sorted(site.rglob("*.html")):
        rel = p.relative_to(site)
        parts = rel.parts
        if any(part.startswith((".", "_")) for part in parts):
            continue
        if rel.as_posix() in exclude or p.name in exclude:
            continue
        out.append(p)
    return out


def page_url(base, site_dir, path):
    rel = Path(path).relative_to(site_dir).as_posix()
    if rel == "index.html":
        return base
    if rel.endswith("/index.html"):
        return base + rel[: -len("index.html")]
    return base + rel


def scan_page(path):
    info = PageInfo()
    info.feed(Path(path).read_text(encoding="utf-8", errors="replace"))
    issues = []
    if not info.title:
        issues.append("missing <title>")
    if not info.description:
        issues.append("missing meta description")
    if not info.canonical:
        issues.append("missing canonical")
    for tag in ("og:title", "og:description", "og:url"):
        if not info.og.get(tag):
            issues.append("missing " + tag)
    if not info.jsonld_types:
        issues.append("no JSON-LD structured data")
    return info, issues


def cmd_scan(args):
    cfg = load_config(args.site_dir)
    exclude = set(cfg.get("exclude", [])) | {"404.html"}
    files = html_files(args.site_dir, exclude)
    if not files:
        print("no HTML pages found under %s" % args.site_dir)
        return 1
    bad = 0
    for p in files:
        info, issues = scan_page(p)
        rel = Path(p).relative_to(args.site_dir)
        if issues:
            bad += 1
            print("%s\n  %s" % (rel, "; ".join(issues)))
        else:
            print("%s  OK" % rel)
    print("\n%d page(s): %d OK, %d need fixes" % (len(files), len(files) - bad, bad))
    return 0 if bad == 0 else 2

# ------------------------------------------------------------ html fix

def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_injections(info, url):
    """Return the list of head tags this page is missing."""
    title = info.title or info.h1 or ""
    desc = info.description or (info.first_para or "")[:155]
    tags = []
    if not info.description and desc:
        tags.append('<meta name="description" content="%s">' % _esc(desc))
    if not info.canonical:
        tags.append('<link rel="canonical" href="%s">' % _esc(url))
    if not info.og.get("og:title") and title:
        tags.append('<meta property="og:title" content="%s">' % _esc(title))
    if not info.og.get("og:description") and desc:
        tags.append('<meta property="og:description" content="%s">' % _esc(desc))
    if not info.og.get("og:url"):
        tags.append('<meta property="og:url" content="%s">' % _esc(url))
    if not info.og.get("og:type"):
        tags.append('<meta property="og:type" content="website">')
    if not info.jsonld_types:
        ld = {"@context": "https://schema.org", "@type": "WebPage", "url": url}
        if title:
            ld["name"] = title
        if desc:
            ld["description"] = desc
        tags.append('<script type="application/ld+json">%s</script>'
                    % json.dumps(ld, ensure_ascii=False))
    return tags


def inject_into_head(html, tags):
    block = "\n".join(tags) + "\n"
    m = re.search(r"</head\s*>", html, re.IGNORECASE)
    if m:
        return html[: m.start()] + block + html[m.start():], True
    m = re.search(r"<html[^>]*>", html, re.IGNORECASE)
    if m:
        return html[: m.end()] + "\n<head>\n" + block + "</head>" + html[m.end():], True
    return html, False


def cmd_fix(args):
    cfg = load_config(args.site_dir)
    base = get_base_url(args, cfg)
    exclude = set(cfg.get("exclude", [])) | {"404.html"}
    files = html_files(args.site_dir, exclude)
    changed = 0
    for p in files:
        html = Path(p).read_text(encoding="utf-8", errors="replace")
        info = PageInfo()
        info.feed(html)
        tags = build_injections(info, page_url(base, args.site_dir, p))
        if not tags:
            continue
        new_html, ok = inject_into_head(html, tags)
        rel = Path(p).relative_to(args.site_dir)
        if not ok:
            print("%s  SKIPPED (no <head> found)" % rel)
            continue
        if args.dry_run:
            print("%s  would add %d tag(s)" % (rel, len(tags)))
        else:
            Path(p).write_text(new_html, encoding="utf-8")
            print("%s  added %d tag(s)" % (rel, len(tags)))
        changed += 1
    print("\n%d page(s) %s" % (changed, "would change" if args.dry_run else "updated"))
    return 0

# ------------------------------------------------------- sitemap/robots

def build_sitemap_xml(base, site_dir, exclude):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in html_files(site_dir, exclude):
        lastmod = time.strftime("%Y-%m-%d", time.gmtime(os.path.getmtime(p)))
        lines.append("<url><loc>%s</loc><lastmod>%s</lastmod></url>"
                     % (page_url(base, site_dir, p), lastmod))
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def cmd_sitemap(args):
    cfg = load_config(args.site_dir)
    base = get_base_url(args, cfg)
    exclude = set(cfg.get("exclude", [])) | {"404.html"}
    xml = build_sitemap_xml(base, args.site_dir, exclude)
    out = Path(args.site_dir) / "sitemap.xml"
    out.write_text(xml, encoding="utf-8")
    print("wrote %s (%d URLs)" % (out, xml.count("<url>")))
    return 0


def cmd_robots(args):
    cfg = load_config(args.site_dir)
    base = get_base_url(args, cfg)
    out = Path(args.site_dir) / "robots.txt"
    sitemap_line = "Sitemap: %ssitemap.xml" % base
    if out.is_file():
        text = out.read_text(encoding="utf-8")
        if "Sitemap:" in text:
            print("robots.txt already declares a sitemap; left unchanged")
            return 0
        text = text.rstrip() + "\n\n" + sitemap_line + "\n"
    else:
        text = "User-agent: *\nAllow: /\n\n%s\n" % sitemap_line
    out.write_text(text, encoding="utf-8")
    print("wrote %s" % out)
    return 0

# ---------------------------------------------------- verification file

def cmd_verify(args):
    if not args.google:
        raise SystemExit("error: pass --google CODE (the code from googleCODE.html)")
    name = "google%s.html" % args.google
    out = Path(args.site_dir) / name
    out.write_text("google-site-verification: %s\n" % name, encoding="utf-8")
    print("wrote %s - upload it, then click Verify in Search Console" % out)
    return 0

# -------------------------------------------------------------- IndexNow

def get_key(args, cfg, base, create=False):
    key = args.key or cfg.get("indexnow_key") or ""
    if not key and create:
        key = uuid.uuid4().hex
        key_file = Path(args.site_dir) / (key + ".txt")
        key_file.write_text(key + "\n", encoding="utf-8")
        cfg["base_url"] = base
        cfg["indexnow_key"] = key
        save_config(args.site_dir, cfg)
        print("created IndexNow key file %s" % key_file)
    if not key:
        raise SystemExit("error: no IndexNow key. Run: seo_launch.py key --base-url %s" % base)
    return key


def cmd_key(args):
    cfg = load_config(args.site_dir)
    base = get_base_url(args, cfg)
    get_key(args, cfg, base, create=True)
    return 0


def sitemap_urls(site_dir):
    path = Path(site_dir) / "sitemap.xml"
    if not path.is_file():
        return []
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.parse(str(path)).getroot()
    return [loc.text.strip() for loc in root.findall(".//s:loc", ns) if loc.text]


def build_payload(base, key, urls):
    from urllib.parse import urlparse
    host = urlparse(base).netloc
    return {
        "host": host,
        "key": key,
        "keyLocation": "%s%s.txt" % (base, key),
        "urlList": urls,
    }


def post_indexnow(endpoint, payload, dry_run=False):
    body = json.dumps(payload).encode("utf-8")
    if dry_run:
        return 0, "dry-run"
    req = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": "seo-launch/%s" % VERSION})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, "OK"
    except urllib.error.HTTPError as e:
        return e.code, e.reason or "HTTP error"
    except (urllib.error.URLError, OSError) as e:
        return -1, str(e)


def cmd_submit(args):
    cfg = load_config(args.site_dir)
    base = get_base_url(args, cfg)
    key = get_key(args, cfg, base)
    if args.urls:
        urls = [u.strip() for u in args.urls if u.strip()]
    else:
        urls = sitemap_urls(args.site_dir)
        if not urls:
            raise SystemExit("error: no sitemap.xml. Run: seo_launch.py sitemap --base-url %s" % base)
    names = list(INDEXNOW_ENDPOINTS) if args.all_engines else ["hub"]
    sent = 0
    for i in range(0, len(urls), CHUNK):
        payload = build_payload(base, key, urls[i:i + CHUNK])
        for name in names:
            code, msg = post_indexnow(INDEXNOW_ENDPOINTS[name], payload, args.dry_run)
            tag = "[dry-run]" if args.dry_run else ""
            print("%s %s: HTTP %s %s (%d URLs)" % (tag, name, code, msg, len(payload["urlList"])))
            if code != 0 and not (200 <= code <= 202):
                print("  -> check the key file is live: %s%s.txt" % (base, key), file=sys.stderr)
        sent += len(payload["urlList"])
    print("%d URL(s) submitted to %s" % (sent, ", ".join(names)))
    return 0

# --------------------------------------------------------- GitHub Action

WORKFLOW = """name: seo-launch
on:
  push:
    branches: [main, master]
  workflow_dispatch:
permissions:
  contents: read
jobs:
  submit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: get seo-launch
        run: |
          if [ ! -f seo_launch.py ]; then
            curl -fsSL -o seo_launch.py https://raw.githubusercontent.com/ibra8y3-web/seo-launch/main/seo_launch.py
          fi
      - name: rebuild sitemap and push every URL
        working-directory: ${{ vars.SEO_SITE_DIR || '.' }}
        run: |
          python "$GITHUB_WORKSPACE/seo_launch.py" sitemap --base-url "${{ vars.SEO_BASE_URL }}"
          python "$GITHUB_WORKSPACE/seo_launch.py" robots --base-url "${{ vars.SEO_BASE_URL }}"
          python "$GITHUB_WORKSPACE/seo_launch.py" submit --base-url "${{ vars.SEO_BASE_URL }}"
"""


def cmd_action(args):
    out = Path(args.site_dir) / ".github" / "workflows" / "seo-launch.yml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(WORKFLOW, encoding="utf-8")
    print("wrote %s" % out)
    print("set two repo variables (Settings > Secrets and variables > Actions > Variables):")
    print("  SEO_BASE_URL  = your site URL, e.g. https://user.github.io/site/")
    print("  SEO_SITE_DIR  = folder the site publishes from, e.g. docs (or leave unset for repo root)")
    return 0

# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="seo-launch",
        description="Push any static site to search engines, instantly.")
    ap.add_argument("--version", action="version", version="seo-launch " + VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def base_flags(p, url=False):
        p.add_argument("--site-dir", default=".", help="folder holding the site's HTML (default: .)")
        if url:
            p.add_argument("--base-url", help="public site URL, e.g. https://user.github.io/site/")

    p = sub.add_parser("scan", help="audit pages: titles, meta, canonical, OG, JSON-LD")
    base_flags(p); p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("fix", help="inject missing meta/canonical/OG/JSON-LD (idempotent)")
    base_flags(p, url=True); p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_fix)

    p = sub.add_parser("sitemap", help="write sitemap.xml")
    base_flags(p, url=True); p.set_defaults(fn=cmd_sitemap)

    p = sub.add_parser("robots", help="write robots.txt pointing at the sitemap")
    base_flags(p, url=True); p.set_defaults(fn=cmd_robots)

    p = sub.add_parser("verify", help="write the Google Search Console verification file")
    base_flags(p); p.add_argument("--google", metavar="CODE")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("key", help="create an IndexNow key file and save it to config")
    base_flags(p, url=True); p.add_argument("--key", help="use this key instead of generating one")
    p.set_defaults(fn=cmd_key)

    p = sub.add_parser("submit", help="submit URLs to IndexNow (Bing, Yandex, Naver, Seznam, Yep)")
    base_flags(p, url=True)
    p.add_argument("--key"); p.add_argument("--all-engines", action="store_true",
                   help="POST to every engine directly, not just the hub")
    p.add_argument("--urls", nargs="*", help="submit these URLs instead of the sitemap")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_submit)

    p = sub.add_parser("action", help="install the GitHub Action that pushes on every commit")
    base_flags(p); p.set_defaults(fn=cmd_action)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
