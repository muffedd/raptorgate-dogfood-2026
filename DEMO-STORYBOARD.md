# Five-minute demo storyboard

For the reviewed RaptorGate source at the 8792fff source baseline. This is a shot plan, not a video. Do not imply that a JSON response is a finished screen or that `published=true` makes results public. Official brief: https://dogfoodhack.com/.

| Time | Live action | Honest narration |
| --- | --- | --- |
| 0:00-0:35 | Show cached-image setup, `docker compose up`, then `http://localhost:8080/projects`. | Explain that a clean machine first needs online image/dependency downloads; subsequent boot runs migrations and seeds if there is no event. Do not call a fresh boot offline-tested unless you perform that test. |
| 0:35-1:10 | Gallery search/filter; point out one official fixture project and hidden duplicate. | There are 41 imported project rows, one duplicate excluded from the gallery. |
| 1:10-1:50 | Show organizer event-creation POST and team/invite flow with a prepared *separate* open-event test database. | Current app always selects the first event, so a second event is not automatically active. If this setup cannot be shown end-to-end without swapping data, say so rather than staging a false lifecycle. |
| 1:50-2:25 | Show a team submission and in-place edit before close in an open-event test, then denial after close. | Source and tests cover the POST behavior; the official seeded event is already closed, so use a clean test setup and name it. No draft-save path exists. |
| 2:25-3:15 | Organizer invite/assign via API, judge score POST, judge A own-score GET; judge B peer URL gets 403. | These are backend checks, not finished judge screens. Avoid displaying private score comments to an unauthorized role. |
| 3:15-4:05 | Change the three rubric weights, inspect organizer standings and audit, export raw CSV. | Describe `0.4/0.35/0.25` defaults, mean-centered normalization and zero-variance neutral 3.0; note the sparse-review caveat. The CSV is raw, not normalized. |
| 4:05-4:35 | Show organizer publication POST on closed event and returned flag. | No public results page exists. Do not call this a public publication walkthrough. |
| 4:35-5:00 | Show exact `acceptance-report.txt` and `.dogfood.toml`; close on limits. | Seven committed checker PASS lines; full UI, public results, community voting, bulk movement and video are not implemented at this source baseline. |

Pre-recording: run the same commit and local test data through this sequence, mask fixed demo cookies and passwords, and make cuts apparent. The required full event lifecycle is not currently demonstrable through a single active seeded event and complete UI; show the gap explicitly. Freeze: Tuesday 29 September 2026 at 18:00 UTC (23:30 IST), per https://dogfoodhack.com/ and https://dogfoodhack.com/spec/ checked 28 September.
