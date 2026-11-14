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
| **Company analysis** | Finds the advertiser's page from its name, loads every active ad of that page and summarises how the company advertises: formats, launch pace, languages, buttons, destinations, repeated copy. |
| **Reach and audience** | For the top-ranked ads, reads the detail view: reach (EU total, the researched country, UK), age, gender and the locations the advertiser targeted or excluded. |
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

### Open the app

On Windows, double-click `avvia.bat`. The first time it creates the virtual
environment and installs everything; after that it opens the app in your
browser. On any system, with the environment active:

```bash
ad-library-insights app
```

The app runs on your computer only (`127.0.0.1`). Choose a mode, a country and
a level. The modes are: search by keyword, analyse a company, compare two
companies, and what changed since the previous search.

| Level | What you get | What it uses |
|---|---|---|
| **Data** | Ranking, days running, reach and audience, company signals. | Nothing: plain code, no AI. |
| **Analysis** | The same data, plus a ready text for your own assistant to explain why the company gets those results. | Your assistant's limits. |
| **Plan** | The analysis plus ad ideas, a test plan and a report for your own product. Asks once for your project (product, price, cost, market, goal, main problem). | More of your assistant's limits. |

**Compare two companies** loads both pages and lines them up on the same
numbers: active ads, launch pace, formats, copy, reach and audience, platforms,
buttons and destinations, with the differences worth noting written out. It
names no winner, because the Ad Library shows no spend and no sales.

Every search is saved on your computer. From the second search of the same
company or keyword, the **What changed** tab lists new ads, ads no longer
listed, and ads whose copy, headline, button, destination or offer changed.

No model is called by the app. Before an Analysis or Plan search it shows what
will be sent (ads, video stills) and an estimate of the size, labelled low,
medium or high. It is an estimate: limits depend on your plan and model.

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
| `competitor-analysis` | The Analysis level: explain why a company gets its reach, through copy, creative, reach and audience, testing and destinations. |
| `competitor-plan` | The Plan level: diagnosis of your project, five ad ideas, a test plan built on break-even CPA, and a one-page report. |

### Analysis and Plan with your own assistant

The program never calls a model. For these two levels it writes the data and
you choose who reads it:

- **Any assistant, one pass.** In the app, "Prepare analysis" or "Prepare
  plan" composes one text with role, method, rules of evidence and the data
  inside. Paste it into the assistant you use.
- **Claude Code, with specialists.** The same data is saved as a pack: one
  file per specialist (`copy.md`, `creative.md`, `reach.md`, `testing.md`,
  plus `project.md` for a plan). The four sub-agents in `.claude/agents/`
  each read only their slice; the two skills above coordinate them and join
  the findings. Open this repository in Claude Code so the agents are found,
  and install the skills as described above.

You pick how many ads are analysed (10, 20, 50) and whether video stills are
included, both before the search and again when the text is prepared, and the
app shows an estimate of the size each time. A plan needs your project card:
product, price, product cost, market, goal and main problem, asked once and
kept on your computer.

## Usage

### From an MCP client

Ask in plain language; the client picks the tools.

> Search the Ad Library in DE for "standing desk", show me the ten
> longest-running ads and break down how their copy is structured.

> Export a report for advertiser "Northwind" in US to the folder `reports`.

