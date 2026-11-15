---
name: competitor-analysis
metadata:
  version: "1.1.0"
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
specialists look at one slice each, then you join their findings into one
answer backed by evidence. A summary that would fit any advertiser is a failed
analysis.

## Workflow

1.  **Fix the scope.** One company (preferred) or one keyword, and one
    country. For a company, call `find_advertiser_pages`; if several pages
    share the name, show them and let the user pick. Do not guess the page.

2.  **Show what it will use and get a yes.** Call `estimate_consumption` with
    level `analysis`, the number of ads (10, 20 or 50) and whether video
    stills are wanted. That number is how many of the most shown ads are
    opened to read their reach; several of them can belong to one concept, so
    the pack lists that many concepts and says for how many the reach was
    read. With a number too low for the advertiser, fewer than five concepts
    are read and no ad can be called scaling or flagged for review: say so
    and offer the next size. Tell the user the number of ads, the number of
    pictures, the rough size and the band (low, medium, high), and that it is
    an estimate: limits depend on their plan and model and are not counted in
    credits, so promise no percentage. Offer the cheaper setting (fewer ads,
    no stills). Continue only when they confirm.

3.  **Collect.** Call `prepare_analysis` with level `analysis`. It writes a
    pack and returns its folder. Inside: `brief.md`, `overview.md`, one data
    file per specialist, `manifest.json` and, when stills were asked for, the
    pictures in the folder `frames`. Do not paste the files into the
    conversation; pass the folder path on. If the call returns no pack, tell
    the user what it says and stop.

4.  **Read `overview.md` yourself.** It is short. It says how the rating
    works, what each verdict means, the list of ad types, and what limits this
    pack. Three lines change how everything else is read:

    -   `NO REACH IN`: reach in the country searched is not published. The
        analysis then explains what the advertiser runs and for how long, not
        how many people it reaches, and it says so in the answer.
    -   `Reach in`: for how many of the concepts the reach was read.
    -   `do not show the words searched`: a keyword search brought back ads
        that may be off topic.

5.  **Read through four lenses.**

    | Lens | Sub-agent | File | Returns |
    |---|---|---|---|
    | Copy | `ad-copy-analyst` | `copy.md` | findings, and a type per ad from the text |
    | Creative | `ad-creative-analyst` | `creative.md` and the pictures in `frames` | findings, and a type per ad from the pictures |
    | Reach and audience | `ad-reach-analyst` | `reach.md` | findings on scale, audience and localisation |
    | Testing and destinations | `ad-testing-analyst` | `testing.md` | findings on pace, survival and destinations |

    -   **With sub-agents:** start the four in parallel. Give each the pack
        folder and the language to answer in. Each reads `overview.md` and
        its own file only, and returns findings as finding, evidence,
        strength.
    -   **Without sub-agents:** read `brief.md` and follow it. It holds the
        same four passes and the data in one text.

6.  **Join the findings.** Follow the
    [template](references/analysis-template.md).

    -   Lead with the answer, then the causes ordered by weight.
    -   A fact two specialists confirm (the same hook in the copy that holds
        and in the start still of the most reached video) weighs more than
        one seen through a single lens. Next to each cause write which
        lenses confirm it. A fact seen through one lens stays, marked as such.
    -   Give every ad one type. When copy and creative disagree, the picture
        decides if it was looked at; otherwise keep the type from the text
        and mark it "to confirm".
    -   When two findings contradict each other, say which evidence is
        stronger before dropping one.

7.  **Check the answer against the pack before delivering.**

    -   Every number in the answer is written in a file of the pack, with
        the same meaning: people reached in the country searched are not the
        EU total, and a position by impressions is not a number of people.
    -   No conclusion rests on an ad marked `too recent to judge`.
    -   Survival or cut rates appear only if `testing.md` has the table
        under `Survival`. If it says `NOT MEASURABLE`, the answer says that
        it cannot be measured and why.
    -   A count from the table `On air now, by age` is a count of concepts,
        not of ads.
    -   The launch pace is quoted with what it was counted on. When
        `the list was read in part`, say that the real pace is higher.
    -   Anything you inferred is called a hypothesis, with the way to check it.

8.  **State the limits** as the template asks, then stop. Offer the plan
    (`competitor-plan`) only if the user has a product of their own to apply
    this to.

## Rules

-   Every claim carries a number or a quote from the pack, with the ad id.
-   Meta publishes no spend and no sales. Scale and staying power are clues
    that an ad pays, not proof. Never state returns.
-   Reach is people reached in the country searched. Meta publishes it only
    for ads delivered in the EU or the UK. Inside one concept the ads read
    are added up; concepts are never added to each other.
-   An estimate is never written as a figure.
-   If stills were not collected, say that the creative reading rests on
    formats and copy.
-   Do not re-run the search to "check": the pack is the data for this
    analysis. A fresh search is a new, separately confirmed step.
