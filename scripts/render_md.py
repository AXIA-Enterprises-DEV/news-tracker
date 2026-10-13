#!/usr/bin/env python3
"""Render docs/data JSON into Markdown pages, llms.txt and Atom feeds (machine-readable outputs)."""
import glob, json, os, re, shutil, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape as xesc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
DATA = os.path.join(DOCS, "data")
SITE = "https://axia-enterprises-dev.github.io/news-tracker"
PT = ZoneInfo("America/Los_Angeles")
LBL = {"us": "U.S.", "politics": "politics/policy"}
PAGE_N = 400

st = json.load(open(os.path.join(DATA, "status.json")))
PL = st.get("projects", {})
items = []
for f in glob.glob(os.path.join(DATA, "days", "*.json")):
    items += json.load(open(f))
items.sort(key=lambda i: -i["ts"])
now = datetime.now(PT)
UPD = now.isoformat(timespec="seconds")

def pt(ts, f="%H:%M"): return datetime.fromtimestamp(ts, PT).strftime(f)
def md_esc(s): return re.sub(r"([\[\]])", r"\\\1", s or "")
def tags(i):
    t = [f"#{i['category']}"] + [f"#{f}" for f in i.get("flags", [])] + [f"#{p}" for p in i.get("projects", []) if p != i["category"]] + [f"${x}" for x in i.get("tickers", [])]
    return " ".join(t)
def line(i, date=False):
    when = pt(i["ts"], "%b %d %H:%M") if date else pt(i["ts"])
    return f"- [{md_esc(i['title'])}]({i['link']}) — {i['source']} · {when} PT · {tags(i)}"
def front(title, count, tg, extra=""):
    tl = ", ".join(json.dumps(t) for t in tg)
    return f"---\ntitle: {json.dumps(title)}\nupdated: {UPD}\ncount: {count}\ntags: [{tl}]\n{extra}---\n\n"
def write(rel, text):
    p = os.path.join(DOCS, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)
def by_hour(lst):
    out, cur = [], None
    for i in lst:
        h = pt(i["ts"], "%Y-%m-%d %H:00")
        if h != cur: out.append(f"\n### {h} PT\n"); cur = h
        out.append(line(i))
    return "\n".join(out)
def by_day(lst):
    out, cur = [], None
    for i in lst:
        d = pt(i["ts"], "%Y-%m-%d")
        if d != cur: out.append(f"\n## {d}\n"); cur = d
        out.append(line(i))
    return "\n".join(out)

for d in ("news", "projects", "categories", "tickers", "sources", "feeds"):
    shutil.rmtree(os.path.join(DOCS, d), ignore_errors=True)

days = {}
for i in items: days.setdefault(pt(i["ts"], "%Y-%m-%d"), []).append(i)
for d, lst in days.items():
    write(f"news/{d}.md", front(f"News {d}", len(lst), ["news", "daily"]) + f"# News — {d} (PT)\n\n{len(lst)} items, newest first. [Prev/next: see index](../index.md)\n" + by_hour(lst) + "\n")

def group_page(kind, key, title, lst, tg):
    lst = lst[:PAGE_N]
    feed = f"../feeds/{key}.xml" if kind == "projects" else None
    head = f"# {title}\n\n{len(lst)} most recent items (14-day window)." + (f" Atom feed: [{key}.xml]({feed})" if feed else "") + "\n"
    write(f"{kind}/{key}.md", front(title, len(lst), tg) + head + by_day(lst) + "\n")

for k, v in PL.items():
    group_page("projects", k, f"Project: {v}", [i for i in items if k in i.get("projects", [])], ["project", k])
cats = sorted({i["category"] for i in items})
for c in cats:
    group_page("categories", c, f"Category: {LBL.get(c, c)}", [i for i in items if i["category"] == c], ["category", c])
tk = {}
for i in items:
    for t in i.get("tickers", []): tk.setdefault(t, []).append(i)
active = sorted(tk, key=lambda t: -len(tk[t]))[:300]
for t in active:
    group_page("tickers", t, f"Ticker: ${t}", tk[t], ["ticker", t])
srcs = {}
for i in items: srcs.setdefault(i["source"], []).append(i)
fs = {f["name"]: f for f in st["feeds"]}
rows = [f"| {s} | {fs.get(s,{}).get('category','')} | {len(l)} | {'ok' if fs.get(s,{}).get('ok') else 'down'} | {pt(l[0]['ts'],'%b %d %H:%M')} PT |" for s, l in sorted(srcs.items())]
write("sources/index.md", front("Sources", len(srcs), ["sources"]) + f"# Sources\n\n{st['feeds_ok']}/{st['feeds_total']} feeds OK at last sync.\n\n| Source | Category | Items | Status | Latest |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n")
write("tickers/index.md", front("Tickers", len(active), ["tickers"]) + "# Active tickers\n\n" + "\n".join(f"- [${t}]({t}.md) — {len(tk[t])} items" for t in active) + "\n")

