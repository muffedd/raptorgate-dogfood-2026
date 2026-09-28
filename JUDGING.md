# Judging

Reviewed `src/eventhub/ranking.py`, `views.py`, `models.py` and judging/rubric tests at the 8792fff source baseline. These are implementation claims from source and checked-in report, not independently rerun measurements. Event requirements: https://dogfoodhack.com/ and https://dogfoodhack.com/spec/.

## Assignment and access

An organizer (Django superuser) creates a judge invitation for selected event tracks, then explicitly assigns each canonical project to a judge. The assignment route rejects a judge outside the project's track or on the project's team. The score-write route independently requires that judge's assignment and current membership in the project's track, and rejects self-scoring; it accepts integer 1-5 values for all three criteria. The score-read API scopes records to the authenticated judge's user/event and denies requests naming a peer. A participant has no judge role. An audit row records previous and current criterion maps, editor and time on each score write. Comments are not included in the audit maps, so a comment edit is not independently recoverable there. There is no assignment balancing algorithm or complete progress dashboard.

The committed acceptance report passes T1 x3 and T2 x4, including own scores, peer denial, participant denial and organizer CSV. These seven checks do not test assignment fairness, track reads across all endpoints, normalization quality or UI completeness. The checker's closed-submission probe receives HTTP 403, but CSRF middleware may reject that POST before deadline logic; a separate app test confirms the deadline handler rejects a late edit with CSRF disabled.

## Weighted score

For criterion values `f`, `q`, `i` (integers 1-5), the default raw score is `0.40f + 0.35q + 0.25i`. Organizer-configured positive finite weights for exactly these three criteria can replace the defaults if they sum to 1. A missing/invalid criterion makes that review ineligible for standings. For example, `(f,q,i)=(4,3,5)` yields `3.9`. Score writes still require all three keys even if weights change. These are portal-project rubric weights, distinct from the competition's 40/25/20/15 judging criteria.

## Normalization implemented

For each judge, calculate mean `mu_j` and population standard deviation `sigma_j` over their valid raw review scores on canonical projects. For a review with raw score `r`, adjusted value is `max(1, min(5, 3 + (r - mu_j) / sigma_j))`. If `sigma_j = 0`, adjusted value is 3.0. A project's raw and normalized scores are the separate means of its valid reviews, rounded to three decimals. Unreviewed projects receive nulls and sort after reviewed projects; ties then sort by project slug. The implementation does not require a minimum count or cross-judge overlap and uses per-judge centering even for a singleton review (which becomes 3.0). Sparse/disjoint batches and flat judges can therefore collapse real differences; no fixture-wide raw-versus-adjusted ranking proof was in the reviewed tree. Do not claim the optional Normalization Proof bonus without publishing one.

## Publication, export and limits

The superuser can fetch standings at `/organizer/results`, and `/organizer/publish` sets an event flag and publication time only after submission close. There is no public results endpoint in the URL map; publication does not yet deliver a participant-facing result. Organizer CSV contains raw criterion rows, not normalized standings. The rubric is fixed to three criterion names, and the current system has no pairwise mode or full judge UI. The official contest weights submissions by Tier Completion & Correctness 40%, Judging Integrity 25%, Adoptability & Operability 20%, and Code Quality & Innovation 15%; optional bonuses break ties, not the main weighted score.
