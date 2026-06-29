#!/usr/bin/env python3
"""Generate daily Microsoft Foundry news digests as Markdown files.

Runs in GitHub Actions (cloud) on a schedule. Uses only the Python standard
library so it needs no third-party dependencies. Pulls official Microsoft
Foundry / Azure blog RSS feeds and selected external technology news feeds,
filters for Foundry-relevant items, and writes two files for today's UTC date:

* ``microsoft-foundry-news-YYYY-MM-DD.md`` for Microsoft-owned websites.
* ``external-foundry-news-YYYY-MM-DD.md`` for non-Microsoft websites.

Before writing, the script scans previously generated daily digests for each
group and drops any item whose link has already been published. If nothing new
remains, it writes a short "no news" digest for the day instead of repeating
older items.

If a ``GITHUB_TOKEN`` with ``models: read`` permission is present, the script
uses a named news explainer agent via the GitHub Models API to explain each
news item. If that call fails for any reason, the script still produces a
complete deterministic digest.
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
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class Feed:
    url: str
    source: str
    foundry_only: bool = False
    microsoft_owned: bool = False


@dataclass(frozen=True)
class Digest:
    file_prefix: str
    title: str
    source_description: str
    feeds: tuple[Feed, ...]
    microsoft_owned: bool


MICROSOFT_FEEDS = (
    # The Foundry DevBlog is Foundry-specific; the broader Microsoft feeds are
    # keyword-filtered below.
    Feed(
        url="https://devblogs.microsoft.com/foundry/feed/",
        source="Microsoft Foundry Blog",
        foundry_only=True,
        microsoft_owned=True,
    ),
    Feed(
        url="https://azure.microsoft.com/en-us/blog/feed/",
        source="Azure Blog",
        microsoft_owned=True,
    ),
)

EXTERNAL_FEEDS = (
    Feed(url="https://techcrunch.com/feed/", source="TechCrunch"),
    Feed(url="https://venturebeat.com/category/ai/feed", source="VentureBeat AI"),
    Feed(url="https://www.theverge.com/rss/microsoft/index.xml", source="The Verge - Microsoft"),
    Feed(url="https://www.zdnet.com/news/rss.xml", source="ZDNET"),
)

DIGESTS = (
    Digest(
        file_prefix="microsoft-foundry-news",
        title="Microsoft Foundry — Microsoft Website News Digest",
        source_description="official Microsoft websites",
        feeds=MICROSOFT_FEEDS,
        microsoft_owned=True,
    ),
    Digest(
        file_prefix="external-foundry-news",
        title="Microsoft Foundry — External Website News Digest",
        source_description="external, non-Microsoft websites",
        feeds=EXTERNAL_FEEDS,
        microsoft_owned=False,
    ),
)

FOUNDRY_PHRASES = (
    "microsoft foundry",
    "microsoft ai foundry",
    "azure ai foundry",
    "azure foundry",
    "foundry local",
    "foundry agent service",
    "foundry managed compute",
    "foundry tools",
)
MICROSOFT_HOST_SUFFIXES = (".microsoft.com",)
USER_AGENT = "foundry-news-bot/1.0 (+https://github.com/mddiallo/Microsoft_Foundry_News)"
RECENT_WINDOW_DAYS = 7
HTTP_TIMEOUT = 30
MAX_AGENT_ITEMS = 12
DEFAULT_AGENT_NAME = "Microsoft Foundry News Explainer"
DEFAULT_MODEL = "openai/gpt-4o-mini"

# Previously generated digests are named like this; we scan them to find links
# that have already been published so the same item is never repeated.
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


def parse_date(raw: str) -> dt.datetime | None:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def is_microsoft_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host == "microsoft.com" or any(host.endswith(suffix) for suffix in MICROSOFT_HOST_SUFFIXES)


def is_foundry_related(title: str, summary: str, categories: str) -> bool:
    haystack = f"{title} {summary} {categories}".lower()
    return any(phrase in haystack for phrase in FOUNDRY_PHRASES)


def trim_summary(text: str, limit: int = 400) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def _item_dict(title: str, link: str, published: dt.datetime | None,
               summary: str, source: str) -> dict:
    return {
        "title": title,
        "link": link,
        "published": published,
        "summary": trim_summary(summary),
        "source": source,
    }


def parse_feed(raw: bytes, feed: Feed) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        summary = strip_html(item.findtext("description") or "")
        cats = " ".join((c.text or "") for c in item.findall("category"))
        if feed.foundry_only or is_foundry_related(title, summary, cats):
            items.append(_item_dict(title, link, parse_date(item.findtext("pubDate") or ""),
                                    summary, feed.source))
    atom_ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.iter(f"{atom_ns}entry"):
        title = (entry.findtext(f"{atom_ns}title") or "").strip()
        link_el = entry.find(f"{atom_ns}link[@rel='alternate']")
        if link_el is None:
            link_el = entry.find(f"{atom_ns}link")
        link = (link_el.get("href") if link_el is not None else "") or ""
        summary = strip_html(
            entry.findtext(f"{atom_ns}summary")
            or entry.findtext(f"{atom_ns}content")
            or ""
        )
        cats = " ".join(c.get("term", "") for c in entry.findall(f"{atom_ns}category"))
        if feed.foundry_only or is_foundry_related(title, summary, cats):
            items.append(_item_dict(title, link,
                                    parse_date(entry.findtext(f"{atom_ns}published")
                                               or entry.findtext(f"{atom_ns}updated")
                                               or ""),
                                    summary, feed.source))
    return items


def gather_items(digest: Digest) -> list[dict]:
    all_items: list[dict] = []
    seen_links = set()
    for feed in digest.feeds:
        try:
            raw = fetch(feed.url)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"warning: failed to fetch {feed.url}: {exc}", file=sys.stderr)
            continue
        for it in parse_feed(raw, feed):
            if it["link"] and it["link"] not in seen_links:
                if digest.microsoft_owned != (feed.microsoft_owned or is_microsoft_url(it["link"])):
                    continue
                seen_links.add(it["link"])
                all_items.append(it)
    all_items.sort(key=lambda x: x["published"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
                   reverse=True)
    return all_items


def published_links(today: dt.date, digest: Digest) -> set[str]:
    """Return links already present in previously generated daily digests.

    Each digest lists items as ``### [title](link)`` headlines. We collect every
    such link so items that were already published are not repeated. Today's own
    file is skipped so manual re-runs on the same day stay idempotent.
    """
    today_file = filename_for(digest, today)
    links: set[str] = set()
    for path in sorted(glob.glob(f"{digest.file_prefix}-*.md")):
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


def news_agent_name() -> str:
    return os.environ.get("NEWS_EXPLAINER_AGENT", DEFAULT_AGENT_NAME)


def agent_response(messages: list[dict], warning_context: str) -> str | None:
    """Best-effort response via the named GitHub Models news agent."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    body = {
        "model": os.environ.get("MODELS_MODEL", DEFAULT_MODEL),
        "messages": messages,
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
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError,
            KeyError, IndexError, TypeError) as exc:
        print(f"warning: agent response unavailable for {warning_context}: {exc}", file=sys.stderr)
        return None


