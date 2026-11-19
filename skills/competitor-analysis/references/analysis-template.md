# Analysis template

Replace every `{placeholder}`. Keep it to about one page; the lens lists are
the appendix, not the message.

```markdown
# Why {company}'s ads reach what they reach: {country}, {date}

Based on the top {n} concepts, from {loaded} ads loaded of {active} active.
Reach in {country}: {read for k of the n concepts | not published}.
Pictures: {looked at for n ads | not collected}.

## The answer

{Two lines. The main reason, in plain words, with the single strongest number.}

## Causes, heaviest first

1. **{What they do.}** {Evidence: number or short quote, ad id.} Strength: {high | medium | low}. Confirmed by: {copy + creative | one lens only: reach}.
2. **{...}** {...} Strength: {...}. Confirmed by: {...}.
3. **{...}** {...} Strength: {...}. Confirmed by: {...}.

## The ads read

| Ad id | Type | People reached in {country} | Per day | Days | What it shows |
|---|---|---:|---:|---:|---|
| {id} | {type} | {total, k of m ads read | not published} | {per day | not published} | {days} | {one line} |

## Through each lens

**Copy**
- {finding} · {evidence, ad id} · {strength}

**Creative**
- {finding} · {evidence, ad id} · {strength}

**Reach and audience**
- {finding} · {evidence, ad id} · {strength}

**Testing and destinations**
- {finding} · {evidence, ad id} · {strength}

## What this data cannot tell

- {No spend, no sales: which ads actually pay is inferred from scale and staying power.}
- {What was missing here: reach in the country, reach for some ads, pictures, a second search to measure survival, a list read in part.}

## To test or verify, in order

1. {The most useful next check, and what result would change the reading.}
2. {...}
3. {...}
```

## Filling the table of ads

- People reached and per day are copied from the pack, for the country
  searched. Where the pack says "not published" or "not known", the cell says
  the same: no EU total and no estimate in its place.
- Days are those of the concept. When the pack gives a second age for the
  most shown ad, write both.
- Type is one of the types listed in the overview of the pack, or "other"
  with three words.

## Strength of a cause

Each specialist gives a strength to its own findings, by the rule written in
its file. When you join them into causes:

| Strength | When |
|---|---|
| High | One lens rates the finding high and a second lens confirms it |
| Medium | One lens rates it high and no other confirms it; or two lenses rate it medium |
| Low | Everything else: one lens at medium or low, or an inference with no direct number |

Where the reach in the country searched is not published, no cause is High:
the ratings behind it are of medium reliability at best.
If two lenses contradict each other on the same core ad id and at most one
neutral re-check does not resolve it, cap the cause at Medium (or Low without
reach) and put the open clash at the top of "To test or verify, in order".