nav = ("## Browse\n\n**Days:** " + " · ".join(f"[{d}](news/{d}.md)" for d in sorted(days, reverse=True)) +
       "\n\n**Projects:** " + " · ".join(f"[{v}](projects/{k}.md)" for k, v in PL.items()) +
       "\n\n**Categories:** " + " · ".join(f"[{LBL.get(c,c)}](categories/{c}.md)" for c in cats) +
       "\n\n**Top tickers:** " + " · ".join(f"[${t}](tickers/{t}.md)" for t in active[:25]) + " · [all](tickers/index.md)" +
       "\n\n**Machine-readable:** [llms.txt](llms.txt) · [llms-full.txt](llms-full.txt) · [latest.json](data/latest.json) · [Atom: all](feeds/all.xml) · [sources](sources/index.md)\n")
write("index.md", front("News Tracker", min(100, len(items)), ["index"]) +
      f"# News Tracker\n\nLive news aggregator: {len(items)} items from {st['feeds_ok']}/{st['feeds_total']} feeds, last sync {pt(st['updated'],'%Y-%m-%d %H:%M')} PT. Updates about every 10 minutes.\n\n" +
      nav + "\n## Latest 100\n\n(SEC filings excluded except 8-K Item 1.01 material agreements; see [Filings](categories/filings.md).)\n" + by_hour([i for i in items if i["category"] != "filings" or i.get("flags")][:100]) + "\n")

# llms.txt (spec-style index) + llms-full.txt (latest items, flat)
write("llms.txt", f"# AXIA News Tracker\n\n> Live news aggregator (RSS/Atom only) updated ~every 10 min. All pages are plain Markdown with YAML frontmatter; item lines are `- [Title](url) — Source · HH:MM PT · #category #project $TICKER`.\n\nLast sync: {pt(st['updated'],'%Y-%m-%d %H:%M')} PT · {len(items)} items · {st['feeds_ok']}/{st['feeds_total']} feeds OK\n\n"
      "## Core\n\n" + f"- [Index]({SITE}/index.md): latest 100 + navigation\n- [Full latest dump]({SITE}/llms-full.txt): newest 1000 items, one per line\n- [JSON latest]({SITE}/data/latest.json)\n- [Status]({SITE}/data/status.json)\n- [Sources]({SITE}/sources/index.md)\n\n"
      "## Days\n\n" + "\n".join(f"- [{d}]({SITE}/news/{d}.md)" for d in sorted(days, reverse=True)) +
      "\n\n## Projects\n\n" + "\n".join(f"- [{v}]({SITE}/projects/{k}.md): Atom {SITE}/feeds/{k}.xml" for k, v in PL.items()) +
      "\n\n## Categories\n\n" + "\n".join(f"- [{LBL.get(c,c)}]({SITE}/categories/{c}.md)" for c in cats) +
      "\n\n## Optional\n\n- [Tickers]({SITE}/tickers/index.md)\n")
write("llms-full.txt", f"# AXIA News Tracker — latest {min(1000,len(items))} items (updated {pt(st['updated'],'%Y-%m-%d %H:%M')} PT)\n\n" + "\n".join(line(i, True) for i in items[:1000]) + "\n")

def atom(key, title, lst):
    ents = "".join(f"<entry><title>{xesc(i['title'])}</title><link href=\"{xesc(i['link'])}\"/><id>urn:nt:{i['id']}</id><updated>{datetime.fromtimestamp(i['ts'],timezone.utc).isoformat()}</updated><summary>{xesc(i.get('summary',''))}</summary><author><name>{xesc(i['source'])}</name></author>{''.join(f'<category term=\"{xesc(c)}\"/>' for c in [i['category']]+i.get('projects',[]))}</entry>" for i in lst[:100])
    write(f"feeds/{key}.xml", f'<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"><title>{xesc(title)}</title><id>{SITE}/feeds/{key}.xml</id><link rel="self" href="{SITE}/feeds/{key}.xml"/><link href="{SITE}/"/><updated>{datetime.now(timezone.utc).isoformat()}</updated>{ents}</feed>\n')
atom("all", "AXIA News Tracker — all", items)
for k, v in PL.items(): atom(k, f"AXIA News Tracker — {v}", [i for i in items if k in i.get("projects", [])])
# manifest for the front end explorer
json.dump({"days": sorted(days, reverse=True), "projects": PL, "categories": cats, "tickers": active,
           "updated": st["updated"]}, open(os.path.join(DATA, "manifest.json"), "w"))
print(f"md: {len(days)} days, {len(PL)} projects, {len(cats)} cats, {len(active)} tickers")
