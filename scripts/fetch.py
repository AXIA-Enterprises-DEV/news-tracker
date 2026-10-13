#!/usr/bin/env python3
"""Fetch RSS feeds -> dedupe -> tag -> sharded JSON in docs/data (served by GitHub Pages)."""
import calendar, concurrent.futures as cf, gzip, hashlib, html, json, os, re, time, urllib.request
from datetime import datetime, timezone, timedelta
import feedparser, yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data")
DAYS = os.path.join(DATA, "days")
ARCH = os.path.join(ROOT, "archive")
KEEP_DAYS = 14          # days kept on Pages; older shards are gzipped into archive/
LATEST_N = 600
CAT_N = 300
CATS = ["markets", "business", "tech", "politics", "world", "us", "science", "sports", "filings"]
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

TICK_RE = re.compile(r"\((?:NYSE|NASDAQ|Nasdaq|NYSE American|NYSE MKT|NYSE Arca|Cboe|OTCQX|OTCQB|OTC|AMEX|TSX|TSXV)\s*:\s*([A-Z]{1,5}(?:\.[A-Z])?)", re.I)
TICK_RE2 = re.compile(r"(?:NYSE|NASDAQ|Nasdaq|AMEX)\s*:\s*([A-Z]{1,5}(?:\.[A-Z])?)\b")
CASHTAG = re.compile(r"(?<![\w$])\$([A-Z]{1,5})\b")
TAG_RE = re.compile(r"<[^>]+>")

