# seo-launch

Push any static site to search engines, instantly. One Python file, no dependencies.

[النسخة العربية](README.ar.md)

Most SEO advice tells you to publish and wait weeks for crawlers. seo-launch does
the opposite: it prepares your pages technically and then *tells* the engines the
moment anything changes, using [IndexNow](https://www.indexnow.org/) - the live
notification protocol run by Bing, Yandex, Naver, Seznam and Yep.

## The honest part

**No tool on earth can force Google to index or rank your page.** Anyone who
promises that is selling something. What seo-launch does is remove every
technical blocker (missing titles, descriptions, canonicals, sitemaps) and push
live notifications to every engine that accepts them, so discovery takes minutes
instead of weeks. Google joined no notification protocol; for Google you still
verify in Search Console and request indexing - seo-launch generates the
verification file for you. Google's own crawler usually follows within days once
Bing and the others start visiting.

## What it does

| Command | What you get |
| --- | --- |
| `scan` | audit of every page: title, meta description, canonical, Open Graph, JSON-LD |
| `fix` | injects the missing tags (idempotent - safe to run repeatedly) |
| `sitemap` | generates `sitemap.xml` from your HTML files |
| `robots` | generates `robots.txt` pointing at the sitemap |
| `verify --google CODE` | writes the Search Console verification file |
| `key` | creates your IndexNow key file (`<key>.txt`) |
| `submit` | POSTs your URLs to IndexNow (all member engines share it) |
| `action` | installs a GitHub Action that re-submits on every push |

## Quick start (GitHub Pages)

```bash
# inside your site's folder (the one that holds index.html)
python seo_launch.py fix --base-url https://YOU.github.io/YOUR-SITE/
python seo_launch.py sitemap --base-url https://YOU.github.io/YOUR-SITE/
python seo_launch.py robots --base-url https://YOU.github.io/YOUR-SITE/
python seo_launch.py key --base-url https://YOU.github.io/YOUR-SITE/
git add -A && git commit -m "seo-launch" && git push

# once the key file is live on the site, push every URL:
python seo_launch.py submit --base-url https://YOU.github.io/YOUR-SITE/
```

Then install the GitHub Action so every future push is submitted automatically:

```bash
python seo_launch.py action
```

Commit the generated `.github/workflows/seo-launch.yml` and set two repository
variables (Settings > Secrets and variables > Actions > Variables):

- `SEO_BASE_URL` = your site URL, e.g. `https://you.github.io/site/`
- `SEO_SITE_DIR` = the folder the site publishes from (`docs`, or leave unset for repo root)

## Useful options

- `submit --dry-run` - print exactly what would be sent, send nothing.
- `submit --all-engines` - POST to Bing/Yandex/Naver/Seznam/Yep directly instead
  of only the shared hub. Not needed normally; the hub shares with all of them.
- `submit --urls URL...` - submit specific URLs instead of the whole sitemap.
- `fix --dry-run` - preview the injections without touching files.
- `seo-launch.json` in your site folder remembers `base_url` and
  `indexnow_key`, so you can drop the flags on later runs.

## Requirements

Python 3.8+. Nothing else. No pip install, no build step.

## What seo-launch is not

- Not a ranking guarantee. Content and links decide ranking; this removes the
  technical waiting game.
- Not a Google submission API. Google's Indexing API is restricted to job
  postings and live streams; Search Console "Request indexing" is manual.
  seo-launch prepares everything Google needs and speeds up the engines that
  accept live push.

## License

MIT - see [LICENSE](LICENSE).
