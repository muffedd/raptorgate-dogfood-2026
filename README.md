# RaptorGate (Dogfood 2026 rewrite)

This implementation was started in the build window. The checked-in acceptance report claims T1 and T2 and shows all seven official probes passing. That does not establish completion of every T1/T2 feature. The organizer and judge workflows are mostly JSON endpoints, not a complete UI; no demo video is in the reviewed tree.

## Run

From the repository root:

```sh
docker compose build
docker compose pull db
docker compose up
```

Fetch the images and Python dependencies while online. After they are cached, `docker compose up` starts PostgreSQL 16 and Django 5.2, runs migrations and seeds `fixtures.json` only when there is no event. Open http://localhost:8080/projects. Compose binds the portal to `127.0.0.1:8080`. The dependency-fetch step means a fresh, uncached machine has **not** been shown to satisfy the event's offline one-command requirement. Do not put the fixed demo session cookies or database password on a public server.

The seeded sample event closes submissions at `2026-03-01T18:00:00Z`; create a separate open event for a live submission demonstration only after checking the active-event limitation below. The imported fixture has 41 project rows, including one duplicate retained in storage and hidden from the public gallery.

Run the official checker:

```sh
python3 run.py .dogfood.toml > acceptance-report.txt
cat acceptance-report.txt
```

The committed report at the reviewed baseline shows three T1 PASS and four T2 PASS lines, with `claimed T1 T2, verified T1 T2`. Keep the output unedited and rerun it after every change. The checker can exit zero despite FAIL lines. `.dogfood.toml` contains fixed local demo session headers and actual routes; it must not be reused as production authentication.

Tests documented by the repo: `python src/manage.py test eventhub.tests` or `PYTHONPATH=src pytest -q` after installing `requirements-dev.txt`. At the 8792fff source baseline the suite covered acceptance, invites, judging and rubric behavior. Later regression tests also cover CSV, fixture import, authorization, results, races and cross-event scope; rerun the full suite after each change and report its actual result, including any skips.

## Engineering log

This repository records a fresh build.The initial implementation grew from the fixture-backed T1/T2 portal (`acc016c`) through deadline-locked submissions (`53ea4f9`), event/team setup (`1e3915d`), judge scoring (`ca4f254`), one-use invitations (`16a92d4`) and rubric/audit work (`ebe8151`). The first Compose acceptance run was recorded in `acceptance-report.txt` (remote acceptance commit `3cf621d`); it showed seven literal PASS lines, but the checker does not prove every route is finished.

The next wave was defect finding and repair, not just added test count. Tinku's six regression files (`ab49ff3`) exposed scope, role, CSV, import and concurrency failures. The source fixes (`4f99e32`) addressed nine reproduced defects. PostgreSQL testing then exposed a concurrent judge-invite race; `7fd5527` adds an event/user uniqueness constraint and a 409 response for the losing invite. Jasper's reviewed architecture, data, judging and threat notes are in `13a4d6f`. Draft exclusion followed in `a8a22c8`, with proof tests in `642769c`. The live gallery adaptation in `9b82d01` uses real projects. `4684178` configures `STATICFILES_DIRS`, but the stylesheet still 404'd under Compose's `DJANGO_DEBUG=0`; `5eec446` fixes actual delivery by adding `--insecure` to `runserver` for this local demo deployment, verified live (`200`, `text/css`) with a rendered gallery screenshot. The eight standalone mock dashboard pages were not shipped as functional routes. Check the final commit's tests and checker output rather than assuming these milestones establish completion.

## Current routes

- Public gallery: `GET /projects`, with `q` title search and `track` slug filter.
- Login: `/login/`. Event and team setup: `/events/new`, `/teams/new`, `/teams/<slug>/invite`, `/join/<token>`.
- Submission: `/projects/new`; a second POST from the team edits its canonical project before the deadline.
- Judging: `/organizer/judges/invite`, `/judge/accept/<token>`, `/organizer/assign`, `/judge/assignments`, `/judge/score/<project_slug>`, `/api/judge/scores`.
- Organizer data: `/organizer/rubric`, `/organizer/results`, `/organizer/audit`, `/organizer/publish`, `/api/export.csv`.

Many routes produce JSON responses, not full screens. The active event is currently the database event with the lowest ID, not a selected event. A newly created event will not become active while the seeded event remains first. Event creation currently accepts a name, slug and UTC close time, but does not configure tracks or prizes. There is no public published-results route, no community voting, and no general API/webhook or bulk import/export. Publication sets a database flag and timestamp; it does not expose results to the public. See ARCHITECTURE.md, DATA-MODEL.md, JUDGING.md and THREAT-MODEL.md for details and known risks.

## Submission status

The repo contains an OSI license, Compose setup, official fixture/checker, `.dogfood.toml` and acceptance report. A five-minute demo video is still required. Test clean offline boot, document actual limitations, and re-run the checker on the submitted commit. Freeze: Tuesday 29 September 2026, 18:00 UTC (23:30 IST), per the current https://dogfoodhack.com/ and https://dogfoodhack.com/spec/ pages checked 28 September 2026.
