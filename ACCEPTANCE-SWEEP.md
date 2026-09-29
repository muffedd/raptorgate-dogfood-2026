# Local browser acceptance sweep

On September 29, 2026, the local Django instance was exercised in headless Chrome against a separate seeded PostgreSQL database. The seeded `evt_01` event was kept for the official checker; a temporary open `sweep-e2e-c85036b` event was created and selected in the **local test database only** for submission and judging. This is not a Docker/network-off proof and does not change the public preview or official fixture.

| Flow | Browser check | Result |
| --- | --- | --- |
| Participant account | Signup, login, redirect to `/projects` | PASS after redirect fix |
| Team | Create from form, redirect to submission | PASS after browser-form fix; JSON `Accept` still returns 201 JSON |
| Submission | Draft persists after reload, publish, gallery detail | PASS |
| Organizer | Create/select open event, overview, batch assign one eligible project | PASS; assignment confirmed in database |
| Exports | Teams, submissions, assignments, scores, results CSV before assignments, after assignment, after scoring | PASS; organizer-scoped 200 and CSV headers; scored rows confirmed |
| Judge | Assignment queue, three criteria autosave, score persistence after reload | PASS |
| Judge next | Two assigned projects, score second, change first, Save and next | PASS; navigation and saved score confirmed |
| Gallery and widget | Project visible; widget light/dark queries | PASS |
| Themes/viewport | Signup, login, team, submission, gallery, judge, organizer overview and results in light/dark at 1440 and 390px; widget both themes at both widths | PASS; captured screenshots were visually inspected, and no page-level horizontal overflow was detected |
| Official checker | Three T1 and four T2 literal lines on the seeded `evt_01` database | PASS; see `acceptance-report.txt` |

This is browser-flow and first-viewport coverage, not a claim that every below-the-fold panel or responsive state was audited. The visual captures showed the intended controls and content in the first viewport. A local checker run initially failed two probes because the test had selected the temporary open event in a reused database; selecting the fixture event again restored all seven PASS. That failure did not reflect a source-code regression. The independent cold-boot proof applies only to the earlier `4cd5a399` source tree; see `packaging/README.md` for its bounds and harness caveats.
