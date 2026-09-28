"""T3 adversarial lane: voting policy modes, window boundaries, CSRF, forgery,
ballot permutation fairness, and the no-slug inactive-event fallback."""
import re
from datetime import timedelta
from django.test import Client, TestCase
from django.utils import timezone
from freezegun import freeze_time
from eventhub.models import Event, PublicVote, PublicVoteAudit
from eventhub.ranking import standings
from .t3_helpers import make_event, make_organizer, make_project, make_user


class VotingPolicyModeTests(TestCase):
    def setUp(self):
        self.event = make_event("t3-modes")
        self.project = make_project(self.event)
        self.voter = make_user("voter")

    def test_unimplemented_modes_fail_closed_for_authenticated_voter(self):
        # open/email verification flows do not exist yet; both must reject, not fall open.
        for mode in ("open", "email"):
            Event.objects.filter(pk=self.event.pk).update(voting_access=mode)
            self.client.force_login(self.voter)
            self.assertEqual(self.client.get("/ballot", {"event": "t3-modes"}).status_code, 403, mode)
            resp = self.client.post("/vote", {"event": "t3-modes", "project": "proj"})
            self.assertEqual(resp.status_code, 403, mode)
            self.assertEqual(PublicVote.objects.count(), 0, mode)

    def test_unimplemented_modes_fail_closed_for_anonymous(self):
        for mode in ("open", "email"):
            Event.objects.filter(pk=self.event.pk).update(voting_access=mode)
            self.assertEqual(self.client.get("/ballot", {"event": "t3-modes"}).status_code, 403, mode)
            self.assertEqual(self.client.post("/vote", {"event": "t3-modes", "project": "proj"}).status_code, 403, mode)

    def test_authenticated_mode_rejects_anonymous(self):
        self.assertEqual(self.client.get("/ballot", {"event": "t3-modes"}).status_code, 403)
        self.assertEqual(self.client.post("/vote", {"event": "t3-modes", "project": "proj"}).status_code, 403)

    def test_forged_session_cookie_is_not_a_voter(self):
        self.client.cookies.load({"sessionid": "forged-session-token-12345"})
        resp = self.client.post("/vote", {"event": "t3-modes", "project": "proj"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(PublicVote.objects.count(), 0)


class WindowBoundaryTests(TestCase):
    def setUp(self):
        self.event = make_event("t3-window")
        self.project = make_project(self.event)
        self.voter = make_user("voter")
        self.other = make_user("other")
        self.client.force_login(self.voter)

    def test_vote_accepted_exactly_at_open_and_rejected_exactly_at_close(self):
        Event.objects.filter(pk=self.event.pk).update(
            voting_opens=timezone.now() + timedelta(hours=1),
            voting_closes=timezone.now() + timedelta(hours=2))
        opens = Event.objects.get(pk=self.event.pk).voting_opens
        closes = Event.objects.get(pk=self.event.pk).voting_closes
        with freeze_time(opens):  # opens is inclusive
            self.assertEqual(self.client.post("/vote", {"event": "t3-window", "project": "proj"}).status_code, 201)
        with freeze_time(opens - timedelta(seconds=1)):
            self.assertEqual(self.client.get("/ballot", {"event": "t3-window"}).status_code, 403)
        self.client.force_login(self.other)
        with freeze_time(closes - timedelta(seconds=1)):
            self.assertEqual(self.client.post("/vote", {"event": "t3-window", "project": "proj"}).status_code, 201)
        self.client.force_login(make_user("late"))
        with freeze_time(closes):  # closes is exclusive
            self.assertEqual(self.client.post("/vote", {"event": "t3-window", "project": "proj"}).status_code, 403)
            self.assertEqual(self.client.get("/ballot", {"event": "t3-window"}).status_code, 403)
        self.assertEqual(PublicVote.objects.filter(event=self.event).count(), 2)

    def test_missing_window_fails_closed(self):
        Event.objects.filter(pk=self.event.pk).update(voting_opens=None, voting_closes=None)
        self.assertEqual(self.client.get("/ballot", {"event": "t3-window"}).status_code, 403)
        self.assertEqual(self.client.post("/vote", {"event": "t3-window", "project": "proj"}).status_code, 403)


class VoteForgeryTests(TestCase):
    def setUp(self):
        self.event = make_event("t3-forge")
        self.project = make_project(self.event)
        self.canonical = make_project(self.event, "canonical")
        self.dup = make_project(self.event, "dup", duplicate_of=self.canonical)
        self.draft = make_project(self.event, "draft", draft=True)
        self.voter = make_user("voter")
        self.client.force_login(self.voter)

    def test_draft_and_duplicate_candidates_reject_votes_and_stay_off_ballot(self):
        for slug in ("dup", "draft"):
            resp = self.client.post("/vote", {"event": "t3-forge", "project": slug})
            self.assertEqual(resp.status_code, 404, slug)
        page = self.client.get("/ballot", {"event": "t3-forge"})
        self.assertContains(page, "Project")
        self.assertNotContains(page, ">dup<")
        self.assertEqual(PublicVote.objects.count(), 0)

    def test_unknown_project_slug_rejected(self):
        self.assertEqual(self.client.post("/vote", {"event": "t3-forge", "project": "nope"}).status_code, 404)

    def test_cross_event_project_slug_rejected(self):
        other = make_event("t3-foreign", active=False)
        make_project(other, "foreign")
        self.assertEqual(self.client.post("/vote", {"event": "t3-forge", "project": "foreign"}).status_code, 404)
        self.assertEqual(PublicVote.objects.count(), 0)

    def test_get_on_vote_endpoint_rejected(self):
        self.assertEqual(self.client.get("/vote", {"event": "t3-forge", "project": "proj"}).status_code, 405)
        self.assertEqual(PublicVote.objects.count(), 0)

    def test_receipts_are_unique_and_unpredictable_shape(self):
        self.assertEqual(self.client.post("/vote", {"event": "t3-forge", "project": "proj"}).status_code, 201)
        first = PublicVote.objects.get().receipt
        voter2 = make_user("voter2")
        self.client.force_login(voter2)
        self.assertEqual(self.client.post("/vote", {"event": "t3-forge", "project": "canonical"}).status_code, 201)
        second = PublicVote.objects.exclude(receipt=first).get().receipt
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{32}$")
        self.assertRegex(second, r"^[0-9a-f]{32}$")

    def test_csrf_required_on_vote_post(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.voter)
        resp = csrf_client.post("/vote", {"event": "t3-forge", "project": "proj"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(PublicVote.objects.count(), 0)
        csrf_client.get("/ballot", {"event": "t3-forge"})
        token = csrf_client.cookies["csrftoken"].value
        resp = csrf_client.post("/vote", {"event": "t3-forge", "project": "proj"},
                                HTTP_X_CSRFTOKEN=token)
        self.assertEqual(resp.status_code, 201)


class NoActiveEventFailClosedTests(TestCase):
    """Public callers may not switch into a non-active event by guessing its slug;
    omitting the slug must not silently select a non-active event either."""

    def setUp(self):
        self.event = make_event("t3-inactive", active=False, published=True)
        self.project = make_project(self.event)
        self.voter = make_user("voter")
        self.client.force_login(self.voter)

    def test_ballot_does_not_fall_back_to_inactive_event(self):
        self.assertIn(self.client.get("/ballot").status_code, (403, 404))

    def test_vote_does_not_fall_back_to_inactive_event(self):
        resp = self.client.post("/vote", {"project": "proj"})
        self.assertIn(resp.status_code, (403, 404))
        self.assertEqual(PublicVote.objects.count(), 0)
        self.assertEqual(PublicVoteAudit.objects.count(), 0)

    def test_project_detail_does_not_fall_back_to_inactive_event(self):
        self.assertEqual(self.client.get("/projects/proj").status_code, 404)

    def test_results_do_not_fall_back_to_inactive_event(self):
        Event.objects.filter(pk=self.event.pk).update(voting_closes=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.get("/results").status_code, 404)


class BallotFairnessTests(TestCase):
    def setUp(self):
        self.event = make_event("t3-ballot")
        self.projects = [make_project(self.event, f"p{i:02d}", f"Project {i}") for i in range(8)]
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def _order(self, user):
        self.client.force_login(user)
        page = self.client.get("/ballot", {"event": "t3-ballot"}).content.decode()
        positions = {}
        for project in self.projects:
            marker = f'name="project" value="{project.slug}"'
            self.assertIn(marker, page)
            positions[project.slug] = page.index(marker)
        return tuple(sorted(positions, key=positions.get))

    def test_per_voter_order_is_stable_across_refreshes(self):
        self.assertEqual(self._order(self.alice), self._order(self.alice))

    def test_order_is_a_full_permutation_of_eligible_projects(self):
        order = self._order(self.alice)
        self.assertEqual(sorted(order), sorted(p.slug for p in self.projects))

    def test_order_varies_between_voters(self):
        # 8! = 40320 permutations; an HMAC-keyed shuffle colliding is negligible.
        self.assertNotEqual(self._order(self.alice), self._order(self.bob))

    def test_ballot_order_does_not_leak_score_ranking(self):
        organizer = make_organizer("judge-owner-xqz")
        from eventhub.models import Judge, Score
        judge = Judge.objects.create(event=self.event, slug="j1", user=organizer)
        for i, project in enumerate(self.projects):  # p00 strongest .. p07 weakest
            Score.objects.create(judge=judge, project=project,
                                 criteria={"functionality": 5, "quality": 5 - min(i, 4),
                                           "innovation": max(1, 5 - i)})
        ranking = [row["project"] for row in standings(self.event)]
        ballot_order = list(self._order(self.alice))
        self.assertNotEqual(ballot_order, ranking)
        page = self.client.get("/ballot", {"event": "t3-ballot"}).content.decode()
        self.assertNotIn("normalized", page)
        self.assertNotIn("j1", page)
        self.assertNotIn(organizer.username, page)
