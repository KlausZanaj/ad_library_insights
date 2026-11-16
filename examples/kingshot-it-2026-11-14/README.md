# Example: Analysis and Plan from one real search

A company search of the advertiser page Kingshot in Italy, collected on 14 November 2026: 212 ads
loaded of 216 active, 14 concepts, reach in Italy read for 12 of them.

| File | What it is |
|---|---|
| [`analisi.md`](analisi.md) | The Analysis level: why these ads reach what they reach, with the evidence |
| [`piano.md`](piano.md) | The Plan level: a plan for another product, built on that analysis |
| [`pacchetto/`](pacchetto) | The data pack the program wrote: the only source of both texts |

The two texts are in Italian, the language they were asked in. The pack is in English, as the
program writes it.

## How they were made

1. The program collected the data and wrote the pack: `overview.md`, one file per specialist
   (`copy.md`, `creative.md`, `reach.md`, `testing.md`) and, for the plan, `project.md`.
2. Four specialists read one file each and returned findings with evidence and strength.
3. Their findings were joined with the templates of the two skills, `competitor-analysis` and
   `competitor-plan`.

## What to check

- Every figure in `analisi.md` and `piano.md` is written in a file of `pacchetto/`. A test
  (`tests/test_examples.py`) checks it, together with the ad ids.
- The amounts of the plan (margin, break-even, budgets, cut rule) are copied from
  `pacchetto/project.md`: the program computed them. The two rules of thumb the plan adds are marked
  as such.
- The project card of the plan is an invented one, made for this example: a medieval strategy board
  game sold from its own site at 39.9, product cost 14, goal 30 orders a day.
- The pictures of the ads (video stills and thumbnails) were looked at for the creative reading and
  are not included here.
