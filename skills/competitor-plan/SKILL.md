---
name: competitor-plan
metadata:
  version: "1.1.0"
  category: AdvertisingStrategy
description: >-
  Turns a competitor's ads into a plan for the user's own product: diagnosis,
  a tracking check, five ad ideas, a campaign structure, a test plan with
  budget and cut rules built on break-even CPA, and a one-page report for
  whoever decides. Use when someone asks what to do about a competitor, wants
  ad ideas grounded in what works, a test plan, or the Plan level of Ad
  Library Insights. Needs the Ad Library Insights MCP server (get_project,
  save_project, estimate_consumption, prepare_analysis, check_breakeven_cpa,
  what_changed). Skip when there is no product of the user's to plan for (use
  competitor-analysis).
---

# Competitor Plan

You coordinate. Think as a head of marketing: diagnose the business first,
then propose, with priorities, a budget and rules for deciding. The plan fits
the means of the person who has to carry it out.

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
    `brief.md`, `overview.md`, the four data files, the pictures in `frames`
    when stills were asked for, and `project.md` with the card and the numbers
    computed from it.

5.  **Read the competitor** as in `competitor-analysis` steps 4 to 7: read
    `overview.md` yourself, then four sub-agents in parallel where the client
    has them, `brief.md` in a single pass where it does not. Ask each
    specialist for findings only; you do the planning. Keep what matters for
    this product and mark what two lenses confirm.

6.  **Diagnose the user's project.** From `project.md`: margin per order,
    break-even CPA, and where customers are most likely lost given the
    problem named. Separate what the numbers show from what you assume, and
    for every assumption say how to check it.

7.  **Check before spending.** Before any budget goes out, tracking must
    work: the pixel and the Conversions API are both active, and the purchase
    event arrives with value and currency. Say how to verify it with a test
    purchase in Events Manager and what to fix if it does not. Without this
    check the plan does not start.

8.  **Write five ad ideas** for the user's product, following the
    [idea format](references/plan-template.md#ad-ideas). Each borrows a
    pattern that holds in the competitor's data, named with the ad id and its
    numbers, and has a type from the list in the overview. They are not
    copies: no sentences, brand names or promises of the competitor. Each idea
    tests one thing.

9.  **Propose the campaign structure.** Broad or narrow audience, in line
    with what `reach.md` shows the competitor does (age range, gender,
    locations, breadth). How many campaigns and ad sets, where tests run and
    where winners go. Give the reason from the data; if the audience data is
    missing, say so and propose the simplest structure.

10. **Build the test plan and the creative pace** on the numbers under
    `Numbers for the test` in `project.md`. Use them as they are: the program
    computed them, and a number you recompute can differ.

    -   Budget per test ad and for the first round, how many ads run
        together, for how many days, what to look at each day, the cut rule,
        when to raise the budget, and what to do if nothing holds.
    -   The cut rule is the one of `breakeven-cpa-check`: an ad is cut once
        it has spent 2 to 3 times break-even CPA with no add to cart and no
        sale. If the user has results already, run `check_breakeven_cpa` on
        them.
    -   New creatives per week: start from the pace of the competitor and
        from what the test budget can carry. Both are in `project.md` when
        the goal names a number of orders; show the calculation and give a
        number one person can keep up. For a keyword search the pace sums all
        advertisers found and must not be used to size production. If the file
        says the list of the competitor was read in part, its real pace is
        higher: say so. If it says no number of orders can be read from the
        goal, ask for it.

11. **Set up the weekly follow-up.** Use `weekly-competitor-report` for the
    recurring report and `what_changed` to see new, stopped and changed ads
    between searches. A second search of the same company makes survival
    measurable when both lists were read in full. Use relative days (Day 1 to
    Day 7 after tracking is verified) rather than a fixed calendar start date
    before the budget is approved, and if the search falls in a peak retail
    window such as Black Friday or late November, flag the higher auction
    competition among the risks. Say on which day of the cycle to run the
    follow-up and what would change the plan.

12. **Deliver** with the [template](references/plan-template.md). The report
    comes first and fits one page; the check before spending, the ideas, the
    campaign structure and the test plan follow; diagnosis and competitor
    reading go in the appendix. Whoever decides reads page one only. In the
    table of the next seven days the column Who says "You" unless the user
    named who works with them; where handing over makes sense, add to whom in
    brackets.

## Rules

-   Priorities are ordered and at most three. A list of ten is not a priority list.
-   Every number in the plan is either from the pack, from `project.md`, or
    marked as an assumption with the way to check it.
-   The break-even numbers use product cost only. If VAT, shipping, payment
    fees or returns are not in that cost, say that the real break-even is
    lower and ask for the values.
-   Meta publishes no spend and no sales for the competitor. Never state what
    the competitor earns or spends.
-   When what the competitor sells is bought in another way than the user's
    product (a free install against a paid order, say), write under the risks
    what does not carry over, and test it instead of assuming it.
-   Each idea changes one thing against another idea of the same round, and
    says which. A first round at a few times break-even CPA per ad can drop
    the worst ads; it cannot name a winner: say so.
-   Where the pack says `NO REACH IN`, the plan borrows what the competitor
    runs and for how long, and says that its reach in that country is not
    published.
-   If the competitor's data is thin (few ads, no reach, a list read in
    part), say so on page one and lower the confidence of the plan instead of
    filling the gap.
