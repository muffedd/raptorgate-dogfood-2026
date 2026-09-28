from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, ScoreAudit, Team, Track
from eventhub.ranking import standings, weighted_score

class RubricTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='rubric',title='Rubric',submissions_close=timezone.now()-timedelta(days=1))
        cls.track=Track.objects.create(event=cls.event,slug='track',name='Track')
        cls.team=Team.objects.create(event=cls.event,slug='team',name='Team')
        cls.project=Project.objects.create(event=cls.event,team=cls.team,track=cls.track,slug='project',title='Project')
        User=get_user_model()
        cls.organizer=User.objects.create_superuser(username='rubric-org',email='r@example.org',password='x')
        cls.stranger=User.objects.create_user(username='stranger')
        cls.judge=Judge.objects.create(event=cls.event,slug='judge',user=cls.stranger)
    def test_default_rubric(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get('/organizer/rubric').json()['rubric']['quality'],0.35)
    def test_new_weights_save_and_change_raw(self):
        self.client.force_login(self.organizer)
        r=self.client.post('/organizer/rubric',{'functionality':'0.2','quality':'0.3','innovation':'0.5'})
        self.assertEqual(r.status_code,200)
        self.event.refresh_from_db()
        Score.objects.create(judge=self.judge,project=self.project,criteria={'functionality':1,'quality':1,'innovation':5})
        self.assertEqual(standings(self.event)[0]['raw'],3.0)
    def test_reject_non_finite_and_mismatched(self):
        self.client.force_login(self.organizer)
        for value in ('nan','inf','-1','0','garbage'):
            with self.subTest(value=value):
                r=self.client.post('/organizer/rubric',{'functionality':value,'quality':'0.3','innovation':'0.5'})
                self.assertEqual(r.status_code,400)
        self.assertEqual(self.client.post('/organizer/rubric',{'functionality':'0.1','quality':'0.3','innovation':'0.5'}).status_code,400)
    def test_non_organizer_blocked(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.post('/organizer/rubric',{'functionality':'0.2','quality':'0.3','innovation':'0.5'}).status_code,403)
        self.assertEqual(self.client.get('/organizer/audit').status_code,403)
    def test_audit_log_scoped_to_current_event(self):
        score=Score.objects.create(judge=self.judge,project=self.project,criteria={'functionality':1,'quality':2,'innovation':3})
        ScoreAudit.objects.create(score=score,editor=self.organizer,previous=None,current=score.criteria)
        self.client.force_login(self.organizer)
        self.assertEqual(len(self.client.get('/organizer/audit').json()['entries']),1)
