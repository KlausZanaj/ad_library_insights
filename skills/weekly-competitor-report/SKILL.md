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
  messaging. Needs the Ad Library Insights MCP server (analyze_company,
  search_ads, what_changed, analyze_top_ads, export_report) and a folder where
  past reports are kept. Skip
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

2.  **Search again, fresh.** For each competitor call `analyze_company`
    with its `page_id` (find it once with `find_advertiser_pages` and keep it
    in the watchlist) and `use_cache` false; for each keyword call
    `search_ads` with `query` and `use_cache` false. Every search is saved on
    the machine. To keep files too, call `export_report` with `output_dir` =
    `<report folder>/<YYYY-MM-DD>/`. The server spaces requests out; a full
    watchlist can take several minutes. If a search returns `blocked`, note
    it in the report and move on rather than retrying in a loop.

3.  **Compare with the previous run.** Call `what_changed` with the same
    `page_id` or `query` and country: it returns new ads, ads no longer
    listed, ads whose copy, headline, button, destination or offer changed
    since the previous saved search, and—for `page_id` company searches with
    at least two snapshots—`ritmo` (`sta_lta` 1w vs 8w launch pace, `cusum`
    format drift, `littles_law` `L = λW` balance, and `trigger_ai`). Where
    only exported CSVs exist, match rows on `library_id` instead. The buckets:

    | Bucket | Definition |
    |---|---|
    | New | In this week's CSV, not in the previous one, `started` within the period |
    | Stopped | In the previous CSV, missing now |
    | Still running | In both; report the ones with the highest `score` and their verdict |

    A missing row is only evidence that an ad stopped. The page shows a
    sample, so confirm notable disappearances by opening the ad link.

4.  **Read the new ads (peak-gated).** Inspect new ads in depth with
    `analyze_top_ads` primarily when `ritmo.trigger_ai` is true (a real
    STA/LTA launch spike or CUSUM format drift) or when notable copy/offer
    edits appear, citing example ad IDs and noting what changed (hook type,
    offer, landing domain, selling vs lead capture). Keep steady competitors
    where `ritmo.status` is steady to a brief status line.

5.  **Write the report** following the
    [template](references/report-template.md) and save it as
    `<report folder>/<YYYY-MM-DD>/report.md`, including the
    **Pace and format shifts (Ritmo)** table.

6.  **First run.** With no previous search there is nothing to compare:
    deliver the baseline (longest-running ads and copy patterns) and say that
    changes will appear from the next run.

## Rules

-   Keep the watchlist stable. Record any change to it in the report, because
    it breaks comparability.
-   Report counts with their sample caveat: "at least N new ads seen".
-   Include one plausible alternative explanation (seasonal drop, batch
    upload, short testing sprint) for any launch spike or format shift in Ritmo;
    mention active-only survivor bias when snapshot history spans fewer than
    three weeks.
-   No spend or performance claims about competitors; the library does not
    publish them for commercial ads.
-   Keep the report to one page. Link to the CSVs for detail.
