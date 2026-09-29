"""Public UI tour is fixture-backed and cannot submit or impersonate roles."""
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from eventhub.models import Event, Project, Team, Track

class PreviewTourTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='tour',title='Tour fixture',active=True,
            published=True,submissions_close=timezone.now()-timedelta(days=3),
            voting_opens=timezone.now()-timedelta(days=2),
            voting_closes=timezone.now()-timedelta(days=1))
        team=Team.objects.create(event=cls.event,slug='sample',name='Sample team')
        track=Track.objects.create(event=cls.event,slug='demo',name='Demo track')
        Project.objects.create(event=cls.event,team=team,track=track,
            slug='sample',title='Sample project',summary='Fixture-only sample')

    @override_settings(PREVIEW=True)
    def test_tour_pages_render_without_login_or_private_score_data(self):
        for page, marker in [('judge','Sample project'),('ballot','On the'),
                             ('organizer','Event overview'),('standings','Judging results'),
                             ('voter','Verify your email'),('login','Sign in'),('signup','Create'),
                             ('event','Create event'),('questions','Submission questions'),
                             ('submit','Submit project'),('team','Create team'),
                             ('invite','Accept judge invite'),('signals','Signals, not verdicts')]:
            with self.subTest(page=page):
                response=self.client.get('/tour/'+page)
                self.assertEqual(response.status_code,200)
                self.assertContains(response,marker)
                self.assertNotContains(response,'event-organizer')

    @override_settings(PREVIEW=True)
    def test_tour_rejects_posts_and_unknown_pages(self):
        self.assertEqual(self.client.post('/tour/judge',{'functionality':'5'}).status_code,405)
        self.assertEqual(self.client.get('/tour/nope').status_code,404)

    @override_settings(PREVIEW=False)
    def test_tour_is_not_available_in_local_full_app(self):
        self.assertEqual(self.client.get('/tour/judge').status_code,404)
