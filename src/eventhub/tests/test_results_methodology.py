from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, Team, Track


class PublicMethodologyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now=timezone.now()
        cls.event=Event.objects.create(slug='method',title='Method event',active=True,published=True,
                 voting_closes=now-timedelta(hours=1),submissions_close=now-timedelta(days=1))
        track=Track.objects.create(event=cls.event,slug='track',name='Track')
        team=Team.objects.create(event=cls.event,slug='team',name='Team')
        project=Project.objects.create(event=cls.event,team=team,track=track,slug='project',title='Project')
        judge=Judge.objects.create(event=cls.event,slug='private-judge',
                 user=get_user_model().objects.create_user('private-judge-user'))
        Score.objects.create(project=project,judge=judge,
                     criteria={'functionality':4,'quality':3,'innovation':5},comment='Private judge comment')

    def test_defaults_and_private_identity_boundary(self):
        page=self.client.get('/results')
        self.assertEqual(page.context['rubric_weights'],
                         [('Functionality',40.0),('Quality',35.0),('Innovation',25.0)])
        html=page.content.decode()
        for text in ('Functionality','40%','Quality','35%','Innovation','25%',
                     'population standard deviation','zero spread contributes 3.00',
                     'Equal three-decimal means share a competition rank','not proof of statistical fairness'):
            self.assertIn(text,html)
        for secret in ('private-judge','private-judge-user','Private judge comment'):
            self.assertNotIn(secret,html)

    def test_event_specific_weights_and_publication_gate(self):
        self.event.rubric={'functionality':0.2,'quality':0.3,'innovation':0.5}
        self.event.save(update_fields=['rubric'])
        page=self.client.get('/results')
        self.assertEqual(page.context['rubric_weights'],
                         [('Functionality',20.0),('Quality',30.0),('Innovation',50.0)])
        self.assertContains(page,'50%')
        self.event.published=False;self.event.save(update_fields=['published'])
        self.assertEqual(self.client.get('/results').status_code,404)