def clean(s, n=None):
    s = html.unescape(TAG_RE.sub(" ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n] if n else s

def norm_title(t):
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()[:160]

def fetch(feed, ua):
    hdr = {"User-Agent": BROWSER_UA if feed.get("ua") == "browser" else ua,
           "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"}
    t0 = time.time()
    try:
        raw = urllib.request.urlopen(urllib.request.Request(feed["url"], headers=hdr), timeout=12).read()
        p = feedparser.parse(raw)
        return feed, p.entries, None, round(time.time() - t0, 2)
    except Exception as e:
        return feed, [], str(e)[:200], round(time.time() - t0, 2)

def entry_ts(e):
    for k in ("published_parsed", "updated_parsed"):
        v = e.get(k)
        if v:
            ts = calendar.timegm(v)
            return min(ts, int(time.time()))
    return int(time.time())

def tickers(text):
    s = set(m.upper() for m in TICK_RE.findall(text)) | set(TICK_RE2.findall(text)) | set(CASHTAG.findall(text))
    return sorted(s)[:8]

def load_projects():
    try: cfg = yaml.safe_load(open(os.path.join(ROOT, "projects.yml")))["projects"]
    except Exception: return {}, {}
    rules = {k: re.compile("|".join(f"(?:{r})" for r in v["any"]), re.I) for k, v in cfg.items()}
    return rules, {k: v.get("label", k) for k, v in cfg.items()}

def tag_projects(it, rules, forced=None):
    text = f"{it['title']} {it.get('summary','')}"
    ps = {k for k, rx in rules.items() if rx.search(text)}
    if forced: ps.add(forced)
    if it["category"] == "filings":
        ps.add("markets")
        if re.search(r"Item 1\.01", text): it["flags"] = ["item-1.01"]
    if "nevada" in ps and "realestate" in ps: pass
    return sorted(ps)

def load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default

def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

def main():
    cfg = yaml.safe_load(open(os.path.join(ROOT, "feeds.yml")))
    ua = cfg.get("user_agent")
    rules, labels = load_projects()
    feeds = [f for f in cfg["feeds"] if f.get("enabled", True)]
    os.makedirs(DAYS, exist_ok=True)

    # existing items within retention window
    items, seen_id, seen_title = {}, set(), set()
    for fn in sorted(os.listdir(DAYS)):
        for it in load(os.path.join(DAYS, fn), []):
            items[it["id"]] = it; seen_id.add(it["id"]); seen_title.add(norm_title(it["title"]))

    fmap = {f["name"]: f.get("project") for f in feeds}
    for it in items.values(): it["projects"] = tag_projects(it, rules, fmap.get(it["source"]))
    status, added = [], 0
    with cf.ThreadPoolExecutor(32) as ex:
        results = list(ex.map(lambda f: fetch(f, ua), feeds))
    for feed, entries, err, secs in results:
        n_new = 0
        for e in entries:
            link = e.get("link") or ""
            key = e.get("id") or e.get("guid") or link
            title = clean(e.get("title"), 300)
            if not title or not key: continue
            iid = hashlib.sha1(key.encode()).hexdigest()[:14]
            lid = hashlib.sha1(link.encode()).hexdigest()[:14] if link else iid
            nt = norm_title(title)
            if iid in seen_id or lid in seen_id or nt in seen_title: continue
            if entry_ts(e) < time.time() - KEEP_DAYS * 86400: continue  # too old to be news
            summary = clean(e.get("summary") or e.get("description"), 400)
            text = f"{title} {summary}"
            it = {"id": iid, "title": title, "link": link, "summary": summary,
                  "source": feed["name"], "category": feed["category"], "ts": entry_ts(e),
                  "tickers": tickers(text)}
            it["projects"] = tag_projects(it, rules, feed.get("project"))
            if feed["category"] == "filings":  # e.g. "8-K - ACME CORP (0001234) (Filer)"
                m = re.match(r"([\w\-/ ]+?) - ", title)
                if m: it["form"] = m.group(1).strip()
            items[iid] = it; seen_id.update([iid, lid]); seen_title.add(nt); n_new += 1
        added += n_new
        status.append({"name": feed["name"], "url": feed["url"], "category": feed["category"],
                       "ok": err is None and len(entries) > 0, "entries": len(entries),
                       "new": n_new, "error": err, "secs": secs})

    # shard by UTC day; archive old shards
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    by_day = {}
    for it in items.values():
        d = datetime.fromtimestamp(it["ts"], timezone.utc).strftime("%Y-%m-%d")
        by_day.setdefault(d, []).append(it)
    os.makedirs(ARCH, exist_ok=True)
    for fn in os.listdir(DAYS):
        if fn[:10] not in by_day or fn[:10] < cutoff: os.remove(os.path.join(DAYS, fn))
    for d, lst in by_day.items():
        lst.sort(key=lambda x: -x["ts"])
        if d < cutoff:
            ap = os.path.join(ARCH, f"{d}.json.gz")
            old = json.load(gzip.open(ap)) if os.path.exists(ap) else []
            ids = {x["id"] for x in old}
            with gzip.open(ap, "wt") as f: json.dump(old + [x for x in lst if x["id"] not in ids], f, separators=(",", ":"))
        else:
            dump(os.path.join(DAYS, f"{d}.json"), lst)

    live = sorted((i for d, l in by_day.items() if d >= cutoff for i in l), key=lambda x: -x["ts"])
    dump(os.path.join(DATA, "latest.json"), live[:LATEST_N])
    for pk in labels:
        dump(os.path.join(DATA, "project", f"{pk}.json"), [i for i in live if pk in i.get("projects", [])][:CAT_N])
    for c in CATS:
        dump(os.path.join(DATA, "category", f"{c}.json"), [i for i in live if i["category"] == c][:CAT_N])
    ok = sum(1 for s in status if s["ok"])
    dump(os.path.join(DATA, "status.json"), {
        "updated": int(time.time()), "feeds_total": len(status), "feeds_ok": ok, "added": added,
        "items_live": len(live), "projects": labels, "days": sorted([d for d in by_day if d >= cutoff], reverse=True), "feeds": status})
    print(f"feeds ok {ok}/{len(status)}, new {added}, live {len(live)}")
    for s in status:
        if not s["ok"]: print("  FAIL", s["name"], s["error"])

if __name__ == "__main__":
    main()
