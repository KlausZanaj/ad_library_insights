# Reading the results

## Fields that carry the signal

| Field | What it tells you |
|---|---|
| `days_running` | Days since the start date. Long runs mean the advertiser chose not to turn the ad off. |
| `repetitions` | Ads carrying the same copy from the same advertiser (the card's own counter, summed over identical copies in the sample). High values mean the copy is being scaled across creatives or audiences. |
| `creative_variants` | Distinct cards sharing that copy. Many variants with one copy means the advertiser is testing visuals, not words. |
| `multiple_versions` | The ad uses dynamic variations. The text shown is one of several. |
| `cta`, `landing_domain` | Where the click goes and what it is asked to do. Compare across advertisers to see who sells directly and who collects leads. |
| `results_label` | The library's own total for the search. The parsed sample is usually a fraction of it. |

## How the score is built

    age        = min(days_running / 90, 1)
    repetition = min(log(repetitions) / log(10), 1)
    score      = 100 * (0.6 * age + 0.4 * repetition)

Everything running longer than 90 days gets the full age component; ties are
broken by the earlier start date. An ad that started last week can still rank
high if its copy is reused many times.

## Traps

-   **Big brands run everything for a long time.** A long-running ad from an
    advertiser with a large budget is weaker evidence than one from a small
    shop. Weigh the advertiser, not only the score.
-   **Recency bias of the sample.** The library lists recent ads first, so a
    shallow scroll under-represents old ads. If the ranking looks young, rerun
    with a higher `scroll_rounds`.
-   **Keyword search matches text anywhere.** Results can include ads that
    only mention the keyword in passing. Drop off-topic advertisers before
    drawing conclusions.
-   **A start date is the date of this version.** An advertiser who edits an
    ad restarts the clock. `repetitions` partly compensates.
-   **Inactive ads** have an end date; their `days_running` is the full run.
