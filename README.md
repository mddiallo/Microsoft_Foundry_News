# Microsoft_Foundry_News

Daily Microsoft Foundry news automation.

The GitHub Actions workflow runs every day at 08:00 UTC and writes two Markdown
digests:

- `microsoft-foundry-news-YYYY-MM-DD.md` for Microsoft-owned websites.
- `external-foundry-news-YYYY-MM-DD.md` for non-Microsoft websites.

Each digest filters RSS feed items for Microsoft Foundry relevance, skips links
that already appeared in earlier digests, and writes a no-news marker when there
are no new items. When GitHub Models access is available, each headline includes
an explanation from the `Microsoft Foundry News Explainer` agent.

Run the generator manually with:

```bash
python scripts/generate_foundry_news.py
```
