# RaptorGate (Dogfood 2026 rewrite)

Fresh Dogfood 2026 build.The committed checker report claims T1/T2 and has seven literal PASS lines. The code also contains substantial T3 work and one T4 widget slice, but neither tier is complete. Authenticated community voting, comments, ballot randomization, rate/duplicate checks, audit, receipts and gated public results run; email-gated and open-link voting modes are settings only and reject voters until verification is implemented. T4 has a read-only embeddable gallery, not a complete REST API, webhook, signed-record, certificate and bulk-import system. Do not infer tier completion from the number of tests or the checker, which checks only seven T1/T2 behaviors. No five-minute demo video or offline cold-boot proof is in this repository.

## Run

From the repository root on a Docker-capable machine with network access for the first build:

```sh
docker compose build
docker compose pull db
docker compose up
```

This fetches Python/PostgreSQL images and Python packages while online, then starts PostgreSQL 16 and Django 5.2, applies migrations and seeds `fixtures.json` when the database has no event. Open http://localhost:8080/projects. Compose binds to `127.0.0.1:8080`. This is a local demo configuration with fixed credentials; do not publish it directly.

For an **offline** run, `packaging/README.md` describes online image-build and archive export plus a separate offline load/boot. The scripts are committed, but no image archive is included and no Docker-capable network-off cold rehearsal has passed yet. A fresh Windows PC cannot boot this repo from source offline without Docker Desktop installed and the prebuilt archive transferred. Jasper has been asked to test the actual build/cold run; do not claim the offline requirement before that evidence lands.

The seeded sample event closes submissions at `2026-03-01T18:00:00Z`; create a separate open event for a live submission demonstration and select it with the organizer-only `POST /events/select` route. The imported fixture has 41 project rows, including one duplicate retained in storage and hidden from the public gallery.

Run the official checker:

```sh
python3 run.py .dogfood.toml > acceptance-report.txt
cat acceptance-report.txt
```

The committed checker report shows three T1 PASS and four T2 PASS lines, with `claimed T1 T2, verified T1 T2`. Local testing at the current tree also passed all seven probes after an empty PostgreSQL migration/seed/boot in a prepared Linux environment. The checked-in report is a historical run; regenerate it from the final submission tree after the real deployment. Keep checker output unedited. The checker can exit zero despite FAIL lines. `.dogfood.toml` contains fixed local demo session headers and actual routes; it must not be reused as production authentication.

Tests documented by the repo: `python src/manage.py test eventhub.tests` or `PYTHONPATH=src pytest -q` after installing `requirements-dev.txt`. At private-main commit `7e1c52a`, real PostgreSQL pytest and Django runners each passed 176/176 tests with no skips. Coverage includes acceptance, invites, fixture import, judging, concurrency, event isolation, voting, comments, public-result gates, widget and UI truths. This is prepared-environment verification, not Docker cold-boot proof. Run both suites against the final source and report skips as well as passes.

## Engineering log

This repository records a fresh build.The initial implementation grew from the fixture-backed T1/T2 portal (`acc016c`) through deadline-locked submissions (`53ea4f9`), event/team setup (`1e3915d`), judge scoring (`ca4f254`), one-use invitations (`16a92d4`) and rubric/audit work (`ebe8151`). The first Compose acceptance run was recorded in `acceptance-report.txt` (remote acceptance commit `3cf621d`); it showed seven literal PASS lines, but the checker does not prove every route is finished.

The next wave was defect finding and repair, not just added test count. Tinku's six regression files (`ab49ff3`) exposed scope, role, CSV, import and concurrency failures. The source fixes (`4f99e32`) addressed nine reproduced defects. PostgreSQL testing then exposed a concurrent judge-invite race; `7fd5527` adds an event/user uniqueness constraint and a 409 response for the losing invite. Jasper's reviewed architecture, data, judging and threat notes are in `13a4d6f`. Draft exclusion followed in `a8a22c8`, with proof tests in `642769c`. The live gallery adaptation in `9b82d01` uses real projects. `4684178` configures `STATICFILES_DIRS`, but the stylesheet still 404'd under Compose's `DJANGO_DEBUG=0`; `5eec446` fixes actual delivery by adding `--insecure` to `runserver` for this local demo deployment, verified live (`200`, `text/css`) with a rendered gallery screenshot. The eight standalone mock dashboard pages were not shipped as functional routes. Check the final commit's tests and checker output rather than assuming these milestones establish completion.

## Status by tier

- **T1/T2 claimed:** fixture-backed public gallery, deadline-locked canonical submissions, organizer event/team setup, judge invitation, assignment/track/team conflict checks, score audit, rubric/normalization and CSV. The official checker verified its seven probes. Gaps remain in participant onboarding, a full organizer GUI and a tested cold offline boot.
- **T3 partial, not claimed:** authenticated-account ballots with stable per-voter ordering, one vote per event, receipt verification only after publication and voting close, comments/moderation, rate counters and superuser vote audit. Email-verified and open-link access are not implemented and fail closed. Sybil voting with multiple accounts remains possible.
- **T4 partial, not claimed:** a public read-only iframe gallery widget with isolated CSS and explicit `?theme=dark` option. REST/token API coverage, webhooks, certificate/record generation, signed judge participation and bulk import are not shipped.

## Current routes

- Public gallery: `GET /projects`, with `q` title search and `track` slug filter; project detail and moderated comments at `GET /projects/<slug>`. Only nondraft, canonical projects appear. The gallery currently falls back to the oldest event if none is active; public ballot, comments and results do not.
- Login: `/login/`. Event and team setup: `/events/new`, organizer-only `POST /events/select` with form field `event=<slug>`, `/teams/new`, `/teams/<slug>/invite`, `/join/<token>`. The selected event is global and determines gallery, submissions, judging and public participation. When none is marked active, public ballot, results and moderation routes fail closed; the gallery and some organizer routes still use the oldest event fallback. Select an active event before a real multi-event demo.
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

Most organizer mutations and some judge routes still produce JSON rather than full screens. The judge console, gallery, project detail, open ballot, organizer overview/results and public results honor a per-browser light-first theme switch with a saved dark choice. The widget is isolated from that preference; it accepts `?theme=dark` and otherwise stays light. These surfaces were visually checked at 1440, 768 and 320 pixel widths, with keyboard toggle and mobile overflow checks; this does not replace browser testing of other routes. The active event selector is a global setting, not a personal preference; recheck the selected event before a demo. To demonstrate a different event, create it, give it tracks/teams/projects through the current flows, then `POST /events/select` as organizer and verify `/projects` before showing that event. Creation accepts name, slug and UTC close time but does not set up tracks or prizes automatically. Authenticated-account voting works; email-verified and open-link choices currently fail closed without identity verification. There is no complete general API/webhook, bulk importer or certificate flow. Fixed fixture cookies and demo credentials are local-only. See ARCHITECTURE.md, DATA-MODEL.md, JUDGING.md and THREAT-MODEL.md for risk and scoring details.

## Submission status

The repo contains an OSI license, Compose setup, official fixture/checker, `.dogfood.toml`, a historical acceptance report and unverified offline image scripts. A five-minute demo video and an actual network-off Docker cold-boot proof are still required. Re-run the checker and both PostgreSQL test runners on the submitted commit. Keep the private repository private until a separate approval and secret/history review authorize publication. Freeze: Tuesday 29 September 2026, 18:00 UTC (23:30 IST), per the current https://dogfoodhack.com/ and https://dogfoodhack.com/spec/ pages checked 28 September 2026.
