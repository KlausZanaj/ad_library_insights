---
name: competitor-analysis
metadata:
  version: "1.0.0"
  category: AdvertisingResearch
description: >-
  Explains why a competitor gets the reach it gets on Meta, from its own ads:
  copy, creative, reach and audience, testing and destinations. Use when
  someone asks why a company's ads work, what its ads have in common, or wants
  the Analysis level of Ad Library Insights. Needs the Ad Library Insights MCP
  server (estimate_consumption, prepare_analysis, find_advertiser_pages). Runs
  four specialist sub-agents where the client supports them and a single pass
  otherwise. Skip for a plain list of ads (use ad-library-research) and for a
  plan for the user's own product (use competitor-plan).
---

# Competitor Analysis

The program collects the data with plain code. This skill is the reading: four
specialists look at one slice each, then their findings are joined into one
answer backed by evidence. A generic summary is a failed analysis.

## Workflow

1.  **Fix the scope.** One company (preferred) or one keyword, and one
    country. For a company, call `find_advertiser_pages`; if several pages
    share the name, show them and let the user pick. Do not guess the page.

2.  **Show what it will use and get a yes.** Call `estimate_consumption` with
    level `analysis`, the number of ads (10, 20 or 50) and whether video
    stills are wanted. Tell the user the number of ads, the number of
    pictures, the rough size and the band (low, medium, high), and that it is
    an estimate: limits depend on their plan and model and are not counted in
    credits, so promise no percentage. Offer the cheaper setting (fewer ads,
    no stills). Continue only when they confirm.

3.  **Collect.** Call `prepare_analysis` with level `analysis`. It returns a
    folder with `brief.md` and one data file per specialist. Do not paste the
    files into the conversation; pass the folder path on.

4.  **Read through four lenses.**

    | Lens | Sub-agent | File |
    |---|---|---|
    | Copy | `ad-copy-analyst` | `copy.md` |
    | Creative | `ad-creative-analyst` | `creative.md` and the pictures it lists |
    | Reach and audience | `ad-reach-analyst` | `reach.md` |
    | Testing and destinations | `ad-testing-analyst` | `testing.md` |

    -   **With sub-agents:** start the four in parallel. Give each the pack
        folder and the language to answer in. Each reads `overview.md` and
        its own file only, and returns findings as finding, evidence,
        strength.
    -   **Without sub-agents:** read `brief.md` and follow it. It holds the
        same four passes and the data in one text.

5.  **Join the findings.** Follow the
    [template](references/analysis-template.md). Lead with the answer, then
    the causes ordered by weight. A cause backed by two lenses (the same hook
    in the longest-running copy and in the opening still of the most-reached
    video) outranks one seen through a single lens. Drop findings that
    contradict each other only after saying which evidence is stronger.

6.  **State the limits** as the template asks, then stop. Offer the plan
    (`competitor-plan`) only if the user has a product of their own to apply
    this to.

## Rules

-   Every claim carries a number or a quote from the pack, with the ad id.
-   Meta publishes no spend and no sales. Longevity and copy reuse are clues
    that an ad pays, not proof. Never state returns.
-   Reach exists only for ads delivered in the EU or the UK, per ad. Where it
    is missing, say so and work from copy and dates.
-   If stills were not collected, say that the creative reading rests on
    thumbnails, formats and copy.
-   Do not re-run the search to "check": the pack is the data for this
    analysis. A fresh search is a new, separately confirmed step.
