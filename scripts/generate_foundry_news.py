#!/usr/bin/env python3
"""Generate a daily Microsoft Foundry news digest as a Markdown file.

Runs in GitHub Actions (cloud) on a schedule. Uses only the Python standard
library so it needs no third-party dependencies. Pulls official Microsoft
Foundry / Azure blog RSS feeds, filters for Foundry-relevant items, and writes
``microsoft-foundry-news-YYYY-MM-DD.md`` (today's UTC date).

If a ``GITHUB_TOKEN`` with ``models: read`` permission is present, the script
adds a best-effort AI executive summary via the GitHub Models API. If that call
fails for any reason, the script still produces a complete deterministic digest.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
import urllib.error
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree as ET

# Feeds to pull. The Foundry DevBlog is Foundry-specific; the Azure blog is
# broad, so its items are keyword-filtered below.
FEEDS = [
    {"url": "https://devblogs.microsoft.com/foundry/feed/", "foundry_only": True,
     "source": "Microsoft Foundry Blog"},
    {"url": "https://azure.microsoft.com/en-us/blog/feed/", "foundry_only": False,
     "source": "Azure Blog"},
]

KEYWORDS = ("foundry", "ai foundry", "azure ai foundry")
USER_AGENT = "foundry-news-bot/1.0 (+https://github.com/mddiallo/Microsoft_Foundry_News)"
RECENT_WINDOW_DAYS = 7
HTTP_TIMEOUT = 30


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read()


def strip_html(text: str) -> str:
    out = []
    skip = False
    for ch in text:
        if ch == "<":
            skip = True
        elif ch == ">":
            skip = False
        elif not skip:
            out.append(ch)
    return unescape("".join(out)).strip()


def parse_feed(raw: bytes, source: str, foundry_only: bool) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = item.findtext("pubDate") or ""
        desc = strip_html(item.findtext("description") or "")
        cats = " ".join((c.text or "") for c in item.findall("category"))
        try:
            published = parsedate_to_datetime(pub_raw)
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
            published = published.astimezone(dt.timezone.utc)
        except (TypeError, ValueError):
            published = None
        haystack = f"{title} {desc} {cats}".lower()
        if foundry_only or any(k in haystack for k in KEYWORDS):
            items.append({
                "title": title,
                "link": link,
                "published": published,
                "summary": desc[:400].rsplit(" ", 1)[0] + ("…" if len(desc) > 400 else ""),
                "source": source,
            })
    return items


def gather_items() -> list[dict]:
    all_items: list[dict] = []
    seen_links = set()
    for feed in FEEDS:
        try:
            raw = fetch(feed["url"])
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"warning: failed to fetch {feed['url']}: {exc}", file=sys.stderr)
            continue
        for it in parse_feed(raw, feed["source"], feed["foundry_only"]):
            if it["link"] and it["link"] not in seen_links:
                seen_links.add(it["link"])
                all_items.append(it)
    all_items.sort(key=lambda x: x["published"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
                   reverse=True)
    return all_items


def ai_summary(items: list[dict]) -> str | None:
    """Best-effort executive summary via GitHub Models. Returns None on failure."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token or not items:
        return None
    bullet_src = "\n".join(f"- {it['title']}: {it['summary']}" for it in items[:12])
    body = {
        "model": os.environ.get("MODELS_MODEL", "openai/gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": "You are a concise tech news editor. "
             "Write a 2-3 sentence executive summary of the day's Microsoft "
             "Foundry news. No preamble, no markdown headings."},
            {"role": "user", "content": f"Today's Microsoft Foundry items:\n{bullet_src}"},
        ],
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        "https://models.github.ai/inference/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001 - summary is optional
        print(f"warning: AI summary unavailable: {exc}", file=sys.stderr)
        return None


def build_markdown(today: dt.date, items: list[dict]) -> str:
    today_items = [it for it in items if it["published"] and it["published"].date() == today]
    cutoff = today - dt.timedelta(days=RECENT_WINDOW_DAYS)
    recent_items = [it for it in items
                    if it["published"] and cutoff <= it["published"].date() <= today]
    no_new = not today_items
    display = today_items if today_items else recent_items[:10]

    lines = [
        "# Microsoft Foundry — Daily News Digest",
        "",
        f"**Date:** {today.isoformat()} (UTC)",
        "",
        "> Automated digest generated from official Microsoft Foundry and Azure "
        "blog feeds.",
        "",
    ]

    if no_new:
        lines += [
            "> **Note:** No brand-new Microsoft Foundry items were published in the "
            "source feeds today. Below are the most recent relevant updates.",
            "",
        ]

    summary = ai_summary(display)
    if summary:
        lines += ["## Executive Summary", "", summary, ""]

    lines += ["## Headlines", ""]
    if display:
        for it in display:
            date_str = it["published"].date().isoformat() if it["published"] else "n/a"
            lines.append(f"### [{it['title']}]({it['link']})")
            lines.append("")
            lines.append(f"*{date_str} — {it['source']}*")
            lines.append("")
            if it["summary"]:
                lines.append(it["summary"])
                lines.append("")
    else:
        lines += ["_No Foundry-related items found in the source feeds._", ""]

    lines += [
        "## Sources",
        "",
        "- [Microsoft Foundry Blog](https://devblogs.microsoft.com/foundry/)",
        "- [Azure Blog](https://azure.microsoft.com/en-us/blog/)",
        "",
        f"*Generated automatically on {dt.datetime.now(dt.timezone.utc).isoformat()} "
        "by the daily GitHub Actions workflow.*",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    today = dt.datetime.now(dt.timezone.utc).date()
    items = gather_items()
    markdown = build_markdown(today, items)
    out_name = f"microsoft-foundry-news-{today.isoformat()}.md"
    with open(out_name, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    print(f"Wrote {out_name} ({len(markdown)} chars, {len(items)} items gathered)")
    # Expose the filename to later workflow steps.
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"file={out_name}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
