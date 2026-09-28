"""T3 adversarial lane: public results gating, judge-identity leakage,
draft/duplicate exclusion, and organizer audit scoping."""
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, PublicVote, Score
from .t3_helpers import make_event, make_organizer, make_project, make_user


class ResultsGatingTests(TestCase):
    def setUp(self):
        self.event = make_event("t3-results")
        self.project = make_project(self.event, title="Visible Project")
        self.voter = make_user("voter")
        self.organizer = make_organizer("audit-owner-xqz")
        judge = Judge.objects.create(event=self.event, slug="judge-secret", user=self.organizer)
        Score.objects.create(judge=judge, project=self.project,
                             criteria={"functionality": 5, "quality": 4, "innovation": 3})

    def _statuses(self, path="/results", params=None):
        out = {}
        out["anonymous"] = self.client.get(path, params or {}).status_code
        self.client.force_login(self.voter)
        out["voter"] = self.client.get(path, params or {}).status_code
        self.client.force_login(self.organizer)
        out["organizer"] = self.client.get(path, params or {}).status_code
        self.client.logout()
        return out

    def test_unpublished_results_blocked_for_every_role_and_path(self):
        for params in ({"event": "t3-results"}, {}):
            statuses = self._statuses(params=params)
            self.assertEqual(set(statuses.values()), {404}, (params, statuses))

    def test_published_but_window_still_open_blocked(self):
        self.event.published = True
        self.event.save()
        statuses = self._statuses(params={"event": "t3-results"})
        self.assertEqual(set(statuses.values()), {404}, statuses)

    def test_published_without_close_blocked(self):
        self.event.published = True
        self.event.voting_opens = None
        self.event.voting_closes = None
        self.event.save()
        statuses = self._statuses(params={"event": "t3-results"})
        self.assertEqual(set(statuses.values()), {404}, statuses)

    def test_guessed_slug_of_unpublished_event_blocked(self):
        other = make_event("t3-unpublished", active=False, published=True, closed=True)
        make_project(other, "hidden-gem")
        self.assertEqual(self.client.get("/results", {"event": "t3-unpublished"}).status_code, 404)
        self.assertEqual(self.client.get("/projects/hidden-gem", {"event": "t3-unpublished"}).status_code, 404)

    def test_results_public_after_publish_and_close(self):
        self.event.published = True
        self.event.voting_closes = timezone.now() - timedelta(minutes=1)
        self.event.save()
        page = self.client.get("/results", {"event": "t3-results"})
        self.assertContains(page, "Visible Project")

    def test_results_never_expose_judge_identities(self):
        self.event.published = True
        self.event.voting_closes = timezone.now() - timedelta(minutes=1)
        self.event.save()
        page = self.client.get("/results", {"event": "t3-results"}).content.decode()
        self.assertNotIn("judge-secret", page)
        self.assertNotIn(self.organizer.username, page)
        self.assertNotIn("criteria", page)

    def test_results_exclude_drafts_duplicates_and_their_scores(self):
        self.event.published = True
        self.event.voting_closes = timezone.now() - timedelta(minutes=1)
        self.event.save()
        judge = Judge.objects.get(event=self.event)
        canonical = make_project(self.event, "canonical", "Canonical")
        dup = make_project(self.event, "dup", "Duplicate Entry", duplicate_of=canonical)
        draft = make_project(self.event, "draft", "Draft Entry", draft=True)
        Score.objects.create(judge=judge, project=dup,
                             criteria={"functionality": 5, "quality": 5, "innovation": 5})
        Score.objects.create(judge=judge, project=draft,
                             criteria={"functionality": 5, "quality": 5, "innovation": 5})
        page = self.client.get("/results", {"event": "t3-results"}).content.decode()
        self.assertNotIn("Duplicate Entry", page)
        self.assertNotIn("Draft Entry", page)
        self.assertIn("Canonical", page)

    def test_results_do_not_fall_back_to_inactive_event(self):
        Event.objects.filter(pk=self.event.pk).update(
            active=False, published=True,
            voting_closes=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.get("/results").status_code, 404)


class OrganizerAuditTests(TestCase):
    def setUp(self):
        self.event = make_event("t3-audit")
        self.project = make_project(self.event)
        self.other = make_event("t3-audit-foreign", active=False)
        self.other_project = make_project(self.other, "foreign")
        self.voter = make_user("voter")
        self.organizer = make_organizer("audit-owner-xqz")

    def test_audit_is_superuser_only(self):
        self.assertEqual(self.client.get("/organizer/vote-audit").status_code, 403)
        self.client.force_login(self.voter)
        self.assertEqual(self.client.get("/organizer/vote-audit", {"event": "t3-audit"}).status_code, 403)

    def test_audit_excludes_other_events(self):
        self.client.force_login(self.voter)
        self.client.post("/vote", {"event": "t3-audit", "project": "proj"})
        self.assertEqual(PublicVote.objects.filter(event=self.event).count(), 1)
        self.client.force_login(self.organizer)
        entries = self.client.get("/organizer/vote-audit", {"event": "t3-audit"}).json()["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["project"], "proj")
        foreign = self.client.get("/organizer/vote-audit", {"event": "t3-audit-foreign"}).json()["entries"]
        self.assertEqual(foreign, [])
        # Entries must not carry judge score data, only vote actions.
        self.assertNotIn("criteria", str(entries))
        self.assertNotIn("score", str(entries).lower())

    def test_audit_unknown_event_slug_is_404(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get("/organizer/vote-audit", {"event": "nope"}).status_code, 404)
