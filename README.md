# RaptorGate | Dogfood 2026

A self-hosted hackathon portal from submission to judged results, built fresh for Dogfood 2026.

`PostgreSQL: 289 Django + 292 pytest PASS (this source); SQLite differs` · `Official checker: 7/7 PASS` · `License: MIT`

`API.md` describes the current partial JSON API. The test counts are local PostgreSQL runs on this source, not automated CI. The independently reported amd64 cold-boot proof covers commit `4cd5a399`, before this documentation update.

## Features

### Judge workflow

- **Judging:** assignment-scoped console with server-confirmed autosave; backend role, track and team-conflict checks; editable rubric, score audit and CSV export. Organizer results show raw and normalized standings and tied ranks. A reproducible fixture proof in `NORMALIZATION-PROOF.md` and `normalization-proof.csv` shows the rank changes and the limits of the method.

### Community participation

- **Voting and results:** searchable gallery, project detail and moderated comments; authenticated one-vote-per-event ballot with stable randomized order, rate checks, receipt and organizer vote audit. Results and receipt lookup open only after voting closes and the organizer publishes.

### User interface

- **Local-first design:** light-first UI with a saved dark choice across judge, gallery, ballot, organizer and results screens. A separately styled, read-only gallery widget can be embedded on other sites.
- **Responsive and accessible:** the dual-theme sweep checked desktop, tablet and mobile widths, keyboard toggle, persisted choice and mobile overflow.

