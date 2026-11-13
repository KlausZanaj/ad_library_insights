---
name: weekly-competitor-report
metadata:
  version: "1.0.0"
  category: AdvertisingResearch
description: >-
  Recurring competitor ad report built from the public Meta Ad Library. Use
  when someone wants a weekly (or other regular) summary of what a fixed list
  of competitors or keywords is advertising in a given country: new ads since
  the last report, ads that stopped, the longest-running ads and shifts in
  messaging. Needs the Ad Library Insights MCP server (export_report,
  search_ads, analyze_top_ads) and a folder where past reports are kept. Skip
  for a one-off look at a market (use ad-library-research) and for reporting
  on the user's own campaign results.
---

# Weekly Competitor Report

Produces the same report every period so that changes stand out. The value is
in the comparison with the previous run, so the watchlist and the output
folder stay fixed between runs.

## Setup (first run only)

Agree on a watchlist with the user and save it as `watchlist.md` in the
report folder:

-   **Country**: one ISO code per report.
-   **Competitors**: up to about eight advertiser names, as they appear on
    their page.
-   **Keywords**: two or three category terms in the language of the market,
    to catch advertisers not yet on the list.
-   **Report folder**: where exports and reports accumulate.

## Workflow

1.  **Load the watchlist** from the report folder. If it is missing, run the
    setup above. Do not guess competitors.

2.  **Export this week's data.** For each competitor call `export_report`
    with `advertiser` set and `formats` `["csv"]`; for each keyword call it
    with `query` set. Use `output_dir` = `<report folder>/<YYYY-MM-DD>/`.
    The server spaces requests out; a full watchlist can take several
    minutes. If a search returns `blocked`, note it in the report and move
    on rather than retrying in a loop.

3.  **Compare with the previous run.** Find the most recent earlier dated
    folder and match rows on `library_id` for the same search:

    | Bucket | Definition |
    |---|---|
    | New | In this week's CSV, not in the previous one, `started` within the period |
    | Stopped | In the previous CSV, missing now |
    | Still running | In both; report the ones with the highest `longevity_score` |

    A missing row is only evidence that an ad stopped. The page shows a
    sample, so confirm notable disappearances by opening the ad link.

4.  **Read the new ads.** Call `analyze_top_ads` for competitors with new
    ads and note what changed: new hook type, new offer, new landing domain,
    a switch between selling and lead capture.

5.  **Write the report** following the
    [template](references/report-template.md) and save it as
    `<report folder>/<YYYY-MM-DD>/report.md`.

6.  **First run.** With no previous folder there is nothing to compare:
    deliver the baseline (longest-running ads and copy patterns) and say that
    changes will appear from the next run.

## Rules

-   Keep the watchlist stable. Record any change to it in the report, because
    it breaks comparability.
-   Report counts with their sample caveat: "at least N new ads seen".
-   No spend or performance claims about competitors; the library does not
    publish them for commercial ads.
-   Keep the report to one page. Link to the CSVs for detail.