def agent_summary(items: list[dict], digest: Digest) -> str | None:
    """Best-effort executive summary via the named news agent."""
    if not items:
        return None
    agent_name = news_agent_name()
    bullet_src = "\n".join(f"- {it['title']}: {it['summary']}" for it in items[:MAX_AGENT_ITEMS])
    return agent_response(
        [
            {
                "role": "system",
                "content": (
                    f"You are {agent_name}, a concise specialist agent for "
                    "Microsoft Foundry news. Write a 2-3 sentence executive "
                    "summary for technical and business readers. No preamble "
                    "and no markdown heading."
                ),
            },
            {
                "role": "user",
                "content": f"Today's {digest.source_description} Microsoft Foundry items:\n{bullet_src}",
            },
        ],
        f"{digest.file_prefix} summary",
    )


def agent_explanation(item: dict) -> str | None:
    """Best-effort per-item explanation via the named news agent."""
    agent_name = news_agent_name()
    return agent_response(
        [
            {
                "role": "system",
                "content": (
                    f"You are {agent_name}, a concise specialist agent for "
                    "Microsoft Foundry news. Explain one news item for technical "
                    "and business readers in 2 short sentences. Focus on what "
                    "changed and why it matters. No preamble and no markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Title: {item['title']}\n"
                    f"Source: {item['source']}\n"
                    f"Published: {item['published']}\n"
                    f"Summary: {item['summary']}"
                ),
            },
        ],
        item["link"],
    )


