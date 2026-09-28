# RaptorGate | Dogfood 2026

A self-hosted hackathon portal from submission to judged results, built fresh for Dogfood 2026.

`PostgreSQL: 209/209 x2 (this source); SQLite differs` · `Official checker: 7/7 PASS` · `License: MIT`

`API.md` describes the current partial JSON API. The test status above describes the current tested source before its final release commit, not automated CI or a Docker cold-boot result.

## Features

### Judge workflow

- **Judging:** assignment-scoped console with server-confirmed autosave; backend role, track and team-conflict checks; editable rubric, score audit and CSV export. Organizer results show raw and normalized standings and tied ranks. A reproducible fixture proof in `NORMALIZATION-PROOF.md` and `normalization-proof.csv` shows the rank changes and the limits of the method.

### Community participation

- **Voting and results:** searchable gallery, project detail and moderated comments; authenticated one-vote-per-event ballot with stable randomized order, rate checks, receipt and organizer vote audit. Results and receipt lookup open only after voting closes and the organizer publishes.

### User interface

- **Local-first design:** light-first UI with a saved dark choice across judge, gallery, ballot, organizer and results screens. A separately styled, read-only gallery widget can be embedded on other sites.
- **Responsive and accessible:** the dual-theme sweep checked desktop, tablet and mobile widths, keyboard toggle, persisted choice and mobile overflow.

