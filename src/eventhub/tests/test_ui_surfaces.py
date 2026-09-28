from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Assignment, Event, Judge, Project, Score, Team, Track


class UISurfaceTruthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='ui-surface',title='UI Surface',active=True,submissions_close=timezone.now()-timedelta(days=1),voting_opens=timezone.now()-timedelta(days=1),voting_closes=timezone.now()+timedelta(days=1))
        cls.track=Track.objects.create(event=cls.event,slug='tools',name='Tools')
        cls.team=Team.objects.create(event=cls.event,slug='team',name='Team')
        cls.project=Project.objects.create(event=cls.event,track=cls.track,team=cls.team,slug='shown',title='Shown project',summary='<script>not script</script>')
        cls.hidden=Project.objects.create(event=cls.event,track=cls.track,team=cls.team,slug='secret',title='Hidden project',draft=True)
        User=get_user_model()
        cls.org=User.objects.create_superuser(username='ui-org',email='ui@example.com',password='x')
        cls.guest=User.objects.create_user(username='ui-guest')
        cls.judge=Judge.objects.create(event=cls.event,slug='judge',user=cls.guest);cls.judge.tracks.add(cls.track)
        Assignment.objects.create(judge=cls.judge,project=cls.project)
        Score.objects.create(judge=cls.judge,project=cls.project,criteria={'functionality':4,'quality':3,'innovation':5})

    def test_organizer_views_are_private_and_use_real_counts(self):
        self.assertEqual(self.client.get('/organizer/overview').status_code,302)
        self.client.force_login(self.guest)
        self.assertEqual(self.client.get('/organizer/overview').status_code,403)
        self.assertEqual(self.client.get('/organizer/results?view=html').status_code,403)
        self.client.force_login(self.org)
        overview=self.client.get('/organizer/overview')
        self.assertContains(overview,'1</h2>')
        self.assertContains(overview,'Eligible projects')
        self.assertNotContains(overview,'Hidden project')
        result=self.client.get('/organizer/results?view=html')
        self.assertContains(result,'Private preview')
        self.assertContains(result,'Shown project')
        self.assertNotContains(result,'Hidden project')
        self.assertEqual(self.client.get('/organizer/results').get('Content-Type'),'application/json')

    def test_public_results_remain_gated_before_close_and_publish(self):
        self.assertEqual(self.client.get('/results').status_code,404)
        self.event.published=True;self.event.save()
        self.assertEqual(self.client.get('/results').status_code,404)
        self.event.voting_closes=timezone.now()-timedelta(seconds=1);self.event.save()
        result=self.client.get('/results')
        self.assertContains(result,'Shown project')
        self.assertNotContains(result,'Hidden project')
        self.assertNotContains(result,'ui-guest')
        self.assertNotContains(result,'criteria')

    def test_widget_theme_is_explicit_and_unknown_defaults_light(self):
        url='/embed/ui-surface/gallery'
        for query,expected in [('', 'light'),('?theme=dark','dark'),('?theme=invalid','light')]:
            page=self.client.get(url+query)
            self.assertContains(page,f'data-theme="{expected}"')
            self.assertContains(page,'Shown project')
            self.assertNotContains(page,'Hidden project')
            self.assertNotContains(page,'ui-guest')
            self.assertFalse(page.cookies)

    def test_gallery_escape_and_filter_clear_state(self):
        page=self.client.get('/projects?q=missing')
        self.assertContains(page,'Clear filters')
        self.assertNotContains(page,'Hidden project')
        page=self.client.get('/projects')
        self.assertContains(page,'&lt;script&gt;not script&lt;/script&gt;')
        self.assertNotContains(page,'<script>not script</script>')

    def test_equal_normalized_scores_share_rank_and_unscored_has_none(self):
        from eventhub.ranking import standings
        second=Project.objects.create(event=self.event,track=self.track,team=self.team,slug='second',title='Second project')
        other=get_user_model().objects.create_user(username='ui-second-judge')
        j2=Judge.objects.create(event=self.event,slug='judge-2',user=other)
        Score.objects.create(judge=j2,project=second,criteria={'functionality':1,'quality':1,'innovation':1})
        third=Project.objects.create(event=self.event,track=self.track,team=self.team,slug='third',title='Unscored')
        rows=standings(self.event)
        self.assertEqual([(r['project'],r['rank']) for r in rows],[('second',1),('shown',1),('third',None)])
