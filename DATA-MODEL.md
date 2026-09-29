# Data model and data movement

Reviewed current source: `src/eventhub/models.py`, `management/commands/seed_event.py`, `views.py`, `bulk.py`, and `lifecycle_export.py` on the integrated UI branch. Official input: https://dogfoodhack.com/spec/fixtures.json.

## Tables and constraints

- `Event`: unique slug, title, submission close time, publication time/flag, JSON rubric.
- `Track`: belongs to event; `(event, slug)` unique.
- `Team`: belongs to event; `(event, slug)` unique; many-to-many Django users; invite token and expiry.
- `Project`: belongs to event, team and track; `(event, slug)` unique; title, summary, repository URL, submission time, draft flag, optional `duplicate_of` self-link.
- `Judge`: belongs to event and Django user, has eligible tracks and invitation fields; `(event, slug)` unique.
- `Assignment`: judge-project pair, unique; `Score`: judge-project pair, unique, JSON criteria, comment and edit time.
- `ScoreAudit`: score, editing user, previous/current JSON criteria and write timestamp.

The database does not itself constrain project team/track to the same event, nor assignment judge/project to the same event. Current endpoint queries and form validation enforce relevant boundaries on the exposed paths; direct data writes need care. The submission handler supports a private draft-save action before the deadline. A team may publish its canonical draft, but cannot revert a published project to draft; public gallery, ballot, assignments and standings exclude drafts.

## Fixture import

The current official fixture has one event, eight tracks, 30 judges, 40 teams, 41 project records and 126 score records. Its one same-team duplicate is kept in the database and linked to the earlier canonical project; gallery and standings exclude rows with `duplicate_of`. The seed upserts event, tracks, teams, judges, projects and scores by event/slug or judge/project. User records are created for team members and judges, and fixed local session cookies are generated for organizer, participant, judge A and judge B. `--if-empty` skips record import whenever any event exists and reprints the fixed fixture session headers. Without it, seeding updates known fixture rows and membership/role mappings; it is not a safe general import or migration facility. The fixture close time is UTC and already past, so the checker POST is rejected.

## Scoring and movement out

The current criteria keys are fixed to functionality, quality and innovation for score writes and CSV. Criteria are JSON, with integer 1-5 validation on the score-write route; the fixture import validates integer 1-5 criteria and timezone-aware close time before writes, but the model itself has no matching schema constraint. `/organizer/rubric` stores configurable weights for those three keys, positive/finite and summing to 1. Missing score rows remain missing. Ranking excludes duplicate projects, skips reviews with missing/invalid criteria, returns `null` scores for unreviewed projects, and sorts these last. CSV rows contain `project_id,project_title,team,track,judge,functionality,quality,innovation`, raw values only; string cells beginning with a spreadsheet formula prefix after leading whitespace receive an apostrophe. The legacy `/api/export.csv` is a raw-score export, not a complete re-import format. Separate organizer-only lifecycle snapshots at `/organizer/export/{teams,submissions,assignments,scores,results}.csv` cover those five datasets for the active event (up to 5,000 rows each). `/organizer/projects.csv` exports public project metadata, and `/organizer/projects/import` accepts a bounded, validated project CSV (up to 500 complete rows and 1 MB); neither route is a general database migration or re-import of every relationship, audit row and score.

The current fixture file itself, not the prose's rounded project count, is the record to import. Source: https://dogfoodhack.com/spec/ and https://dogfoodhack.com/spec/fixtures.json.
