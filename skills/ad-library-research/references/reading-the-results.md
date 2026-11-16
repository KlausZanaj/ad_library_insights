# Reading the results

## One ad per concept

The tool merges the cards of a search before rating them, so that one idea is
one row:

| Merged into one ad | Why it is not creative investment |
|---|---|
| Identical copies ("N ads use this creative and text") | The same ad in several ad sets |
| Versions of one dynamic ad | Meta mixes texts and pictures inside one ad |
| Catalogue ads | The same text with a different product behind each ad |
| Translations of the same ad | The same video under texts in other languages, or the same emoji and digits in texts of different languages |

What was merged is reported, not scored: `cards` (ads carrying the concept),
`copies_total` (identical copies included), `languages`, `kind` (`standard`,
`catalog`, `dynamic`) and, for catalogues, `products`.

## Fields of a rated ad

| Field | Meaning |
|---|---|
| `score` | The rating, 0-100 |
| `score_points` | Points from `scale`, `staying` and `creative`; they add up to `score` |
| `reliability` | `high`: reach in the country searched was read. `medium`: scale estimated from the impression position. `low`: only days and creatives |
| `verdict` | `scaling`, `holding`, `testing`, `review`, `average`, `ended` (see below) |
| `days_running` | Days since the oldest ad of the concept started |
| `creatives` | Different videos or pictures carrying the concept |
| `reach_per_day` | Reach in the country searched, divided by days running (seven at the least). Up to three ads of a concept are read and added up |
| `impression_rank` | Position in the library's list, which is ordered by total impressions, highest first |
| `longevity_score` | The earlier score (days and copy reuse). Informative only |

## How the rating is built

| Part | Measures | Points |
|---|---|---:|
| Scale | People reached per day in the country searched; where not read or not published, the impression position | 60 |
| Staying power | Days running, full at 90 | 25 |
| Creative investment | Different creatives for one concept, full at 10 | 15 |

The weights never change (`60 / 25 / 15`). Scale is relative to the best ad of
the same search (among those of seven days or more), on a log scale. Staying
power (90 days) and creative investment (10 creatives) use fixed thresholds. An
unread ad never gets a higher scale than the weakest ad that was read.

## Verdicts

| Verdict | When |
|---|---|
| `scaling` | 14 to 89 days on air, scale at 70 of 100 or more, in the top third by people per day (only on read reach with at least 5 concepts read) |
| `holding` | 90 days or more, with scale at 40 or more |
| `testing` | Under 30 days (under 7 days an ad is `too_recent`: too recent to judge) |
| `review` | 90 days or more, no fresh ad added, low scale and total reach below the median: a small budget that works or a forgotten ad, to check, not a negative verdict (only on read reach with at least 5 concepts read) |
| `ended` | No longer on air |
| `average` | Everything else |

## Traps

-   **Reach belongs to a market.** Meta publishes reach for ads delivered in
    the EU or the UK. For a search in another country the reach read is about
    those regions, so it is shown but does not rate; reliability stays medium.
-   **Medium is an estimate.** Without reach, scale comes from the position in
    Meta's list, and no ad is called `scaling` or `review`.
-   **Very young ads.** Reach per day is never divided by fewer than 7 days,
    and an ad under 7 days is marked `too_recent`: describe it, build no
    conclusion on it.
-   **Reach is a floor for large concepts.** Up to three ads per concept are
    opened and summed; next to every figure is how many of its ads were read.
-   **No spend, no sales.** The rating is a clue about what an advertiser
    keeps paying for, never proof of profit.
-   **A keyword search is a sample.** It loads the most shown ads, not all of
    them. Say how many were loaded and how many the library counts.
