# Threat model

Reviewed source at the 8792fff source baseline. This document distinguishes implemented checks from remaining risks. Scope is the local fixture-backed portal; it has no community voting yet. Requirement: https://dogfoodhack.com/ (optional Threat Model bonus) and https://dogfoodhack.com/spec/.

## Assets and boundaries

Private judge scores/comments, assignments, unpublished standings, team invites, submissions, demo sessions, and organizer CSV cross browser-to-server, role-to-role, and database-to-public-output boundaries. A URL or client-supplied judge identifier is not authority. A superuser can read and publish results; a judge should see only their own event rows, and participants should not see judge scores.

| Attack | Current source control | Remaining risk |
| --- | --- | --- |
| Judge guesses peer score URL | `judge_scores` derives the judge from the authenticated user; peer `judge` parameter returns 403. Acceptance report passes this probe. | Audit other future score endpoints on each change. |
| Participant reads scores or exports CSV | No judge role returns 403 on score API; CSV requires `is_superuser`. | Other organizer data routes need sustained negative tests. |
| Judge scores outside track, assignment or own team | Assignment checks track and own-team; score write checks current track membership, assignment and own-team again. | Database constraints do not independently bind assignment's event/track. |
| Deadline bypass on submission | Submission writes lock team/event and compare server UTC time, including edit POST. | There is no full draft flow; other future write routes must check closure. The public gallery, scoring and standings exclude draft projects, but test draft lifecycle before enabling it. |
| Stolen invite | Team/judge tokens use random generation and seven-day expiry; judge acceptance consumes token. | Team join token remains reusable until expiry; anyone holding it can join while authenticated. No revocation/abuse log shown. |
| Judge collusion or score alteration | `ScoreAudit` keeps previous/current criteria and editor/time for writes; organizer-only audit route. | Comments' previous values are not audited; no tamper-evident log or collusion detection. |
| Spreadsheet formula injection | CSV prepends apostrophe to risky string cell prefixes, even after whitespace. | Verify behavior in target spreadsheet clients; New regression tests cover formula prefixes in the exported text and JSON score criteria; spreadsheet-client behavior still needs verification. |
| Fixture or demo-secret leakage | Compose binds loopback; CSRF and session middleware configured. | Known fixed session cookies, static Django key and DB password in repo are unsafe for public deployment. Never expose this stack directly. |
| Submission scraping | Gallery is intentionally public. | No observed rate limit or scraping controls. |
| Ballot stuffing/Sybil voting | No voting implementation. | T3 threat remains out of scope until voting exists. |

## Tests and residual risk

Reviewed tests cover peer/participant denial, off-track and own-team assignment, unauthorized score write, expiry of invitations, submission close on edit, and basic organizer authorization. The checked-in checker shows seven PASS lines but is narrower than this model. No independent live penetration or clean offline deployment test was performed for this draft. Future work: add rate limits, session/secret configuration, event-scoped database constraints, audit of comments, published-results access rules, backup/restore and abuse monitoring. This written model does not by itself establish the optional +3 bonus; defenses and limitations must match the final submitted commit.
