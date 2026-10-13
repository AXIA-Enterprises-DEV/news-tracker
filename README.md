# news-tracker

Free, live news RSS aggregator. GitHub Actions runs `scripts/fetch.py` every ~10 min, fetches every feed in
`feeds.yml` in parallel, dedupes (guid/link hash + normalized title), tags by source / category / US tickers
(`(NYSE: XYZ)`, `(Nasdaq: XYZ)`, `$XYZ`), and writes sharded JSON to `docs/data/`:

- `latest.json` – newest 600 items · `category/<cat>.json` – newest 300 per category
- `days/YYYY-MM-DD.json` – per-UTC-day shards (last 14 days) · `status.json` – per-feed health
- shards older than 14 days are gzipped into `archive/` (not published)

Front end: `docs/index.html` (static, MiniSearch full-text search, PT timestamps, dark mode, auto-refresh), deployed to GitHub Pages by the same workflow.

Edit `feeds.yml` to add/remove feeds. RSS/Atom only; no scraping. SEC requests use a User-Agent with contact `axia@mail.grokbot.com`.
Includes health-checked feeds imported from [plenaryapp/awesome-rss-feeds](https://github.com/plenaryapp/awesome-rss-feeds).
