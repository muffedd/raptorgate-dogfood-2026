# RaptorGate (Dogfood 2026 rewrite)

This implementation was started in the build window. The checked-in acceptance report claims T1 and T2 and shows all seven official probes passing. That does not establish completion of every T1/T2 feature. Most organizer mutations are JSON endpoints; judging has an assignment-scoped web console, and organizer overview/results have HTML views; no demo video is in the reviewed tree.

## Run

From the repository root:

```sh
docker compose build
docker compose pull db
docker compose up
```

Fetch the images and Python dependencies while online. After they are cached, `docker compose up` starts PostgreSQL 16 and Django 5.2, runs migrations and seeds `fixtures.json` only when there is no event. Open http://localhost:8080/projects. Compose binds the portal to `127.0.0.1:8080`. The dependency-fetch step means a fresh, uncached machine has **not** been shown to satisfy the event's offline one-command requirement. Do not put the fixed demo session cookies or database password on a public server.

The seeded sample event closes submissions at `2026-03-01T18:00:00Z`; create a separate open event for a live submission demonstration and select it with the organizer-only `POST /events/select` route. The imported fixture has 41 project rows, including one duplicate retained in storage and hidden from the public gallery.

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

- Public gallery: `GET /projects`, with `q` title search and `track` slug filter; project detail and moderated comments at `GET /projects/<slug>`. Only nondraft, canonical projects for the active event appear.
- Login: `/login/`. Event and team setup: `/events/new`, organizer-only `POST /events/select` with form field `event=<slug>`, `/teams/new`, `/teams/<slug>/invite`, `/join/<token>`. The selected event is global and determines gallery, submissions, judging and public participation. When none is marked active, public gallery, ballot and moderation routes fail closed until an organizer selects one.
- Submission: `/projects/new`; a second POST from the team edits its canonical project before the deadline.
- Judging: assignment-scoped `/judge/console` (light first, persistent manual dark switch, server-confirmed autosave), `/organizer/judges/invite`, `/judge/accept/<token>`, `/organizer/assign`, `/judge/assignments`, `/judge/score/<project_slug>`, `/api/judge/scores`.
- Organizer data: `GET /organizer/overview` renders the active event overview; `GET /organizer/results?view=html` renders a private standings table, while `/organizer/results` remains JSON. `/organizer/rubric`, `/organizer/results`, `/organizer/audit`, `/organizer/publish`, `/api/export.csv`. `GET /organizer/vote-audit` is superuser-only and can select a historical event with `?event=<slug>`; `POST /organizer/comments/<id>/hide` hides a public comment.
- Community participation: `GET /ballot` renders an authenticated voter's stable randomized eligible-project order while voting is open; `POST /vote` records one vote per account per event and returns a receipt. `GET /projects/<slug>` shows comments; authenticated `POST` accepts them while voting is open. `GET /results` exposes aggregate standings only after voting has closed **and** the organizer has published. `GET /receipt/<secret>` checks a receipt only after that same release gate; keep the secret private.
- Embeddable public gallery: `GET /embed/<event-slug>/gallery` is a read-only, event-scoped iframe page with its own CSS and CSP. Example on a trusted host page, using the real event slug:

```html
<iframe src="http://localhost:8080/embed/evt_01/gallery" sandbox="allow-same-origin"
        referrerpolicy="no-referrer" title="Event projects"
        style="width:100%;min-height:480px;border:0"></iframe>
```

The iframe content is public and can be embedded by any origin by default (`frame-ancestors *`); set `WIDGET_FRAME_ANCESTORS` in Django settings for a restricted host (there is no environment-variable hookup yet). Do not embed private results, voting sessions or organizer pages. The widget does not set cookies or show individual judge scores.

Most organizer mutations and some judge routes still produce JSON rather than full screens. The public gallery/results, organizer overview/results and judge console honor a per-browser light-first theme switch; the isolated widget accepts `?theme=dark` and otherwise stays light. The active event selector is a global setting, not a personal preference; recheck the selected event before a demo. To demonstrate a different event, create it, give it tracks/teams/projects through the current flows, then `POST /events/select` as organizer and verify `/projects` before showing that event. Creation accepts name, slug and UTC close time but does not set up tracks or prizes automatically. Authenticated-account voting works; email-verified and open-link choices currently fail closed without identity verification. There is no complete general API/webhook, bulk importer or certificate flow. Fixed fixture cookies and demo credentials are local-only. See ARCHITECTURE.md, DATA-MODEL.md, JUDGING.md and THREAT-MODEL.md for risk and scoring details.

## Submission status

The repo contains an OSI license, Compose setup, official fixture/checker, `.dogfood.toml` and acceptance report. A five-minute demo video is still required. Test clean offline boot, document actual limitations, and re-run the checker on the submitted commit. Freeze: Tuesday 29 September 2026, 18:00 UTC (23:30 IST), per the current https://dogfoodhack.com/ and https://dogfoodhack.com/spec/ pages checked 28 September 2026.
