"""A stored draft is never a public project, score target, or ranked entry."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from eventhub.models import Assignment, Event, Judge, Project, Team, Track
from eventhub.ranking import standings


class DraftVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(
            slug='drafts', title='Draft visibility',
            submissions_close=timezone.now() - timedelta(days=1),
        )
        track = Track.objects.create(event=cls.event, slug='dev', name='Dev')
        team = Team.objects.create(event=cls.event, slug='team', name='Team')
        cls.draft = Project.objects.create(
            event=cls.event, track=track, team=team,
            slug='hidden', title='Hidden draft', draft=True,
        )
        cls.published = Project.objects.create(
            event=cls.event, track=track, team=team,
            slug='shown', title='Visible project', draft=False,
        )
        User = get_user_model()
        cls.judge_user = User.objects.create_user(username='draft-judge')
        cls.judge = Judge.objects.create(event=cls.event, slug='judge', user=cls.judge_user)
        cls.judge.tracks.add(track)
        Assignment.objects.create(judge=cls.judge, project=cls.draft)

    def test_public_gallery_hides_draft(self):
        page = self.client.get('/projects')
        self.assertContains(page, 'Visible project')
        self.assertNotContains(page, 'Hidden draft')

    def test_standings_exclude_draft(self):
        self.assertEqual([row['project'] for row in standings(self.event)], ['shown'])

    def test_judge_cannot_score_draft_even_with_stale_assignment(self):
        self.client.force_login(self.judge_user)
        response = self.client.post('/judge/score/hidden', {
            'functionality': '4', 'quality': '4', 'innovation': '4',
        })
        self.assertEqual(response.status_code, 404)
