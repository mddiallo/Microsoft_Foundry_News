#!/usr/bin/env python3
"""Generate a daily Microsoft Foundry news digest as a Markdown file.

Runs in GitHub Actions (cloud) on a schedule. Uses only the Python standard
library so it needs no third-party dependencies. Pulls official Microsoft
Foundry / Azure blog RSS feeds, filters for Foundry-relevant items, and writes
``microsoft-foundry-news-YYYY-MM-DD.md`` (today's UTC date).

Before writing, the script scans previously generated daily digests and drops
any item whose link has already been published. If nothing new remains, it
writes a short "no news" digest for the day instead of repeating older items.

If a ``GITHUB_TOKEN`` with ``models: read`` permission is present, the script
adds a best-effort AI executive summary via the GitHub Models API. If that call
fails for any reason, the script still produces a complete deterministic digest.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
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

# Previously generated digests are named like this; we scan them to find links
# that have already been published so the same item is never repeated.
NEWS_GLOB = "microsoft-foundry-news-*.md"
HEADLINE_LINK_RE = re.compile(r"^###\s+\[.*\]\((.+)\)\s*$")


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


def published_links(today: dt.date) -> set[str]:
    """Return links already present in previously generated daily digests.

    Each digest lists items as ``### [title](link)`` headlines. We collect every
    such link so items that were already published are not repeated. Today's own
    file is skipped so manual re-runs on the same day stay idempotent.
    """
    today_file = f"microsoft-foundry-news-{today.isoformat()}.md"
    links: set[str] = set()
    for path in sorted(glob.glob(NEWS_GLOB)):
        if os.path.basename(path) == today_file:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    match = HEADLINE_LINK_RE.match(line.strip())
                    if match:
                        links.add(match.group(1).strip())
        except OSError as exc:
            print(f"warning: could not read {path}: {exc}", file=sys.stderr)
    return links


def select_new_items(today: dt.date, items: list[dict],
                     already_published: set[str]) -> list[dict]:
    """Keep recent items whose link has not appeared in an earlier digest."""
    cutoff = today - dt.timedelta(days=RECENT_WINDOW_DAYS)
    new_items: list[dict] = []
    for it in items:
        if not it["link"] or it["link"] in already_published:
            continue
        published = it["published"]
        if published is not None and not (cutoff <= published.date() <= today):
            continue
        new_items.append(it)
    return new_items


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


SOURCES_FOOTER = [
    "## Sources",
    "",
    "- [Microsoft Foundry Blog](https://devblogs.microsoft.com/foundry/)",
    "- [Azure Blog](https://azure.microsoft.com/en-us/blog/)",
    "",
]


def _header(today: dt.date) -> list[str]:
    return [
        "# Microsoft Foundry — Daily News Digest",
        "",
        f"**Date:** {today.isoformat()} (UTC)",
        "",
        "> Automated digest generated from official Microsoft Foundry and Azure "
        "blog feeds.",
        "",
    ]


def _footer() -> list[str]:
    return SOURCES_FOOTER + [
        f"*Generated automatically on {dt.datetime.now(dt.timezone.utc).isoformat()} "
        "by the daily GitHub Actions workflow.*",
        "",
    ]


def build_markdown(today: dt.date, new_items: list[dict]) -> str:
    """Render the digest for ``today`` from items not seen in earlier digests.

    When ``new_items`` is empty every relevant feed item has already been
    published, so a short "no news" digest is produced for the day.
    """
    lines = _header(today)

    if not new_items:
        lines += [
            "## No News Today",
            "",
            f"There is no new Microsoft Foundry news for {today.isoformat()}. "
            "Every relevant item currently available in the source feeds has "
            "already been covered in a previous daily digest.",
            "",
        ]
        return "\n".join(lines + _footer())

    summary = ai_summary(new_items)
    if summary:
        lines += ["## Executive Summary", "", summary, ""]

    lines += ["## Headlines", ""]
    for it in new_items:
        date_str = it["published"].date().isoformat() if it["published"] else "n/a"
        lines.append(f"### [{it['title']}]({it['link']})")
        lines.append("")
        lines.append(f"*{date_str} — {it['source']}*")
        lines.append("")
        if it["summary"]:
            lines.append(it["summary"])
            lines.append("")

    return "\n".join(lines + _footer())


def main() -> int:
    today = dt.datetime.now(dt.timezone.utc).date()
    items = gather_items()
    already = published_links(today)
    new_items = select_new_items(today, items, already)
    markdown = build_markdown(today, new_items)
    out_name = f"microsoft-foundry-news-{today.isoformat()}.md"
    with open(out_name, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    print(f"Wrote {out_name} ({len(markdown)} chars; {len(items)} gathered, "
          f"{len(already)} previously published, {len(new_items)} new)")
    # Expose results to later workflow steps.
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"file={out_name}\n")
            fh.write(f"has_news={'true' if new_items else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
