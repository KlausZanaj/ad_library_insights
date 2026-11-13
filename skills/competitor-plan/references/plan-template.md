# Plan template

Replace every `{placeholder}`. Page one is the report: it must stand on its
own. Everything after it is there to be consulted, not read in order.

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
| Margin per order | {margin} |
| Break-even CPA | {cpa} |
| Budget, first test round ({n} ads) | up to {round_total} |
| Cut an ad after spending | {cut_low} to {cut_high} with no add to cart, no sale |
| {Competitor}: active ads / new per week | {active} / {new_per_week} |
| {Competitor}: median reach per day (EU and UK ads read) | {reach_per_day} |

## Risks and what we do not know

- {The assumption the plan leans on most, and how it gets checked.}
- {What the competitor data cannot show: spend, sales.}

## Next seven days

| Day | What | Who |
|---|---|---|
| {day} | {action} | {owner} |
```

## Ad ideas

Five ideas. One table row each is not enough; use this block per idea.

```markdown
### Idea {n}: {angle in a few words}

- **Borrows from:** {the pattern, in one line} (ad {library_id}, {days} days, copy used {n} times)
- **Hook:** {first line, or what the first three seconds show}
- **Development:** {point 1} / {point 2} / {point 3}
- **Proof to show:** {review, number, demonstration, guarantee: what exactly}
- **Format:** {video | image | carousel}, {length or number of cards}
- **Button and landing page:** {button} to {page}
- **What it tests:** {one variable: the hook, the offer, the proof, the audience}
```

An idea is not a copy when it keeps the mechanism (a question that names the
problem, a demonstration in the first seconds, a guarantee at the close) and
changes everything specific: words, brand, claims, numbers.

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
```

## Appendix

1. **Diagnosis of the project**: what is sold, to whom, price and margin,
   where customers are lost. What the numbers show; what is assumed and how
   to check it.
2. **Reading of the competitor**: the answer and causes from the analysis
   (see the `competitor-analysis` template), kept to what matters for this product.
3. **Weekly follow-up**: day of the week, watchlist, what would change the plan.
