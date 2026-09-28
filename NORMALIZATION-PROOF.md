# Fixture normalization proof

`normalization-proof.csv` is generated from the official `fixtures.json`, seeded into a fresh PostgreSQL database by `seed_event --if-empty`, then read by `python src/manage.py normalization_proof --event evt_01`. The committed CSV was compared byte-for-byte with a second command run on the same fixture database. The command is read-only; it uses the same `standings()` function as the organizer and published-results pages, so the proof is linked to the running implementation rather than an independent spreadsheet formula. The CSV lists all 40 canonical projects with their review count, raw weighted mean, normalized mean, raw and normalized positions, plus each judge's raw mean and population standard deviation. The one duplicate remains in storage but is excluded from this ranking; the fixture contains 126 stored score rows, of which 122 valid reviews belong to canonical, non-draft projects.

## Method

For each score, compute `r = 0.40 * functionality + 0.35 * quality + 0.25 * innovation`. Each judge's mean `mu` and population standard deviation `sigma` use their valid reviews of canonical, non-draft projects in the event. For a judge's review, compute `clamp(3 + (r - mu) / sigma, 1, 5)` when `sigma > 0`; otherwise use neutral `3`. A project's normalized score is the mean of its adjusted reviews. Rank by normalized score, then slug; unreviewed projects sort last. The CSV's `raw_position` ranks raw means with slug tie-breaking; `position_change = raw_position - row position`, so positive numbers mean a rise after normalization. `normalized_rank` uses competition ranking for exact tied normalized means, while row position is the display order. Means shown in the CSV are rounded for display; ranks are computed before rounding, so equal displayed numbers need not tie.

## What changed on the fixture

| Project | Raw mean / position | Normalized mean / rank | Change |
| --- | ---: | ---: | ---: |
| `prj_34` Iron Switch | 4.350 / 1 | 4.212 / 1 | 0 |
| `prj_33` Slow Trail | 4.083 / 6 | 3.986 / 2 | +4 |
| `prj_11` Salt Ledger | 4.338 / 2 | 3.819 / 5 | -3 |
| `prj_07` Dry Harbour | 3.340 / 30 | 3.333 / 8 | +22 |
| `prj_19` | 3.575 / 16 | 2.588 / 32 | -16 |

Thirty-two of 40 project positions change; this is **not** proof the new ranking is more accurate. Different judges score different project batches. Within-judge centering is useful for a judge who grades consistently high or low, but disjoint assignments, a single review or a flat judge leave weak evidence of comparative merit. `jdg_07` has three identical raw reviews and therefore zero variance; the method gives each a neutral 3.0 instead of inventing differences. `jdg_01` and `jdg_23` each have one review and receive the same neutral treatment. No confidence interval, assignment-overlap adjustment or hidden ground truth is claimed. Organizers should use the raw scores, review counts and audit before treating rank movement as a prize decision.

## Reproduce

On a configured PostgreSQL instance, from the repository root:

```sh
python src/manage.py migrate
python src/manage.py seed_event --if-empty
python src/manage.py normalization_proof --event evt_01 > normalization-proof.csv
```

This requires a fresh or otherwise known fixture-only event for an exact CSV match. Run `PYTHONPATH=src pytest -q src/eventhub/tests/test_normalization_proof.py` for evidence-route tests, then the full suite. The command does not mutate rows. Its CSV output is deliberately not an API endpoint or a certificate.
