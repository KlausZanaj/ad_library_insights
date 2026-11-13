---
name: breakeven-cpa-check
metadata:
  version: "1.0.0"
  category: AdvertisingOperations
description: >-
  Break-even CPA calculation and a kill rule for paid social ads in
  e-commerce. Use when someone asks which ads to turn off, whether an ad has
  had a fair test, what their break-even CPA or break-even ROAS is, or shares
  an Ads Manager export with spend, add to cart and purchases. Flags every ad
  that has spent 2-3 times the break-even CPA with no add to cart and no
  purchase. Works from numbers the user provides; uses the check_breakeven_cpa
  tool of the Ad Library Insights MCP server when available and plain
  arithmetic otherwise. Skip for lead-generation accounts with no order value,
  and for questions about competitors' ads (use ad-library-research).
---

# Break-even CPA Check

Decides, ad by ad, whether to cut, watch or keep, using one threshold derived
from the product's own margin instead of a gut feeling.

## Inputs to collect

1.  **Unit economics of one order**: selling price, product cost, shipping
    cost paid by the seller, payment fee (percent and fixed), any other
    per-order cost. Use the average order when several products are sold.
2.  **Multiplier**: how many times the break-even CPA an ad may spend with no
    signal before it is cut. Default 2.5. Use 2 for small budgets or cheap
    products, 3 for expensive products with a longer decision time.
3.  **Ad results**: for each ad (or ad set) the amount spent, adds to cart and
    purchases, over the same period. A CSV export from Ads Manager works as
    is; English and Italian column names are recognised.

If a number is missing, ask for it. Never estimate costs on the user's behalf.

## Workflow

1.  **Compute the break-even CPA.** Call `check_breakeven_cpa` with the unit
    economics, or apply the formula in [formulas](references/formulas.md).
    Show the calculation line by line so the user can correct an input.

2.  **Stop if the margin is not positive.** A product that loses money before
    ad spend cannot be fixed by cutting ads. Say so and stop.

3.  **Judge every ad.** Pass the rows as `ads`, or the export as `csv_path`.
    Each ad gets one verdict:

    | Verdict | Condition | Action |
    |---|---|---|
    | `cut` | Spend at or above multiplier x break-even CPA, 0 add to cart, 0 purchases | Turn it off |
    | `review` | Same spend with add to carts but no purchase, or purchases at a CPA above break-even | Look at the product page, checkout and price before spending more |
    | `watch` | Spend between 1x and the threshold, no purchase yet | Leave it running until it reaches the threshold |
    | `wait` | Spend below 1x break-even CPA | Too early to judge |
    | `keep` | Purchases at a CPA at or below break-even | Keep; candidate for more budget |

4.  **Report.** Start with the break-even CPA and the cut threshold in
    currency. Then list the ads to cut with their spend, followed by the
    `review` group with the specific thing to check. End with the total spend
    that the cuts stop.

## Rules

-   Never switch ads off yourself. This skill recommends; the user acts in
    their ad account.
-   Compare ads over the same date range and attribution setting.
-   The rule covers ads with **no** signal. An ad with purchases is judged on
    its CPA, not on the multiplier.
-   Say which multiplier was used. If the user asks for a different one,
    rerun rather than adjusting verdicts by hand.