| Tool | Purpose |
|---|---|
| `search_ads(country, query, advertiser, ..., deep_ads)` | Ranked ads for a keyword and/or advertiser name. `deep_ads` adds reach and audience for that many top ads. |
| `find_advertiser_pages(name, country)` | The pages the library suggests for a name, with followers and category. |
| `analyze_company(country, page_id \| name, deep_ads, frames)` | Every active ad of one page, ranked, with company signals, reach and audience. |
| `what_changed(country, query \| page_id)` | New, stopped and changed ads since the previous search of the same keyword or page. |
| `compare_companies(country, page_id_a, page_id_b, deep_ads)` | Two pages side by side on the same numbers, with the notable differences. |
| `estimate_consumption(level, ads, frames)` | Rough size of an Analysis or Plan, to confirm before collecting. |
| `prepare_analysis(country, level, page_id \| query, ads, frames)` | Collects the data and writes the pack: one brief and one file per specialist. |
| `get_project()` / `save_project(...)` | The project card the Plan level is written for. |
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
ad-library-insights pages --country US --name "Northwind"
ad-library-insights company --country US --page-id 123456789012345 --deep 20 --out reports
ad-library-insights breakeven --price 60 --product-cost 20 --shipping-cost 5 --fee-pct 3 --csv export.csv
```

`pages` lists the advertiser pages matching a name; `company` analyses one of them.
When a name matches several pages, `company --name` stops and lists them so you can
pick the right `--page-id`. `--deep` is the number of top-ranked ads whose reach and
audience are read (about three seconds each; progress and time left are printed).

The `examples/` folder contains a report produced by a live run.

## How it works

1. **Render.** Playwright opens the public Ad Library URL in headless Chromium
   with the interface pinned to English, waits for the first ad, and scrolls
   until no new ads load or `scroll_rounds` is reached.
2. **Read.** The ads are taken from the data the page itself loads: the first
   batch embedded in the HTML, the next ones as the list scrolls. It carries
   text, button, destination, format, platforms, start date and how many ads
   share the creative. The list is ordered by total impressions, highest first.
3. **Fallback.** If that data is missing, the visible cards are parsed instead.
   Class names are obfuscated, so cards are found by content: each card is the
   largest element containing exactly one `Library ID:` label, and its links
   separate body copy from the link preview.
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
7. **Reach and audience.** For the top-ranked ads only, the detail view is
   opened and the transparency data it loads is read: one ad at a time, about a
   second apart, slower when answers get slow, with retries, and stopping early
   if the page keeps refusing. Thumbnails and page logos of those ads are saved
   locally, because their addresses expire.
8. **Signals.** Plain code computes reach per day, audience breadth, format mix,
   new ads per week, ads started in the last 30 days, languages, most used
   buttons and destinations, repeated copy, and a "needs review" flag for ads
   that ran long on a single use of their copy and reached far fewer people per
   day than the advertiser's other ads. The longevity score is not affected.

Cache, throttle state, saved pictures and saved searches live in `~/.ad_library_insights`
(override with the `AD_LIBRARY_INSIGHTS_HOME` environment variable).

## Technical limits

- **No spend or conversion data.** The Ad Library does not publish them for
  commercial ads. The longevity score is a proxy for what an advertiser keeps
  paying for, not a measure of profit.
- **Reach exists only for the EU and the UK.** Meta publishes reach and
  audience for ads delivered in the European Union or the United Kingdom. Ads
  shown only elsewhere have no such section, and the tool says so. Reach is
  per ad; summed over ads it counts the same person more than once.
- **It reads a web page, not an API.** A change in the page layout or wording
  can break parsing until the parser is updated. The page may also refuse
  automated sessions; the tool then retries, and reports `blocked` instead of
  pretending there are no ads. It does not try to evade detection.
- **Results are a sample.** A search returns the ads loaded by scrolling
  (typically 50 to 150), not every ad the library counts. Recent ads are
  listed first.
- **Company analysis needs the right page.** Several pages can share a name;
  the tool lists them and you choose. A brand that advertises from more than
  one page has to be analysed page by page.
- **Start dates reset on edits.** An advertiser who edits an ad gets a new
  start date; scores for frequently edited ads are understated.
- **The copy breakdown is heuristic.** It labels sentences by rules, not by
  understanding. Expect wrong labels on unusual copy and on languages outside
  the phrase list; treat it as a first pass.
- **Dynamic ads show one variation.** Ads marked as having multiple versions
  expose only one text and one creative.
- **Speed.** A fresh search takes roughly 10 to 40 seconds, a company with a
  few hundred ads about a minute, and each detail view about three seconds.
- **Language detection is a guess** from common words and writing systems;
  short texts are left unlabelled.

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
