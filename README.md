# Ad Library Insights

An MCP server and command-line tool that turns the public Meta Ad Library into
ranked, structured competitor research: which ads a market keeps running, how
their copy is built, and a report you can hand to someone else.

It works for any product, advertiser and country. Keyword, advertiser name and
country are always parameters; nothing about a specific industry is built in.

## What it does

| Capability | Detail |
|---|---|
| **Search** | Renders the public Ad Library in headless Chromium for a keyword and/or advertiser in a given country. No account, token or API key. |
| **Longevity score** | Ranks ads 0-100 by days running and by how many ads reuse the same copy, the two persistence signals the library exposes. |
| **Reliable fetching** | Local disk cache, retries with growing pauses, and a request throttle, with a clear distinction between "no results" and "the page did not serve ads". |
| **Copy breakdown** | Splits the best ads into hook, promise, proof and call to action, as structured output, and summarises the patterns they share. |
| **Reports** | Exports a Markdown brief and a CSV with one row per ad. |
| **Break-even CPA check** | Computes break-even CPA from unit economics and flags ads that spent 2-3x that amount with no add to cart and no purchase. |
| **Skills for Claude** | Three ready-made skills that drive the tools: market research, break-even check, weekly competitor report. |

## Installation

Requires Python 3.10 or newer.

**Windows (PowerShell)**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m playwright install chromium
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m playwright install chromium
```

If PowerShell refuses to run the activation script, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or skip activation
and call `.venv\Scripts\python.exe` directly.

### Connect it to an MCP client

Point the client at the Python interpreter of the virtual environment.

Claude Code:

```bash
claude mcp add ad-library-insights -- /absolute/path/.venv/bin/python -m ad_library_insights
```

On Windows the interpreter is `C:\absolute\path\.venv\Scripts\python.exe`.

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ad-library-insights": {
      "command": "C:\\absolute\\path\\.venv\\Scripts\\python.exe",
      "args": ["-m", "ad_library_insights"]
    }
  }
}
```

### Install the skills (optional)

Copy the folders inside `skills/` to `~/.claude/skills/` (all projects) or to
`.claude/skills/` in a project. Each folder holds a `SKILL.md` and its
reference files.

| Skill | Use it to |
|---|---|
| `ad-library-research` | Map a market or a competitor and explain how the longest-running ads are written. |
| `breakeven-cpa-check` | Decide which of your own ads to cut, from your margin and an Ads Manager export. |
| `weekly-competitor-report` | Track a fixed watchlist and report what is new, what stopped and what changed. |

## Usage

### From an MCP client

Ask in plain language; the client picks the tools.

> Search the Ad Library in DE for "standing desk", show me the ten
> longest-running ads and break down how their copy is structured.

> Export a report for advertiser "Northwind" in US to the folder `reports`.

| Tool | Purpose |
|---|---|
| `search_ads(country, query, advertiser, ...)` | Ranked ads for a keyword and/or advertiser name. |
| `scrape_library_url(url, ...)` | Same, for an Ad Library URL you already filtered by hand. |
| `analyze_top_ads(country, query, advertiser, top_n)` | Hook, promise, proof and CTA of the top ads, plus shared patterns. |
| `export_report(country, output_dir, query, advertiser, top_n, formats)` | Writes the Markdown brief and/or the CSV. |
| `check_breakeven_cpa(price, product_cost, ..., multiplier, ads \| csv_path)` | Break-even CPA and the list of ads to cut. |

One ranked ad looks like this:

```json
{
  "library_id": "1001",
  "ad_url": "https://www.facebook.com/ads/library/?id=1001",
  "advertiser": "Northwind Desks",
  "status": "active",
  "started": "2026-01-05",
  "days_running": 90,
  "repetitions": 2,
  "creative_variants": 2,
  "longevity_score": 72.0,
  "body": "Still working hunched over a laptop?\nRaise your desk in 3 seconds. ...",
  "headline": "Sit-stand desk, oak top",
  "cta": "Shop Now",
  "landing_domain": "northwind.example",
  "media_type": "image"
}
```

