# Pairwise judging: deferred mode

The shipped judging mode is the three-criterion rubric. Pairwise comparison is not wired into scoring or standings. It should not be advertised as complete.

A credible pairwise mode needs more than a button to choose A over B: eligible comparison-pair scheduling within each track, assignment and conflict checks for both projects, enough connected comparisons to rank all entrants, tie/skip handling, an auditable per-judge record, and a specified aggregation method. Feeding a small or disconnected set of pairwise wins into the current normalized rubric average would silently change rankings without a defensible scale. It would also affect published results and CSV/API contracts.

A future implementation should keep pairwise decisions in separate, event-scoped records. The organizer should choose the judging mode before any assignments or scores, and switching modes should be blocked once judging starts. The pairwise results page must show comparison coverage and unranked projects, and publication should refuse to call an incomplete comparison graph a full ranking. Test cross-event, off-track, same-team and double-submit boundaries as well as ties and disconnected components. The existing rubric standings must remain unchanged until a full alternate ranking method is reviewed.
