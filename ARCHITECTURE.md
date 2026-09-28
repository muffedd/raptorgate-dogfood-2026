# Architecture

Reviewed source: private repository `muffedd/raptorgate-dogfood-2026`, the 8792fff source baseline. This describes source, not an independently run deployment.

## Process and storage

`docker-compose.yml` defines local PostgreSQL 16 Alpine and a Django web service bound to `127.0.0.1:8080`. `Dockerfile` uses Python 3.12 slim, installs `requirements.txt`, then starts `migrate`, `seed_event --if-empty`, and Django `runserver`. The database has a persistent named volume. The build and pull need downloaded images/packages first, so clean-checkout offline operation remains unverified. `src/portal/settings.py` configures sessions, CSRF middleware, UTC-aware time, PostgreSQL via `DATABASE_URL` (SQLite fallback outside Compose), and a static demo key supplied by Compose. `src/portal/urls.py` maps templates and JSON endpoints into `src/eventhub/views.py`; business records are in `src/eventhub/models.py`, ranking in `src/eventhub/ranking.py`.

## Request boundaries

The active event is `Event.objects.order_by('id').first()`. All user-facing workflows target that first event. Creating another event does not switch the active one; this limits the advertised multi-event workflow. Gallery reads canonical projects (not duplicates) and filters by title/track. Submission takes a transaction and team row lock, checks team membership and the server's UTC time against the event close date, and creates or edits that team's canonical project. The project form restricts track to the active event. Team and judge invite tokens expire after seven days; judge acceptance consumes its token and sets a password.

The judge scores API derives the judge from the authenticated user and active event, and denies a mismatched `judge` query parameter. Organizer-only endpoints require `is_superuser` for assignment, rubric, results, audit, publication and CSV, and event creation also requires `is_superuser`. Judge assignment checks track membership and own-team conflicts; score writes require an assignment and current judge-track membership, and reject own-team scoring. Audit records are written on score creation/edit. The checked-in acceptance report records all seven T1/T2 probes as PASS, including peer-score and participant denial. These probes do not cover every path or prove production security.

## Results and export

`/organizer/results` returns raw and centered normalized standings to a superuser; `/organizer/publish` flips `published` after submissions close. There is no public results endpoint in the reviewed URL map. CSV export returns raw score criteria to a superuser; it is not an export at every workflow stage. The JSON rubric endpoint permits positive finite weights summing to 1 for three fixed criteria. A browser-facing organizer and judge console is incomplete.

## Operational limits

The seed runs only when **no event** exists and otherwise leaves the database rows alone while reprinting the fixed fixture session headers; manual seeding upserts official fixture records and can overwrite those rows. Fixed local demo sessions and Compose credentials are not production-safe. `runserver` is a development server, not a production deployment. The current tree lacks a complete UI, public publication view, T3/T4 workflows and video. Before submission, run clean offline boot and tests, capture results and update this document if implementation changes.

Official requirements: https://dogfoodhack.com/spec/ and https://dogfoodhack.com/.
