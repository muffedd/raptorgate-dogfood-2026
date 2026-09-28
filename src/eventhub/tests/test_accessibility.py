"""Stable structural checks supplement live axe and keyboard/browser testing."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, Team, Track


class AccessibilityStructureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now=timezone.now()
        cls.event=Event.objects.create(slug='access', title='Accessible event', active=True,
               published=True, submissions_close=now-timedelta(days=1),
               voting_opens=now-timedelta(days=2), voting_closes=now-timedelta(hours=1))
        track=Track.objects.create(event=cls.event, slug='t', name='Track')
        team=Team.objects.create(event=cls.event, slug='team', name='Team')
        cls.project=Project.objects.create(event=cls.event, track=track, team=team,
                                           slug='candidate', title='Candidate')
        judge=Judge.objects.create(event=cls.event, slug='j',
                                  user=get_user_model().objects.create_user('access-judge'))
        Score.objects.create(project=cls.project, judge=judge,
                             criteria={'functionality':4,'quality':4,'innovation':4})
        cls.organizer=get_user_model().objects.create_superuser('access-org','o@example.org','pw')

    def test_public_landmarks_labels_and_native_expander(self):
        for url in ('/projects','/signup/','/verify','/results','/projects/candidate'):
            with self.subTest(url=url):
                html=self.client.get(url).content.decode()
                self.assertIn('href="#main-content"',html)
                self.assertIn('id="main-content"',html)
                self.assertIn('aria-label="Primary navigation"',html)
                self.assertIn('<h1',html)
        verify=self.client.get('/verify').content.decode()
        self.assertIn('for="verify-artifact"',verify)
        self.assertIn('aria-describedby="verify-help"',verify)
        results=self.client.get('/results').content.decode()
        self.assertIn('<details>',results)
        self.assertIn('<summary>',results)
        self.assertNotIn('access-judge',results)

    def test_organizer_landmarks(self):
        self.client.force_login(self.organizer)
        for url in ('/organizer/overview','/organizer/results?view=html','/organizer/vote-signals'):
            with self.subTest(url=url):
                html=self.client.get(url).content.decode()
                self.assertIn('href="#main-content"',html)
                self.assertIn('aria-label="Primary navigation"',html)
                self.assertIn('<h1',html)
