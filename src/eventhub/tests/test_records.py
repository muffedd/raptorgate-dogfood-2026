from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, JudgeParticipationRecord, Project, Score, Team, Track

class ParticipationRecordTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='records-event',title='Records',active=True,published=True,voting_closes=timezone.now()-timedelta(hours=1),submissions_close=timezone.now()-timedelta(days=1))
        cls.track=Track.objects.create(event=cls.event,slug='track',name='Track')
        cls.team=Team.objects.create(event=cls.event,slug='team',name='Team')
        cls.project=Project.objects.create(event=cls.event,track=cls.track,team=cls.team,slug='project',title='Project')
        User=get_user_model();cls.organizer=User.objects.create_superuser('record-org','record-org@example.org','pw')
        cls.judge_user=User.objects.create_user('record-judge')
        cls.judge=Judge.objects.create(event=cls.event,slug='judge',user=cls.judge_user)
        Score.objects.create(project=cls.project,judge=cls.judge,criteria={'functionality':4,'quality':3,'innovation':5})
    def issue(self):
        with patch.dict('os.environ',{'RECORD_SIGNING_KEY':'test-key-only-'*4}):
            return self.client.post('/organizer/records/issue',{'judge':'judge'})
    def test_issue_and_verify_without_public_ballot(self):
        self.client.force_login(self.organizer)
        r=self.issue();self.assertEqual(r.status_code,201)
        pk=r.json()['record_id']
        self.assertEqual(self.issue().json(),{'record_id':pk,'already_issued':True})
        self.client.logout()
        with patch.dict('os.environ',{'RECORD_SIGNING_KEY':'test-key-only-'*4}):
            result=self.client.get(f'/records/{pk}/verify')
        self.assertEqual(result.status_code,200)
        self.assertTrue(result.json()['valid']);self.assertEqual(result.json()['record']['reviews'],1)
        self.assertNotIn('criteria',str(result.json()))
        self.assertNotIn('comment',str(result.json()))
    def test_nonorganizer_denied_and_results_gate(self):
        self.assertEqual(self.issue().status_code,403)
        self.client.force_login(self.judge_user);self.assertEqual(self.issue().status_code,403)
        self.client.force_login(self.organizer);pk=self.issue().json()['record_id']
        self.event.published=False;self.event.save(update_fields=['published'])
        with patch.dict('os.environ',{'RECORD_SIGNING_KEY':'test-key-only-'*4}):
            self.assertEqual(self.client.get(f'/records/{pk}/verify').status_code,404)
        self.assertEqual(self.issue().status_code,409)
    def test_no_eligible_reviews_and_tamper_detection(self):
        self.client.force_login(self.organizer)
        Score.objects.all().delete();self.assertEqual(self.issue().status_code,409)
        Score.objects.create(project=self.project,judge=self.judge,criteria={'functionality':4,'quality':3,'innovation':5})
        pk=self.issue().json()['record_id']
        JudgeParticipationRecord.objects.filter(pk=pk).update(payload={'version':1,'event':'bad'})
        with patch.dict('os.environ',{'RECORD_SIGNING_KEY':'test-key-only-'*4}):
            r=self.client.get(f'/records/{pk}/verify')
        self.assertEqual(r.status_code,409);self.assertFalse(r.json()['valid'])

    def test_default_demo_is_not_a_signing_key(self):
        self.client.force_login(self.organizer)
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(self.issue_without_key().status_code,503)
            self.assertEqual(self.client.get('/records/1/verify').status_code,503)
    def issue_without_key(self):
        return self.client.post('/organizer/records/issue',{'judge':'judge'})
