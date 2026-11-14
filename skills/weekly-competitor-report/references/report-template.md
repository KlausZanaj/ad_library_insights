# Report template

Replace every `{placeholder}`. Remove a section only if it is empty, and say
so in the summary.

```markdown
# Competitor ads: {country}, week ending {YYYY-MM-DD}

Watchlist: {n} competitors, {n} keywords. Compared with {previous date}.
Searches that could not be fetched: {none | list}.

## Summary

- {The single most important change this week, in one sentence.}
- {Second change.}
- {Third change, or "No other notable changes."}

## New ads

| Advertiser | Started | Opening line | CTA | Landing domain | Ad |
|---|---|---|---|---|---|
| {name} | {date} | {first line of the copy} | {button} | {domain} | [{library_id}]({ad_url}) |

## Stopped since last report

| Advertiser | Ran for | Opening line | Ad |
|---|---|---|---|
| {name} | {days} days | {first line} | [{library_id}]({ad_url}) |

## Strongest ads still live

| Advertiser | Rating | Verdict | Per day | Days | Creatives | Opening line | Ad |
|---|---:|---|---:|---:|---:|---|---|
| {name} | {score} | {verdict} | {reach_per_day} | {days_running} | {creatives} | {first line} | [{library_id}]({ad_url}) |

## Messaging shifts

- **{Advertiser}**: {what changed in hook, offer, proof or CTA, with a short quote}.

## New advertisers on the watched keywords

- {name}: {n} ads, oldest started {date}. {Add to watchlist? yes/no and why.}

## What to test next

- {One or two concrete ideas that follow from the changes above.}

---
Source: public Meta Ad Library, sampled on {date}. Counts are lower bounds.
No spend or performance data is available for these ads.
```
