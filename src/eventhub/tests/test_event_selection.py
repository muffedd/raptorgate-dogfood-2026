from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, Team, Track

class GlobalEventSelectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.old=Event.objects.create(slug='old',title='Old',submissions_close=timezone.now()-timedelta(days=1))
        cls.new=Event.objects.create(slug='new',title='New',submissions_close=timezone.now()+timedelta(days=1))
        cls.track=Track.objects.create(event=cls.new,slug='track',name='Track')
        cls.team=Team.objects.create(event=cls.new,slug='team',name='Team')
        cls.project=Project.objects.create(event=cls.new,slug='p',title='New Project',team=cls.team,track=cls.track)
        User=get_user_model()
        cls.organizer=User.objects.create_superuser(username='event-org',email='event@example.org',password='x')
        cls.member=User.objects.create_user(username='event-member');cls.team.members.add(cls.member)
        cls.judge_user=User.objects.create_user(username='event-judge')
        cls.judge=Judge.objects.create(event=cls.new,slug='judge',user=cls.judge_user);cls.judge.tracks.add(cls.track)
        Score.objects.create(judge=cls.judge,project=cls.project,criteria={'functionality':3,'quality':3,'innovation':3})

    def test_select_switches_public_submission_and_organizer_routes_globally(self):
        self.assertNotContains(self.client.get('/projects'),'New Project')
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.post('/events/select',{'event':'new'}).status_code,200)
        self.assertContains(self.client.get('/projects'),'New Project')
        self.assertIn(b'New Project',self.client.get('/api/export.csv').content)
        self.assertEqual(self.client.get('/organizer/results').status_code,200)
        self.client.logout()
        self.assertContains(self.client.get('/projects'),'New Project')
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/projects/new',{'title':'New submission','track':str(self.track.pk)}).status_code,200)
        self.client.force_login(self.judge_user)
        self.assertEqual(self.client.get('/api/judge/scores').status_code,200)
        self.assertEqual(self.client.get('/judge/assignments').status_code,200)

    def test_non_organizer_cannot_switch_event(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/events/select',{'event':'new'}).status_code,403)
        self.assertNotContains(self.client.get('/projects'),'New Project')
