---
name: ad-library-research
metadata:
  version: "1.0.0"
  category: AdvertisingResearch
description: >-
  Competitor ad research in the public Meta Ad Library for any product,
  advertiser and country. Use when someone asks what ads competitors are
  running, which ads in a market have lasted longest, how winning ads in a
  category are written, or wants angles and hooks for new creatives backed by
  what is live right now. Needs the Ad Library Insights MCP server
  (search_ads, analyze_top_ads, export_report). Skip when the question is
  about the user's own account performance (use breakeven-cpa-check) or about
  spend or ROAS of competitors, which the Ad Library does not publish
  for commercial ads.
---

# Ad Library Research

Finds the ads a market keeps paying for and explains how they are built. The
keyword, the advertiser and the country always come from the user; nothing is
assumed.

## Inputs to collect

Ask only for what is missing:

-   **Country** (required): two-letter ISO code of the market, or `ALL`.
-   **Keyword** and/or **advertiser name**: at least one. A keyword maps a
    category; an advertiser name narrows to one competitor.
-   **Depth** (optional): how many top ads to break down. Default 10.

## Workflow

1.  **Search in the language of the market.** Call `search_ads` with the
    country and the keyword as a local buyer would type it. For a category,
    run two or three keyword variants (product name, problem it solves, a
    generic category term) rather than one broad term. Calls are spaced out
    by the server, so prefer few, well-chosen searches.

2.  **Check the outcome before reading the ads.**

    | `outcome` | Meaning | What to do |
    |---|---|---|
    | `ok` | Ads were parsed | Continue |
    | `no_results` | The library has nothing for this search | Try a broader or translated keyword |
    | `blocked` | The page served no ads after all retries | Tell the user, wait several minutes, do not loop |

3.  **Read the ranking as a media buyer would.** Ads are merged one per
    concept and rated on scale (people reached per day, or the impression
    position where reach is not published), staying power and creative
    investment. Each rating carries a reliability and a plain verdict. Pass
    `deep_ads` to read reach for the top ads: without it every rating is an
    estimate. See [reading the results](references/reading-the-results.md)
    for each field and the traps to avoid.

4.  **Break down the top ads.** Call `analyze_top_ads` with the same
    arguments. It returns hook, promise, proof and CTA per ad plus the shared
    patterns. The breakdown is rule-based: reread the `body` of each top ad
    and correct any label that is wrong before presenting it.

5.  **Report.** Lead with what the user can act on:

    -   the three to five advertisers that dominate the search and how long
        their oldest ad has run;
    -   the recurring hook types, proof devices and CTAs, each with one
        quoted example and its Ad Library link;
    -   two or three angles nobody in the sample is using;
    -   the sample size and the date, and that no spend data exists.

6.  **Export when asked.** `export_report` writes the Markdown brief and a
    CSV with one row per ad to the folder the user names.

## Rules

-   Never present a rating as proof of profit. Say "reaches N people a day
    and has run for N days", not "is profitable". State the reliability.
-   Quote competitor copy only as short excerpts for analysis. Write new
    creatives from the patterns, never by copying an ad.
-   State the keyword, country and date of every search you report on.