And its copy breakdown:

```json
{
  "hook": { "text": "Still working hunched over a laptop?", "type": "question" },
  "promise": { "text": "Raise your desk in 3 seconds." },
  "proof": [{ "text": "Rated 4.8/5 by 12,000 customers.", "kinds": ["statistic", "reviews"] }],
  "cta": { "button": "Shop Now", "kind": "purchase",
           "closing_line": "Order today with free shipping", "urgency": true },
  "structure": "hook:question > promise > proof > cta"
}
```

### From the command line

```bash
ad-library-insights report --country DE --query "standing desk" --top 10 --out reports
ad-library-insights report --country US --advertiser "Northwind" --out reports
ad-library-insights breakeven --price 60 --product-cost 20 --shipping-cost 5 --fee-pct 3 --csv export.csv
```

The `examples/` folder contains a report produced by a live run.

## How it works

1. **Render.** Playwright opens the public Ad Library URL in headless Chromium
   with the interface pinned to English, waits for the first ad, and scrolls
   until no new ads load or `scroll_rounds` is reached.
2. **Snapshot.** Class names on the page are obfuscated, so cards are found by
   content: each card is the largest element containing exactly one
   `Library ID:` label. Text, links and media of every card are captured.
3. **Parse.** The card's links separate body copy from the link preview
   (headline, description, button), which keeps the split independent of the
   language of the ad.
4. **Fetch policy.** Results are cached on disk for six hours. Renders are at
   least 20 seconds apart and at most 30 per hour. A page with no ads and no
   "no results" statement is retried twice, after about 20 and 60 seconds,
   with a longer wait each time. Empty pages are never cached.
5. **Score.** `score = 100 x (0.6 x min(days / 90, 1) + 0.4 x min(log(repetitions) / log(10), 1))`.
   Ads from one advertiser with identical copy are merged and their counters
   summed. Weights and caps are function parameters.
6. **Copy breakdown.** Rules based on position, punctuation, digits and a
   small phrase list in English, Italian, Spanish, French and German
   (`src/ad_library_insights/data/lexicon.json`, editable).

Cache and throttle state live in `~/.ad_library_insights`
(override with the `AD_LIBRARY_INSIGHTS_HOME` environment variable).

## Technical limits

- **No spend, reach or conversion data.** The Ad Library does not publish
  them for commercial ads. The longevity score is a proxy for what an
  advertiser keeps paying for, not a measure of profit.
- **It reads a web page, not an API.** A change in the page layout or wording
  can break parsing until the parser is updated. The page may also refuse
  automated sessions; the tool then retries, and reports `blocked` instead of
  pretending there are no ads. It does not try to evade detection.
- **Results are a sample.** A search returns the ads loaded by scrolling
  (typically 50 to 150), not every ad the library counts. Recent ads are
  listed first.
- **Keyword search only.** Advertiser lookups search the name as a keyword and
  filter by advertiser name, so an advertiser whose ads are not returned for
  that term is missed. The per-page "all ads" view is not supported.
- **Start dates reset on edits.** An advertiser who edits an ad gets a new
  start date; scores for frequently edited ads are understated.
- **The copy breakdown is heuristic.** It labels sentences by rules, not by
  understanding. Expect wrong labels on unusual copy and on languages outside
  the phrase list; treat it as a first pass.
- **Dynamic ads show one variation.** Ads marked as having multiple versions
  expose only one text and one creative.
- **Speed.** A fresh search takes roughly 10 to 40 seconds, more when the
  throttle or a retry adds a pause.
- **Platform list and media details are not extracted**; media type is
  inferred from the card (video, carousel, image, text).

Use it for research on publicly displayed ads, at a modest request rate, and
in line with the terms of the site you are reading.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest
```

The suite runs offline: the browser is replaced by a scripted renderer, and
time by a fake clock, so cache, throttle and retry behaviour are tested
deterministically.

## License

MIT. See [LICENSE](LICENSE).