`.dogfood.toml` claims T1/T2, the scope verified by the official checker. The T3 voting features and T4 widget, JSON API, participation records, portable JSON certificates and one results-published webhook are working slices, not blanket tier claims. See `T3-VOTER-ACCESS.md` for the three access modes and their trust limits. See [Current routes](#current-routes), [Roadmap](#roadmap) and the design documents for details.

## Quickstart

From the repository root on a Docker-capable machine with network access for the first build:

```sh
docker compose build
docker compose pull db
docker compose up
```

This fetches Python/PostgreSQL images and Python packages while online, then starts PostgreSQL 16 and Django 5.2, applies migrations and seeds `fixtures.json` when the database has no event. Open http://localhost:8080/projects. Compose binds to `127.0.0.1:8080`. This is a local demo configuration with fixed credentials; do not publish it directly.

For an offline demonstration, `packaging/README.md` gives the online image-build/archive-export and offline load/boot steps, including Windows PowerShell scripts. Docker Desktop and a prebuilt archive must be available on the target Windows PC. The scripts are shipped; the archive and network-off cold-boot validation are next.

The seeded sample event closes submissions at `2026-03-01T18:00:00Z`; create a separate open event for a live submission demonstration and select it with the organizer-only `POST /events/select` route. The imported fixture has 41 project rows, including one duplicate retained in storage and hidden from the public gallery.

Run the official checker:

```sh
python3 run.py .dogfood.toml > acceptance-report.txt
cat acceptance-report.txt
```

The committed report records three T1 and four T2 PASS lines, `claimed T1 T2, verified T1 T2`. Rerun it on the final submission tree and read each result line; the checker can exit zero even when a line says FAIL. `.dogfood.toml` supplies local demo sessions and routes, not production credentials.

Install `requirements-dev.txt` into a Python environment, then run `python src/manage.py test eventhub.tests` and `PYTHONPATH=src pytest -q`. Run both against the final submission tree.

## Architecture

- Django 5.2 serves HTML pages and role-checked endpoints; PostgreSQL 16 stores event, team, project, judge, assignment, score and participation records.
- Event and track checks run on the server. Score writes are transaction-locked and audited; organizer results normalize each judge's scoring spread while keeping raw scores visible.
- The public ballot derives a stable per-voter project order, writes one vote per account and event, and holds receipts/results behind the release gate. The embeddable gallery is read-only and uses its own CSS and content-security policy.
- `src/eventhub/` owns models, views and tests; `src/templates/` and `src/static/` own the UI; `packaging/` contains the image-bundle handoff. See `ARCHITECTURE.md`, `DATA-MODEL.md`, `JUDGING.md` and `THREAT-MODEL.md` for the design and its risk decisions.

## Testing and proof

At the current reviewer-fix source, real PostgreSQL pytest and Django runners each passed **209/209**, no skips. SQLite runs can collect fewer tests and skip PostgreSQL-only concurrency cases; do not compare their totals with the PostgreSQL runs. An empty PostgreSQL database migrated, seeded the official fixture and passed all seven literal T1/T2 checker probes. The committed acceptance report also shows seven PASS lines. Test coverage includes role and event isolation, fixture integrity, submission and score races, voting, results gating, widget isolation and UI truths. The checked-in report is a prior run, so regenerate it against the final submission commit. Offline Docker cold boot remains a separate proof step.

## Current routes

- Bulk project data: organizer-only `GET /organizer/projects.csv` exports up to 5000 active-event projects; `POST /organizer/projects/import` accepts a UTF-8 CSV body with exact `project_slug,title,summary,repo_url,team_slug,track_slug` columns, 1-500 rows, up to 1 MB. It creates projects only while submissions are open and results unpublished. Team and track slugs must already belong to the active event; duplicate slugs reject the entire batch. This does not migrate judges, scores, votes or users.

- Public gallery: `GET /projects`, with `q` title search and `track` slug filter; project detail and moderated comments at `GET /projects/<slug>`. Only nondraft, canonical projects appear. Select an active event before demonstrating multiple events; the gallery currently falls back to the oldest event if none is selected.
- Login: `/login/`. Event and team setup: `/events/new`, organizer-only `POST /events/select` with form field `event=<slug>`, `/teams/new`, `/teams/<slug>/invite`, `/join/<token>`. The selected event is global and determines gallery, submissions, judging and public participation. Ballot, results and moderation require an active event. A few routes fall back to the oldest event when none is selected.
- Submission: `/projects/new`; a second POST from the team edits its canonical project before the deadline.
- Judging: assignment-scoped `/judge/console` (light first, persistent manual dark switch, server-confirmed autosave), `/organizer/judges/invite`, `/judge/accept/<token>`, `/organizer/assign`, `/judge/assignments`, `/judge/score/<project_slug>`, `/api/judge/scores`.
- Organizer data: `GET /organizer/overview` renders the active event overview; `GET /organizer/results?view=html` renders a private standings table, while `/organizer/results` remains JSON. `/organizer/rubric`, `/organizer/results`, `/organizer/audit`, `/organizer/publish`, `/api/export.csv`. `GET /organizer/vote-audit` is superuser-only and can select a historical event with `?event=<slug>`; `POST /organizer/comments/<id>/hide` hides a public comment.
- Community participation: `GET /ballot` renders an authenticated voter's stable randomized eligible-project order while voting is open; `POST /vote` records one vote per account per event and returns a receipt. `GET /projects/<slug>` shows comments; authenticated `POST` accepts them while voting is open. `GET /results` exposes aggregate standings only after voting has closed **and** the organizer has published. `GET /receipt/<secret>` checks a receipt only after that same release gate; keep the secret private.
- Partial JSON API: see `API.md`; project and published standings reads are public, judge assignment reads require a bearer token. Issuance/revocation require an authenticated session and CSRF. This is not complete REST.
- Participation record snapshot: organizer-only issue after published voting close, public verify if `RECORD_SIGNING_KEY` is set; this is not a certificate. See `PARTICIPATION-RECORDS.md`.
- Results-published webhook: operator-configured HTTPS callback queued on first publication, delivered by a separate management command, with HMAC body signature and organizer-only attempt status. See `WEBHOOKS.md`; this is one event type, not full webhook coverage.
- Portable JSON judge certificate: organizer-only `POST /organizer/certificates/issue` after public results, public `GET /certificates/<id>.json`. Private signing key required; embedded public key must be pinned through a trusted event channel. See `CERTIFICATES.md`.
- Embeddable public gallery: `GET /embed/<event-slug>/gallery` is a read-only, event-scoped iframe page with its own CSS and CSP. Example on a trusted host page, using the real event slug:

```html
<iframe src="http://localhost:8080/embed/evt_01/gallery" sandbox="allow-same-origin"
        referrerpolicy="no-referrer" title="Event projects"
        style="width:100%;min-height:480px;border:0"></iframe>
```

The iframe content is public and can be embedded by any origin by default (`frame-ancestors *`); set `WIDGET_FRAME_ANCESTORS` in Django settings for a restricted host (there is no environment-variable hookup yet). Do not embed private results, voting sessions or organizer pages. The widget does not set cookies or show individual judge scores.

Open-link voting adds organizer-issued one-use links; email voting adds a one-time SMTP code and fails closed when SMTP is not configured. Both preserve the same ballot and vote gate. Several organizer controls and judge routes expose JSON alongside the HTML workbench and results screens. The judge console, gallery, project detail, open ballot, organizer overview/results and public results honor a per-browser light-first theme switch with a saved dark choice. The widget is isolated from that preference; it accepts `?theme=dark` and otherwise stays light. These surfaces were visually checked at 1440, 768 and 320 pixel widths, with keyboard toggle and mobile overflow checks; this does not replace browser testing of other routes. The active event selector is a global setting, not a personal preference; recheck the selected event before a demo. To demonstrate a different event, create it, give it tracks/teams/projects through the current flows, then `POST /events/select` as organizer and verify `/projects` before showing that event. Creation accepts name, slug and UTC close time but does not set up tracks or prizes automatically. The seeded credentials are for a localhost demo only. See ARCHITECTURE.md, DATA-MODEL.md, JUDGING.md and THREAT-MODEL.md for implementation and security decisions.

## Roadmap

Next: live SMTP delivery proof for email-gated voting; expand the read-only `/api/v1` slice into complete REST and webhook coverage beyond one results-published callback; a judge-facing certificate distribution UI. The HMAC record snapshot is not a certificate; see `PARTICIPATION-RECORDS.md`. Portable Ed25519 JSON certificate issuance is a separate tested slice with key-pinning limits in `CERTIFICATES.md`. An organizer-scoped CSV project import/export slice is available at `/organizer/projects/import` and `/organizer/projects.csv`, with full lifecycle migration still on the roadmap. Complete a Docker-capable network-off cold run using the packaged image archive, record its checker output, and link the five-minute event-lifecycle demo video. These are planned deliverables, not shipped tier claims. Keep `.dogfood.toml` at T1/T2 until a later tier is finished and independently checked.

The repository is private during the build. Publication needs a separate owner decision and review of the full history and demo credentials. Freeze: Tuesday 29 September 2026, 18:00 UTC (23:30 IST), per https://dogfoodhack.com/ and https://dogfoodhack.com/spec/ checked 28 September 2026.
