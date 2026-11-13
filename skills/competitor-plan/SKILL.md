---
name: competitor-plan
metadata:
  version: "1.0.0"
  category: AdvertisingStrategy
description: >-
  Turns a competitor's ads into a plan for the user's own product: diagnosis,
  five ad ideas, a test plan with budget and cut rules built on break-even
  CPA, and a one-page report for whoever decides. Use when someone asks what
  to do about a competitor, wants ad ideas grounded in what works, a test
  plan, or the Plan level of Ad Library Insights. Needs the Ad Library
  Insights MCP server (get_project, save_project, estimate_consumption,
  prepare_analysis, check_breakeven_cpa, what_changed). Skip when there is no
  product of the user's to plan for (use competitor-analysis).
---

# Competitor Plan

You coordinate. Think as a head of marketing: diagnose the business first,
then propose, with priorities, a budget and rules for deciding. This is not a
content calendar and not a social media plan.

## Workflow

1.  **Get the project card.** Call `get_project`. If it is empty, ask once
    for: what they sell, selling price, product cost, market (country), goal,
    and main problem (for example high cost per purchase, too few creatives,
    low reach). Save it with `save_project`. Without the card, do not write a
    plan: one more question beats a generic plan.

2.  **Fix the competitor and the scope,** as in `competitor-analysis` step 1.
    Use the market on the card as the country unless told otherwise.

3.  **Show what it will use and get a yes.** Call `estimate_consumption` with
    level `plan`. A plan re-reads the data more times than an analysis, so it
    weighs more: say so, give the band, say it is an estimate and promise no
    percentage. Offer fewer ads or no stills. Continue only on a yes.

4.  **Collect.** Call `prepare_analysis` with level `plan`. The folder holds
    `brief.md`, the four data files and `project.md` with the card and the
    numbers computed from it.

5.  **Read the competitor** through the four lenses, as in
    `competitor-analysis` step 4: four sub-agents in parallel where the
    client has them, `brief.md` in a single pass where it does not. Ask each
    specialist for findings only; you do the planning.

6.  **Diagnose the user's project.** From `project.md`: margin per order,
    break-even CPA, and where customers are most likely lost given the
    problem named. Separate what the numbers show from what you assume, and
    for every assumption say how to check it.

7.  **Write five ad ideas** for the user's product, following the
    [idea format](references/plan-template.md#ad-ideas). Each borrows a
    pattern that holds in the competitor's data, named with the ad id. They
    are not copies: no sentences, brand names or promises of the competitor.
    Each idea tests one thing.

8.  **Build the test plan** on the numbers in `project.md`. Budget per test
    ad and for the first round, how many ads run together, for how many days,
    what to look at each day, the cut rule, when to raise the budget, and
    what to do if nothing holds. For the cut rule follow
    `breakeven-cpa-check`: an ad is cut once it has spent 2 to 3 times
    break-even CPA with no add to cart and no sale. If the user has results
    already, run `check_breakeven_cpa` on them.

9.  **Set up the weekly follow-up.** Use `weekly-competitor-report` for the
    recurring report and `what_changed` to see new, stopped and changed ads
    between searches. Say on which day to run it and what would change the plan.

10. **Deliver** with the [template](references/plan-template.md). The report
    comes first and fits one page; ideas and test plan follow; diagnosis and
    competitor reading go in the appendix. Whoever decides reads page one only.

## Rules

-   Priorities are ordered and at most three. A list of ten is not a priority list.
-   Every number in the plan is either from the pack, from `project.md`, or
    marked as an assumption with the way to check it.
-   The break-even numbers use product cost only. If shipping, payment fees
    or returns are not in that cost, say that the real break-even is lower.
-   Meta publishes no spend and no sales for the competitor. Never state what
    the competitor earns or spends.
-   If the competitor's data is thin (few ads, no reach), say so on page one
    and lower the confidence of the plan instead of filling the gap.
