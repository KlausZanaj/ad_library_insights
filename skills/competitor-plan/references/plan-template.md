# Plan template

Replace every `{placeholder}`. Page one is the report: it must stand on its
own. Everything after it is there to be consulted, not read in order.

Numbers marked "from the project file" are copied from the project file of
the pack as they are written there. Numbers of the competitor are copied from
the pack, with the country they refer to.

```markdown
# {Product}: plan against {competitor}, {country}, {date}

## Decision asked for

{One sentence: what you want approved, with the amount and the period.}

## Three priorities

1. **{Priority.}** {Why now, in one line, with the number behind it.}
2. **{Priority.}** {...}
3. **{Priority.}** {...}

## The numbers behind them

| | |
|---|---:|
| Margin per order (from the project file) | {margin} |
| Break-even CPA (from the project file) | {cpa} |
| Budget, first test round ({n} ads) | up to {round_total} |
| Cut an ad after spending | {cut_low} to {cut_high} with no add to cart, no sale |
| Spend at the level of the goal, at break-even | {daily_max} a day, {weekly_max} a week; or "goal has no number of orders" |
| {Competitor}: active ads / new per week among those still on air | {active} / {new_per_week}, counted on {loaded} ads loaded |
| {Competitor}: people reached per day in {country}, median per concept | {median} over {k} concepts read; or "not published" |

## Risks and what we do not know

- {The assumption the plan leans on most, and how it gets checked.}
- {What the competitor data cannot show: spend, sales; and what was missing in this pack.}

## Next seven days

| Day | What | Who |
|---|---|---|
| {day} | {action} | {You, or the person named; in brackets to whom it can be handed over} |
```

## Check before spending

```markdown
## Check before spending

- **Pixel and Conversions API:** {both active | what is missing}.
- **Purchase event:** {arrives with value and currency | what is missing}.
- **How to verify:** {a test purchase, and where to see it in Events Manager}.
- **If it fails:** {what to fix first}. The plan starts only after this check passes.
```

## Ad ideas

Five ideas. One table row each is not enough; use this block per idea.

```markdown
### Idea {n}: {angle in a few words}

- **Type:** {one of the ad types listed in the overview of the pack}
- **Borrows from:** {the pattern, in one line} (ad {library_id}: {days} days, {creatives} creatives, {people per day in the country | reach not published})
- **Hook:** {first line, or what the first three seconds show}
- **Development:** {point 1} / {point 2} / {point 3}
- **Proof to show:** {review, number, demonstration, guarantee: what exactly}
- **Format:** {video | image | carousel}, {length or number of cards}
- **Button and landing page:** {button} to {page}
- **What it tests:** {one variable: the hook, the offer, the proof, the audience}
```

The amounts of the test plan below ({per_ad}, {round_total}, {cut_low},
{cut_high}, {cpa}) come from the project file. The spend after which an ad is
kept ({threshold}) and the rule for raising the budget are your proposal:
write them as a rule of thumb, with the reason, not as figures of the program.

An idea is not a copy when it keeps the mechanism (a question that names the
problem, a demonstration in the first seconds, a guarantee at the close) and
changes everything specific: words, brand, claims, numbers.

## Campaign structure

```markdown
## Campaign structure

- **Audience:** {broad | narrow}, because {what the competitor does: age range, gender, locations, breadth; or "audience data missing"}.
- **Campaigns and ad sets:** {how many, and what each is for}.
- **Where tests run, where winners go:** {rule}.
```

## Test plan

```markdown
## Test plan

- **Round 1:** {n} ads live together, {days} days, up to {per_ad} each, {round_total} in total.
- **Each day, look at:** spend per ad, add to cart, purchases, cost per purchase against {cpa}.
- **Cut:** an ad that has spent {cut_low} to {cut_high} with no add to cart and no sale.
- **Keep:** an ad with purchases at or below {cpa} per purchase after {threshold} spend.
- **Raise the budget:** {rule, for example +20% every two days while cost per purchase stays under {cpa}}.
- **If nothing holds:** {what changes first: offer, landing page, or audience, and why in that order}.
- **Round 2:** {what the winners of round 1 are varied on}.
- **New creatives per week:** {number}. {Competitor} launches {new_per_week} a week among the ads still on air{, list read in part: the real pace is higher}; the test share at the level of the goal carries {capacity}; one person can keep up {number}. {The calculation.}
```

## Appendix

1. **Diagnosis of the project**: what is sold, to whom, price and margin,
   where customers are lost. What the numbers show; what is assumed and how
   to check it.
2. **Reading of the competitor**: the answer and causes from the analysis
   (see the `competitor-analysis` template), kept to what matters for this product.
3. **Weekly follow-up**: day of the week, watchlist, what would change the plan.