`.dogfood.toml` claims T1/T2, the scope verified by the official checker. The T3 voting features and T4 widget, JSON API, participation records, portable JSON certificates and one results-published webhook are working slices, not blanket tier claims. See `T3-VOTER-ACCESS.md` for the three access modes and their trust limits. See [Current routes](#current-routes), [Roadmap](#roadmap) and the design documents for details.

## Demo-only secrets and DEBUG - read before deployment

**This repository is a localhost demo, not a production-ready deployment.** The checked-in Compose file has a fixed PostgreSQL password and `DJANGO_SECRET_KEY`; the Django fallback key is also fixed, and `DJANGO_DEBUG` defaults to **on** outside Compose (Compose sets it to `0`). The checker config includes fixed demo session credentials. Do not expose this stack to the internet, reuse the demo credentials, or deploy it as-is. For a non-demo deployment, supply unique secrets outside version control, set `DJANGO_DEBUG=0`, restrict hosts/network access, rotate demo credentials and review the deployment security settings first.

## Quickstart

From the repository root on a Docker-capable machine with network access for the first build:

```sh
docker compose build
docker compose pull db
docker compose up
```

This fetches Python/PostgreSQL images and Python packages while online, then starts PostgreSQL 16 and Django 5.2, applies migrations and seeds `fixtures.json` when the database has no event. Open http://localhost:8080/projects. Compose binds to `127.0.0.1:8080`. This is a local demo configuration with fixed credentials; do not publish it directly.

For an offline demonstration, `packaging/README.md` gives the online image-build/archive-export and offline load/boot steps, including Windows PowerShell scripts. Docker Desktop and a prebuilt archive must be available on the target Windows PC. An independent Ubuntu 24.04 x86_64 VM cold-boot report for commit `4cd5a399` records a fresh Docker host, the network interface down during boot and proof, a checksum-verified image archive, healthy PostgreSQL, a seeded portal, HTTP 200 for gallery and CSS, and seven literal official checker PASS lines. See `packaging/README.md` for scope and limits. This was not a Windows or arm64 run.

The seeded sample event closes submissions at `2026-03-01T18:00:00Z`; create a separate open event for a live submission demonstration and select it with the organizer-only `POST /events/select` route. The imported fixture has 41 project rows, including one duplicate retained in storage and hidden from the public gallery.

Organizer-only lifecycle CSV snapshots for the active event are at `/organizer/export/{teams,submissions,assignments,scores,results}.csv` and linked from the organizer overview. Teams include individual member email addresses; submissions include drafts and duplicates; scores include raw criteria and comments; results include raw and normalized ranks even before publication. Keep downloaded CSVs private. These read-only exports do not import participant, assignment or score state and are limited to 5,000 rows per file. The legacy `/api/export.csv` route remains unchanged for the checker.

Run the official checker:

```sh
python3 run.py .dogfood.toml > acceptance-report.txt
cat acceptance-report.txt
```

The committed report records three T1 and four T2 PASS lines, `claimed T1 T2, verified T1 T2`, from this source on a fresh migrated and fixture-seeded local PostgreSQL database with the checker pointed at an isolated localhost port 18909. It is a separate local check, not the independent Docker or offline cold-boot log. The checked-in `.dogfood.toml` defaults to localhost:8080 for Compose. Rerun the checker on the final submission tree and read each result line; it can exit zero even when a line says FAIL. `.dogfood.toml` supplies local demo sessions and routes, not production credentials.

Install `requirements-dev.txt` into a Python environment, then run `python src/manage.py test eventhub.tests` and `PYTHONPATH=src pytest -q`. Run both against the final submission tree.

## Architecture

- Django 5.2 serves HTML pages and role-checked endpoints; PostgreSQL 16 stores event, team, project, judge, assignment, score and participation records.
- Event and track checks run on the server. Score writes are transaction-locked and audited; organizer results normalize each judge's scoring spread while keeping raw scores visible.
- The public ballot derives a stable per-voter project order, writes one vote per account and event, and holds receipts/results behind the release gate. The embeddable gallery is read-only and uses its own CSS and content-security policy.
- `src/eventhub/` owns models, views and tests; `src/templates/` and `src/static/` own the UI; `packaging/` contains the image-bundle handoff. See `ARCHITECTURE.md`, `DATA-MODEL.md`, `JUDGING.md` and `THREAT-MODEL.md` for the design and its risk decisions.

## Testing and proof

At this source, both full runners passed on real PostgreSQL: **289/289 Django tests** and **292/292 pytest tests** (including three packaging checks), no skips. Pytest reported four Django 6 URL-field default-scheme deprecation warnings, not failing tests. SQLite can skip PostgreSQL-only concurrency cases, so its total is not comparable. On a fresh migrated and fixture-seeded PostgreSQL database, the official checker returned **7/7 literal PASS lines** for the claimed T1/T2 probes. The checked-in `acceptance-report.txt` captures the seven PASS lines on isolated port 18909; the checker was rerun after these regression tests with the same seven PASS lines. These local checks are not the independent Docker cold-boot proof, which covers the earlier `4cd5a399` source tree. The separate local event-lifecycle video is not an offline cold-boot proof either.

Selected regression cases that can be inspected in `src/eventhub/tests/`:

| Case | Expected result and boundary |
| --- | --- |
| Signup with a forged `is_staff` or `is_superuser` POST field | Extra privilege fields are ignored by the user-creation form; signup makes a normal user, not an organizer or judge. `test_signup.py` now directly checks this injected-field case; the reviewer also probed it live. |
| Duplicate username, short/common/mismatched password, and authenticated signup | Invalid or redundant registration is rejected; successful registration can log in, with no judge role. `test_signup.py`. |
| Judge comment-only revision | `ScoreAudit.previous` retains the old comment and criteria; `current` holds the new comment and criteria. Non-organizers cannot fetch the audit trail. `test_judging.py`. |
| Edited certificate JSON | Changing the signed payload makes the Ed25519 check fail (red on `/verify`, nonzero exit offline). `test_verify_public.py`. |
| Validly self-signed but unissued certificate | Signature alone is not trusted by the site: `/verify` rejects it as not a published issuance. `test_verify_public.py`. |
| Offline certificate with a different trusted public key | `verify.py` exits nonzero despite the intact signature. Without a supplied trusted key, it reports internal signature validity but explicitly does **not** verify issuer identity. `test_verify_public.py`. |
| Vote receipt and participation record | Receipt checks are gated until publication and reveal no voter identity, but the receipt is a bearer capability: any holder can use `/receipt/<secret>/proof` to learn the voted project after release; HMAC record checks need the server-held key and cannot be independently verified. `test_verify_public.py`. |
| Organizer vote signals | The panel is superuser-only, event-scoped and aggregate-only; shared IPs and retry counts are labeled signals, not verdicts. `test_vote_signals.py`. |
| Results expander | Raw and normalized means, judge count, rank movement and unscored state are aggregate-only. The public page does not expose judge identities, comments or individual ballots; it stays gated before publication. `test_results_explainer.py`. |

Other suites exercise event and track isolation, team and judge permissions, concurrent first submissions/scores, rubric/ranking ties, ballot identity modes and duplicate/rate controls, results release gates, widget isolation, CSV import, certificates, records, the partial API and publication webhook. Test counts describe executed cases, not proof of full T3/T4 tier completion.

### UI accessibility sweep (September 29, 2026)

A live Chrome/axe-core 4.13.0 sweep covered the public gallery, signup, verification, published results and project detail, plus organizer overview, private results and vote-signals pages at desktop width. Those eight rendered light-theme pages reported **zero automated WCAG 2 A/AA, WCAG 2.1 A/AA and axe best-practice violations** with 31-38 passing rules each at the first post-fix desktop run. Dark-theme retests on the same routes, plus signup, reported zero violations after color and scroll-focus fixes (31-43 passing rules). A separate mobile-width dark-theme pass found low contrast in selected navigation, track badges and results expander summaries; those dark colors were corrected and retested. It also found a horizontally scrollable organizer standings table lacking keyboard focus; the table wrapper now has a named focusable region. This is an automated snapshot, not a WCAG compliance certificate. Native `<details>/<summary>` expands with keyboard; focused links and controls follow DOM order. Manual desktop/mobile pixel checks inspected the verify, results expander and organizer signals pages. No meaningful images on these pages require alt text; text-only logos are links.

The sweep prompted fixes that automated checks alone miss: a visible-on-focus “Skip to main content” link and labeled navigation landmark; a stronger shared focus outline (including `<summary>`); project-specific accessible names for repeated “Cast vote” buttons; helper text tied to the verify textarea; and larger mobile text for small metadata and ballot actions. `test_accessibility.py` covers the durable landmark, label and native-expander structure. Some older plain-form pages, the isolated widget and the full judge workbench were outside this eight-page live sweep. A keyboard pass confirmed the /verify Tab order (skip link, brand, navigation, theme, select, textarea, submit) and the results expander opening/closing with Enter. Screen-reader, zoom and contrast behavior across every route still need a full manual audit before claiming conformance.

### Improvements in this review cycle

- Public participant self-signup at `/signup/`, with normal-account permissions; judge invitations and assignments remain separate.
- Judge `Score.comment` edits captured in both sides of `ScoreAudit` snapshots.
- Public `/verify` and standalone `verify.py` with distinct claims for certificates, receipts and HMAC records; the offline command checks Ed25519 and can compare a trusted organizer key.
- Published standings row expander for aggregate raw-versus-normalized math and rank movement, without individual judge details.
- Public scoring coverage counts on results: eligible canonical non-draft projects, projects with at least one valid weighted score, and unscored projects. Ranks exclude unscored projects; these counts do not prove equal judging coverage or fairness.
- Public results methodology panel shows the event rubric weights, per-judge centering and clamping formula, zero-spread fallback and tie policy, with sparse-judging and statistical-fairness caveats. It reveals no individual judge values or identities.
- Organizer-only vote activity panel at `/organizer/vote-signals` showing signals, not verdicts: retained attempt frequency, shared-IP actor counts, and accepted vote/cast-audit count differences. No IPs, actor keys, voter identities or receipts are shown on that panel.

Offline Docker cold boot remains a separate proof step. Do not treat the independent reviewer’s probes or the official checker as a security audit.

## Current routes

- Bulk project data: organizer-only `GET /organizer/projects.csv` exports up to 5000 active-event projects; `POST /organizer/projects/import` accepts a UTF-8 CSV body with the legacy six-column header `project_slug,title,summary,repo_url,team_slug,track_slug` or the complete enriched export header adding `thumbnail_url,demo_video_url,live_url,gallery_images_json,tags_json,custom_answers_json`, 1-500 rows, up to 1 MB. The JSON columns preserve arrays and answers; imports validate URLs, caps and active-event question keys. It creates projects only while submissions are open and results unpublished. Team and track slugs must already belong to the active event; duplicate slugs reject the entire batch. This does not migrate judges, scores, votes or users.

- Public gallery: `GET /projects`, with `q` title search and `track` slug filter; project detail and moderated comments at `GET /projects/<slug>`. Only nondraft, canonical projects appear. Select an active event before demonstrating multiple events; the gallery currently falls back to the oldest event if none is selected.
- Public participant signup: `GET/POST /signup/` creates a normal user account with no event role; judge roles still require a separate organizer invite, and assignments remain organizer-controlled. Login: `/login/`. Event and team setup: `/events/new`, organizer-only `POST /events/select` with form field `event=<slug>`, `/teams/new`, `/teams/<slug>/invite`, `/join/<token>`. The selected event is global and determines gallery, submissions, judging and public participation. Ballot, results and moderation require an active event. A few routes fall back to the oldest event when none is selected.
- Submission: `/projects/new`; a second POST from the team edits its canonical project before the deadline.
- Judging: assignment-scoped `/judge/console` (light first, persistent manual dark switch, server-confirmed autosave), `/organizer/judges/invite`, `/judge/accept/<token>`, `/organizer/assign`, `/judge/assignments`, `/judge/score/<project_slug>`, `/api/judge/scores`.
- Organizer vote activity signals: `GET /organizer/vote-signals` is private, event-scoped and aggregate-only; counts of retained vote attempts, shared-network patterns and audit/accepted-row differences are signals, not fraud verdicts.
- Organizer data: `GET /organizer/overview` renders the active event overview; `GET /organizer/results?view=html` renders a private standings table, while `/organizer/results` remains JSON. `/organizer/rubric`, `/organizer/results`, `/organizer/audit`, `/organizer/publish`, `/api/export.csv`. `GET /organizer/vote-audit` is superuser-only and can select a historical event with `?event=<slug>`; `POST /organizer/comments/<id>/hide` hides a public comment.
- Results explainer: each published `/results` row expands to show aggregate raw and normalized means, judge count, raw and normalized ranks, and rank movement. No individual judge identity, score or comment is exposed.
- Community participation: `GET /ballot` renders an authenticated voter's stable randomized eligible-project order while voting is open; `POST /vote` records one vote per account per event and returns a receipt. `GET /projects/<slug>` shows comments; authenticated `POST` accepts them while voting is open. `GET /results` exposes aggregate standings only after voting has closed **and** the organizer has published. `GET /receipt/<secret>` checks a receipt only after that same release gate; the receipt is a bearer capability, and any holder of it can use `/receipt/<secret>/proof` to learn the selected project after release. Keep the secret private.
- Partial JSON API: see `API.md`; project and published standings reads are public, judge assignment reads require a bearer token. Issuance/revocation require an authenticated session and CSRF. This is not complete REST.
- Participation record snapshot: organizer-only issue after published voting close, public verify if `RECORD_SIGNING_KEY` is set; this is not a certificate. See `PARTICIPATION-RECORDS.md`.
- Results-published webhook: operator-configured HTTPS callback queued on first publication, delivered by a separate management command, with HMAC body signature and organizer-only attempt status. See `WEBHOOKS.md`; this is one event type, not full webhook coverage.
- Public verification page: `GET/POST /verify` checks a pasted signed certificate JSON against its Ed25519 signature and this site's published issuance, an accepted vote receipt after results release, or a numeric HMAC participation-record ID using the site-held key. These are distinct claims, not proof of overall fairness. `python verify.py certificate.json --trusted-public-key <trusted-base64url-key>` checks the certificate signature offline with only `cryptography`; without a separately trusted key, issuer identity remains unverified.
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

Loopback SMTP delivery is covered by `test_smtp_delivery.py` using a local `aiosmtpd` server: code delivery, redemption and ballot casting run against the real Django SMTP backend. This is not proof of an external provider or production mail delivery. Next: external SMTP operations proof; expand the read-only `/api/v1` slice into complete REST and webhook coverage beyond one results-published callback; a judge-facing certificate distribution UI. The HMAC record snapshot is not a certificate; see `PARTICIPATION-RECORDS.md`. Portable Ed25519 JSON certificate issuance is a separate tested slice with key-pinning limits in `CERTIFICATES.md`. An organizer-scoped CSV project import/export slice is available at `/organizer/projects/import` and `/organizer/projects.csv`, with organizer lifecycle CSV snapshots now available; read-only export is not a full migration or import facility. Complete a Docker-capable network-off cold run using the packaged image archive, record its checker output, and link the five-minute event-lifecycle demo video. These are planned deliverables, not shipped tier claims. Keep `.dogfood.toml` at T1/T2 until a later tier is finished and independently checked.

The repository is private during the build. Publication needs a separate review of repository contents and demo credentials. Freeze: Tuesday 29 September 2026, 18:00 UTC (23:30 IST), per https://dogfoodhack.com/ and https://dogfoodhack.com/spec/ checked 28 September 2026.

## Optional hosted UI preview

`preview.Dockerfile` and `preview-start.sh` provide an optional public preview alongside the unchanged local `docker compose up` path. It requires unique runtime `DJANGO_SECRET_KEY`, `RAPTORGATE_PUBLIC_PREVIEW=1`, `DJANGO_DEBUG=0`, `RAPTORGATE_PREVIEW_HOST=<exact service>.onrender.com`, and `DATABASE_URL` for a separate PostgreSQL database. The preview starts from a sanitized copy of the official fictional fixture: 41 project rows (40 canonical) and 126 score rows, with published results. It stores 30 unusable-password placeholder judge accounts solely to preserve score relations, no participant/admin logins, no sessions, no judge emails or score comments, and no fixture tokens. The preview shows the gallery, standings, coverage and ranking method for UI review, not live voting or scoring. Every write request returns 405; links to inactive vote/login/organizer pages are removed or redirected to the gallery. Do not run the fixture `seed_event` command or use `.dogfood.toml` demo cookies against the public preview. Free Render sleeps when idle and its free PostgreSQL expires in 30 days, without backups. The hosted preview does not replace the offline, seeded, one-command submission requirement.
