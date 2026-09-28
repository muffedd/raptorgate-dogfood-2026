"""Regression tests for event/track cross-scope leaks.

Every reader/writer in views.py resolves its scope through active_event()
(the first event) plus explicit event/track filters. These tests build a
second event with identically shaped data and verify that neither data nor
permissions cross the event or track boundary.

Three defects are exposed and marked xfail-free on purpose: they FAIL until
the app is fixed, because each one demonstrates a genuine cross-scope leak.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from eventhub.models import (
    Assignment,
    Event,
    Judge,
    Project,
    Score,
    ScoreAudit,
    Team,
    Track,
)

CRITERIA = {"functionality": 4, "quality": 3, "innovation": 5}


class CrossEventScopeTests(TestCase):
    """Lock correct behavior: active-event scoping on every read/write path."""

    @classmethod
    def setUpTestData(cls):
        past = timezone.now() - timedelta(days=1)
        # evt_a is created first, so active_event() resolves to it.
        cls.event_a = Event.objects.create(
            slug="evt-a", title="Event A", submissions_close=past
        )
        cls.event_b = Event.objects.create(
            slug="evt-b", title="Event B", submissions_close=past
        )
        cls.track_a = Track.objects.create(event=cls.event_a, slug="trk", name="Track A")
        cls.track_b = Track.objects.create(event=cls.event_b, slug="trk", name="Track B")
        cls.team_a = Team.objects.create(event=cls.event_a, slug="team", name="Team A")
        cls.team_b = Team.objects.create(event=cls.event_b, slug="team", name="Team B")
        cls.project_a = Project.objects.create(
            event=cls.event_a, team=cls.team_a, track=cls.track_a,
            slug="proj", title="Alpha Active Project",
        )
        cls.project_b = Project.objects.create(
            event=cls.event_b, team=cls.team_b, track=cls.track_b,
            slug="proj-b", title="Beta Other Event Project",
        )
        User = get_user_model()
        cls.organizer = User.objects.create_superuser(
            username="scope-org", email="scope-org@example.org", password="x"
        )
        cls.both_user = User.objects.create_user(username="both-judge")
        cls.other_only_user = User.objects.create_user(username="other-only-judge")
        # Same person holds a judge role in both events.
        cls.judge_a = Judge.objects.create(event=cls.event_a, slug="jdg", user=cls.both_user)
        cls.judge_b = Judge.objects.create(event=cls.event_b, slug="jdg", user=cls.both_user)
        cls.judge_a.tracks.add(cls.track_a)
        cls.judge_b.tracks.add(cls.track_b)
        cls.other_judge = Judge.objects.create(
            event=cls.event_b, slug="jdg-b-only", user=cls.other_only_user
        )
        cls.score_a = Score.objects.create(
            judge=cls.judge_a, project=cls.project_a, criteria=CRITERIA
        )
        cls.score_b = Score.objects.create(
            judge=cls.judge_b, project=cls.project_b, criteria=CRITERIA
        )
        # A row the DB permits but the views must never surface: judge from
        # event A scoring a project from event B.
        cls.cross_score = Score.objects.create(
            judge=cls.judge_a,
            project=cls.project_b,
            criteria={"functionality": 1, "quality": 1, "innovation": 1},
        )
        cls.assignment_a = Assignment.objects.create(judge=cls.judge_a, project=cls.project_a)
        cls.assignment_b = Assignment.objects.create(judge=cls.judge_b, project=cls.project_b)
        ScoreAudit.objects.create(score=cls.score_a, editor=cls.organizer, current=CRITERIA)
        ScoreAudit.objects.create(score=cls.score_b, editor=cls.organizer, current=CRITERIA)

    def test_gallery_shows_only_active_event_projects(self):
        response = self.client.get("/projects")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Active Project")
        self.assertNotContains(response, "Beta Other Event Project")

    def test_gallery_search_cannot_reach_other_event(self):
        response = self.client.get("/projects", {"q": "Beta"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Beta Other Event Project")

    def test_judge_scores_scoped_to_active_event(self):
        self.client.force_login(self.both_user)
        response = self.client.get("/api/judge/scores")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["judge"], "jdg")
        # Only the active-event row may appear: not the event-B score and
        # not the cross-event row (event-A judge x event-B project).
        self.assertEqual([row["project"] for row in payload["scores"]], ["proj"])

    def test_judge_only_in_other_event_gets_403(self):
        self.client.force_login(self.other_only_user)
        self.assertEqual(self.client.get("/api/judge/scores").status_code, 403)
        self.assertEqual(self.client.get("/judge/assignments").status_code, 403)

    def test_judge_assignments_scoped_to_active_event(self):
        self.client.force_login(self.both_user)
        response = self.client.get("/judge/assignments")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["assignments"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Alpha Active Project")

    def test_export_csv_excludes_other_event_rows(self):
        self.client.force_login(self.organizer)
        response = self.client.get("/api/export.csv")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # Event A has exactly one legitimate score row; the event-B row and
        # the cross-event row share the same project slug "proj" and team
        # name shape, so count rows instead of matching slugs.
        rows = [line for line in body.splitlines() if line.strip()]
        self.assertEqual(len(rows), 2)  # header + score_a only
        self.assertNotIn("proj-b", body)
        self.assertNotIn("Beta Other Event Project", body)
        self.assertNotIn("Team B", body)

    def test_results_standings_exclude_other_event(self):
        self.client.force_login(self.organizer)
        response = self.client.get("/organizer/results")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["standings"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Alpha Active Project")
        # 3 identical 4/3/5 scores for project_b would skew normalization if
        # the cross-event row leaked into judge stats: judge_a's spread would
        # no longer be zero and the normalized value would drift off 3.0.
        self.assertEqual(rows[0]["normalized"], 3.0)

    def test_audit_log_scoped_to_active_event(self):
        self.client.force_login(self.organizer)
        response = self.client.get("/organizer/audit")
        self.assertEqual(response.status_code, 200)
        entries = response.json()["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["judge"], "jdg")

    def test_assign_judge_rejects_slugs_from_other_event(self):
        self.client.force_login(self.organizer)
        # Judge slug that exists only in event B.
        self.assertEqual(
            self.client.post(
                "/organizer/assign", {"judge": "jdg-b-only", "project": "proj"}
            ).status_code,
            404,
        )
        # A project slug that exists only in event B must not resolve.
        self.assertEqual(
            self.client.post(
                "/organizer/assign", {"judge": "jdg", "project": "proj-b"}
            ).status_code,
            404,
        )

    def test_cross_event_track_membership_grants_nothing(self):
        # A judge whose only track membership is a track from another event
        # must not become assignable inside the active event.
        User = get_user_model()
        user = User.objects.create_user(username="foreign-track-judge")
        judge = Judge.objects.create(event=self.event_a, slug="foreign", user=user)
        judge.tracks.add(self.track_b)  # track from the other event
        self.client.force_login(self.organizer)
        response = self.client.post(
            "/organizer/assign", {"judge": "foreign", "project": "proj"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Assignment.objects.filter(judge=judge).exists())

    def test_score_project_slug_from_other_event_is_404(self):
        Project.objects.create(
            event=self.event_b, team=self.team_b, track=self.track_b,
            slug="b-score-target", title="B target",
        )
        self.client.force_login(self.both_user)
        response = self.client.post(
            "/judge/score/b-score-target",
            {"functionality": "4", "quality": "3", "innovation": "5"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            Score.objects.filter(project__slug="b-score-target", judge=self.judge_a).exists()
        )

    def test_team_invite_slug_from_other_event_is_404(self):
        Team.objects.create(event=self.event_b, slug="b-team", name="B team")
        self.client.force_login(self.other_only_user)
        self.assertEqual(self.client.post("/teams/b-team/invite").status_code, 404)


class TrackScopeLeakTests(TestCase):
    """Defect: score_project checks only the Assignment row, never the
    judge's track membership. assign_judge enforces 'Judge is not assigned
    to this track' at grant time, but nothing re-checks the invariant, so a
    stale assignment lets a judge keep scoring a project that has left (or
    was never in) their tracks."""

    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(
            slug="open-evt", title="Open",
            submissions_close=timezone.now() + timedelta(days=1),
        )
        cls.track_in = Track.objects.create(event=cls.event, slug="in", name="In scope")
        cls.track_out = Track.objects.create(event=cls.event, slug="out", name="Out of scope")
        cls.team = Team.objects.create(event=cls.event, slug="team", name="Team")
        User = get_user_model()
        cls.organizer = User.objects.create_superuser(
            username="track-org", email="track-org@example.org", password="x"
        )
        cls.member = User.objects.create_user(username="track-member")
        cls.team.members.add(cls.member)
        cls.judge_user = User.objects.create_user(username="track-judge")
        cls.judge = Judge.objects.create(event=cls.event, slug="jdg", user=cls.judge_user)
        cls.judge.tracks.add(cls.track_in)

    def _submit(self, track):
        self.client.force_login(self.member)
        return self.client.post(
            "/projects/new",
            {
                "title": "Movable project",
                "summary": "s",
                "repo_url": "https://example.org/r",
                "track": str(track.pk),
            },
        )

    def _assign_and_score(self, slug):
        self.client.force_login(self.organizer)
        self.assertEqual(
            self.client.post("/organizer/assign", {"judge": "jdg", "project": slug}).status_code,
            200,
        )
        self.client.force_login(self.judge_user)
        self.assertEqual(
            self.client.post(
                "/judge/score/" + slug,
                {"functionality": "4", "quality": "3", "innovation": "5"},
            ).status_code,
            200,
        )

    def test_score_blocked_after_project_leaves_judges_track(self):
        response = self._submit(self.track_in)
        self.assertEqual(response.status_code, 201)
        slug = response.json()["project"]
        self._assign_and_score(slug)
        # Team moves the project to a track this judge is not on.
        self.assertEqual(self._submit(self.track_out).status_code, 200)
        self.client.force_login(self.judge_user)
        response = self.client.post(
            "/judge/score/" + slug,
            {"functionality": "5", "quality": "5", "innovation": "5"},
        )
        self.assertEqual(
            response.status_code,
            403,
            "judge edited a score on a project that moved to a track they "
            "are not assigned to: the stale Assignment bypasses the track "
            "check that assign_judge enforces",
        )

    def test_score_blocked_after_track_membership_revoked(self):
        response = self._submit(self.track_in)
        self.assertEqual(response.status_code, 201)
        slug = response.json()["project"]
        self._assign_and_score(slug)
        # Organizer pulls the judge off the track (e.g. via admin); the
        # assignment row survives.
        self.judge.tracks.set([self.track_out])
        self.client.force_login(self.judge_user)
        response = self.client.post(
            "/judge/score/" + slug,
            {"functionality": "5", "quality": "5", "innovation": "5"},
        )
        self.assertEqual(
            response.status_code,
            403,
            "judge scored a project in a track they no longer belong to: "
            "score_project trusts the Assignment row and never re-checks "
            "judge.tracks",
        )


class CrossEventInviteHijackTests(TestCase):
    """Defect: invite_judge reuses the global 'invited:<email>' user account.
    If that account already exists (e.g. as a judge in another event), the
    new event's invite binds to the same identity, and accept_judge resets
    the shared account's password - so an organizer of the active event (who
    receives the accept token in the invite response) can take over an
    account that holds a judge role in a different event."""

    ORIGINAL_PASSWORD = "OriginalShared2026!"
    ATTACKER_PASSWORD = "Hijacked2026!"

    @classmethod
    def setUpTestData(cls):
        past = timezone.now() - timedelta(days=1)
        cls.event_a = Event.objects.create(
            slug="evt-active", title="Active", submissions_close=past
        )
        cls.event_b = Event.objects.create(
            slug="evt-other", title="Other", submissions_close=past
        )
        cls.track_a = Track.objects.create(event=cls.event_a, slug="trk", name="Track A")
        track_b = Track.objects.create(event=cls.event_b, slug="trk", name="Track B")
        User = get_user_model()
        cls.organizer = User.objects.create_superuser(
            username="hijack-org", email="hijack-org@example.org", password="x"
        )
        # Account created by an earlier invite flow for the OTHER event.
        cls.shared_user = User.objects.create_user(
            username="invited:shared@example.org", email="shared@example.org"
        )
        cls.shared_user.set_password(cls.ORIGINAL_PASSWORD)
        cls.shared_user.save()
        cls.judge_b = Judge.objects.create(
            event=cls.event_b, slug="jdg-b", user=cls.shared_user
        )
        cls.judge_b.tracks.add(track_b)

    def test_invite_for_active_event_must_not_reset_other_event_account(self):
        self.client.force_login(self.organizer)
        response = self.client.post(
            "/organizer/judges/invite",
            {"email": "shared@example.org", "tracks": ["trk"]},
        )
        if response.status_code == 201:
            # Current behavior: the invite binds to the pre-existing account.
            judge_a = Judge.objects.get(event=self.event_a, user=self.shared_user)
            self.assertEqual(judge_a.user_id, self.judge_b.user_id)
            # Whoever holds the returned token can reset the shared password.
            self.client.logout()
            accept = self.client.post(
                response.json()["accept_path"],
                {"password": self.ATTACKER_PASSWORD, "confirm": self.ATTACKER_PASSWORD},
            )
            self.assertEqual(accept.status_code, 200)
        # The invariant either way: credentials of an account that already
        # holds a judge role in another event must survive an invite flow
        # for the active event.
        self.shared_user.refresh_from_db()
        self.assertTrue(
            self.shared_user.check_password(self.ORIGINAL_PASSWORD),
            "accepting an invite for the active event overwrote the password "
            "of an account that is a judge in another event: the organizer "
            "receives the accept token and can seize that identity",
        )