def explain_items(items: list[dict]) -> None:
    for item in items[:MAX_AGENT_ITEMS]:
        item["explanation"] = agent_explanation(item) or fallback_explanation(item)
    for item in items[MAX_AGENT_ITEMS:]:
        item["explanation"] = fallback_explanation(item)


def fallback_explanation(item: dict) -> str:
    if item["summary"]:
        return item["summary"]
    return "This item was identified as Microsoft Foundry-related, but the feed did not include a detailed summary."


def sources_footer(digest: Digest) -> list[str]:
    lines = [
        "## Sources",
        "",
    ]
    lines.extend(f"- [{feed.source}]({feed.url})" for feed in digest.feeds)
    lines.append("")
    return lines


def filename_for(digest: Digest, today: dt.date) -> str:
    return f"{digest.file_prefix}-{today.isoformat()}.md"


def _header(today: dt.date, digest: Digest) -> list[str]:
    return [
        f"# {digest.title}",
        "",
        f"**Date:** {today.isoformat()} (UTC)",
        "",
        f"> Automated digest generated from {digest.source_description}.",
        "",
    ]


def _footer(digest: Digest) -> list[str]:
    return sources_footer(digest) + [
        f"*Generated automatically on {dt.datetime.now(dt.timezone.utc).isoformat()} "
        "by the daily GitHub Actions workflow.*",
        "",
    ]


def build_markdown(today: dt.date, digest: Digest, new_items: list[dict]) -> str:
    """Render the digest for ``today`` from items not seen in earlier digests.

    When ``new_items`` is empty every relevant feed item has already been
    published, so a short "no news" digest is produced for the day.
    """
    lines = _header(today, digest)

    if not new_items:
        lines += [
            "## No News Today",
            "",
            f"There is no new Microsoft Foundry news for {today.isoformat()}. "
            f"Every relevant item currently available from {digest.source_description} has "
            "already been covered in a previous daily digest.",
            "",
        ]
        return "\n".join(lines + _footer(digest))

    summary = agent_summary(new_items, digest)
    if summary:
        lines += ["## Executive Summary", "", summary, ""]

    explain_items(new_items)
    agent_name = news_agent_name()

    lines += ["## Headlines", ""]
    for it in new_items:
        date_str = it["published"].date().isoformat() if it["published"] else "n/a"
        lines.append(f"### [{it['title']}]({it['link']})")
        lines.append("")
        lines.append(f"*{date_str} — {it['source']}*")
        lines.append("")
        lines.append(f"**Agent explanation ({agent_name}):**")
        lines.append("")
        lines.append(it["explanation"])
        lines.append("")

    return "\n".join(lines + _footer(digest))


def main() -> int:
    today = dt.datetime.now(dt.timezone.utc).date()
    generated_files: dict[str, str] = {}
    has_news: dict[str, bool] = {}

    for digest in DIGESTS:
        items = gather_items(digest)
        already = published_links(today, digest)
        new_items = select_new_items(today, items, already)
        markdown = build_markdown(today, digest, new_items)
        out_name = filename_for(digest, today)
        with open(out_name, "w", encoding="utf-8") as fh:
            fh.write(markdown)
        generated_files[digest.file_prefix] = out_name
        has_news[digest.file_prefix] = bool(new_items)
        print(f"Wrote {out_name} ({len(markdown)} chars; {len(items)} gathered, "
              f"{len(already)} previously published, {len(new_items)} new)")

    # Expose results to later workflow steps.
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write(f"date={today.isoformat()}\n")
            fh.write(f"has_news={'true' if any(has_news.values()) else 'false'}\n")
            fh.write(f"files={' '.join(generated_files.values())}\n")
            for digest in DIGESTS:
                key = digest.file_prefix.replace("-", "_")
                fh.write(f"{key}_file={generated_files[digest.file_prefix]}\n")
                fh.write(f"{key}_has_news={'true' if has_news[digest.file_prefix] else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
