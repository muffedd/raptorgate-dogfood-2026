from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, Team, Track


class ResultsCoverageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now=timezone.now()
        cls.event=Event.objects.create(slug='coverage',title='Coverage event',active=True,published=True,
             voting_closes=now-timedelta(hours=1),submissions_close=now-timedelta(days=1))
        track=Track.objects.create(event=cls.event,slug='track',name='Track')
        team=Team.objects.create(event=cls.event,slug='team',name='Team')
        cls.good=Project.objects.create(event=cls.event,team=team,track=track,slug='good',title='Good')
        cls.invalid=Project.objects.create(event=cls.event,team=team,track=track,slug='invalid',title='Invalid score')
        cls.unscored=Project.objects.create(event=cls.event,team=team,track=track,slug='unscored',title='No score')
        duplicate=Project.objects.create(event=cls.event,team=team,track=track,slug='duplicate',title='Duplicate',duplicate_of=cls.good)
        draft=Project.objects.create(event=cls.event,team=team,track=track,slug='draft',title='Draft',draft=True)
        cls.judge=Judge.objects.create(event=cls.event,slug='private-judge',
                                     user=get_user_model().objects.create_user('coverage-judge'))
        Score.objects.create(project=cls.good,judge=cls.judge,
                             criteria={'functionality':5,'quality':4,'innovation':3})
        Score.objects.create(project=cls.invalid,judge=cls.judge,criteria={'functionality':5})
        Score.objects.create(project=duplicate,judge=cls.judge,
                             criteria={'functionality':5,'quality':5,'innovation':5})
        Score.objects.create(project=draft,judge=cls.judge,
                             criteria={'functionality':5,'quality':5,'innovation':5})

    def test_aggregate_eligible_valid_scored_unscored_counts(self):
        response=self.client.get('/results')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['eligible_count'],3)
        self.assertEqual(response.context['scored_count'],1)
        self.assertEqual(response.context['unscored_count'],2)
        html=response.content.decode()
        self.assertIn('Ranks exclude unscored projects',html)
        self.assertNotIn('private-judge',html)
        self.assertNotIn('Duplicate',html)
        self.assertNotIn('Draft',html)
        self.event.published=False;self.event.save(update_fields=['published'])
        self.assertEqual(self.client.get('/results').status_code,404)

    def test_empty_event_is_zero_not_a_false_success(self):
        Score.objects.all().delete()
        Project.objects.all().delete()
        response=self.client.get('/results')
        self.assertEqual((response.context['eligible_count'],response.context['scored_count'],response.context['unscored_count']),(0,0,0))
