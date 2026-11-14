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
| `reliability` | `high`: reach was read. `medium`: scale estimated from the impression position. `low`: only days and creatives |
| `verdict` | `scaling`, `holding`, `testing`, `review`, `average` (see below) |
| `days_running` | Days since the oldest ad of the concept started |
| `creatives` | Different videos or pictures carrying the concept |
| `reach_per_day` | Reach of the ad that was opened, divided by its own days. Only after reach is read |
| `impression_rank` | Position in the library's list, which is ordered by total impressions, highest first |
| `longevity_score` | The earlier score (days and copy reuse). Informative only |

## How the rating is built

| Part | Measures | Points with reach | Points without |
|---|---|---:|---:|
| Scale | People reached per day; without reach, the impression position | 60 | 50 |
| Staying power | Days running, full at 90 | 25 | 30 |
| Creative investment | Different creatives for one concept | 15 | 20 |

Scale and creatives are relative to the other ads of the same search, on a log
scale. Staying power uses a fixed 90 days.

## Verdicts

| Verdict | When |
|---|---|
| `scaling` | In the top third of the search for scale, with scale at 70 of 100 or more |
| `holding` | 90 days or more, with scale at 40 or more |
| `testing` | Under 30 days |
| `review` | 90 days or more with scale at 25 or less: possibly forgotten |
| `average` | Everything else |

## Traps

-   **Reach belongs to a market.** Meta publishes reach for ads delivered in
    the EU or the UK. For a search in another country the reach read is about
    those regions, so it is shown but does not rate; reliability stays medium.
-   **Medium is an estimate.** Without reach, old ads look bigger than they
    are, because total impressions grow with time.
-   **Very young ads.** Reach per day of a one-day-old ad is high by
    construction. Read `scaling` on such an ad as "pushed hard at launch".
-   **Reach is per ad.** For a merged concept it is the reach of its most
    shown ad, not of the group.
-   **No spend, no sales.** The rating is a clue about what an advertiser
    keeps paying for, never proof of profit.
-   **A keyword search is a sample.** It loads the most shown ads, not all of
    them. Say how many were loaded and how many the library counts.
