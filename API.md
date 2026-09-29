# JSON API slice

This is a narrow T4 API slice, not "API first" or a full REST representation of every screen. Existing `/api/judge/scores` and `/api/export.csv` still use authenticated session cookies. New `/api/v1` routes offer read-only public project/result data, explicit bearer tokens and scoped judge assignment reads. No bearer score write, organizer mutations, webhook subscription, or OpenAPI schema is shipped by this slice.

## First use

Log in through `/login/` in a browser before requesting a token. `POST /api/v1/tokens` uses that authenticated browser session and its CSRF token; a bearer token cannot bootstrap itself. The seeded first event is used if no organizer has selected an active event yet, matching the web routes. An organizer can choose another event with `POST /events/select`; `?event=` only verifies the selected/fallback event slug and does not switch events.

## Endpoints

| Method | Route | Access | Result |
| --- | --- | --- | --- |
| GET | `/api/v1/projects` | public | Up to 500 canonical, non-draft projects for the active event. Wrong `?event=` slug returns 404. |
| GET | `/api/v1/results` | public after voting close **and** publication | Aggregate standings only; no individual judge ballot. |
| POST | `/api/v1/tokens` | authenticated Django session + CSRF | Issues a 30-day token once; give it a `name` form field. Only the SHA-256 digest is stored. |
| POST | `/api/v1/tokens/<id>/revoke` | owning Django session + CSRF | Revokes one's own token. |
| GET | `/api/v1/judge/assignments` | `Authorization: Bearer <token>` for a judge in the active event | Assignment rows scoped to that judge and eligible projects. |

The token is a bearer secret: store it as carefully as a password. Token issuance returns `Cache-Control: no-store`; never paste tokens into logs or publish fixture credentials. Login, token issue/revoke, grading and organizer operations do not gain CSRF exceptions from this API. An invalid, expired, inactive-user or revoked token is denied with 401; a valid non-judge token gets 403. A missing event is 404. `?event=` cannot switch an API request to an inactive event. Token bearer use is local demo capability; the Compose HTTP listener is on `127.0.0.1`, not HTTPS. Do not expose it over the internet as-is.

The read routes are unversioned in their data schema despite `/v1` path naming; run the regression tests before changing field names. The source and tests are in `src/eventhub/api.py` and `src/eventhub/tests/test_api_slice.py`.

Additional read-only routes: `GET /api/v1/projects/<slug>` returns one eligible
public project, and `GET /api/v1/judge/scores` requires a valid bearer token
for the active event's judge and returns only that judge's eligible scores.
The latter rejects another judge's slug and sends `Cache-Control: no-store`.
This is still not UI parity for writes, organizer actions or comment moderation.
