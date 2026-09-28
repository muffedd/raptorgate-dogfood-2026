from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, Team, Track

class PortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='evt',title='Test Event',submissions_close=timezone.now()-timedelta(days=1))
        cls.track=Track.objects.create(event=cls.event,slug='trk',name='Track')
        cls.team=Team.objects.create(event=cls.event,slug='team',name='Team')
        cls.project=Project.objects.create(event=cls.event,slug='one',team=cls.team,track=cls.track,title='One Project')
        cls.duplicate=Project.objects.create(event=cls.event,slug='two',team=cls.team,track=cls.track,title='Hidden Project',duplicate_of=cls.project)
        User=get_user_model()
        cls.judge_user=User.objects.create_user(username='judge')
        cls.other_judge_user=User.objects.create_user(username='other')
        cls.participant=User.objects.create_user(username='participant')
        cls.organizer=User.objects.create_superuser(username='organizer',email='o@example.org',password='x')
        cls.judge=Judge.objects.create(event=cls.event,slug='jdg_01',user=cls.judge_user)
        cls.other=Judge.objects.create(event=cls.event,slug='jdg_02',user=cls.other_judge_user)
        Score.objects.create(judge=cls.judge,project=cls.project,criteria={'quality':4})
    def test_public_gallery_and_duplicate_filter(self):
        r=self.client.get('/projects')
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'One Project')
        self.assertNotContains(r,'Hidden Project')
    def test_closed_submission_rejected(self):
        self.client.force_login(self.participant)
        self.assertEqual(self.client.post('/projects/new',{'title':'Late'}).status_code,403)
    def test_judge_self_only(self):
        self.client.force_login(self.judge_user)
        self.assertEqual(self.client.get('/api/judge/scores').status_code,200)
        self.assertEqual(self.client.get('/api/judge/scores?judge=jdg_02').status_code,403)
    def test_other_judge_cannot_read_peer(self):
        self.client.force_login(self.other_judge_user)
        self.assertEqual(self.client.get('/api/judge/scores?judge=jdg_01').status_code,403)
    def test_participant_cannot_read_scores(self):
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get('/api/judge/scores').status_code,403)
    def test_organizer_csv(self):
        self.client.force_login(self.organizer)
        r=self.client.get('/api/export.csv')
        self.assertEqual(r.status_code,200)
        self.assertTrue(r.content.startswith(b'project_id,project_title'))

class SubmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='open',title='Open Event',submissions_close=timezone.now()+timedelta(hours=1))
        cls.track=Track.objects.create(event=cls.event,slug='dev',name='Dev tools')
        cls.other_track=Track.objects.create(event=Event.objects.create(slug='other',title='Other',submissions_close=timezone.now()+timedelta(hours=1)),slug='other',name='Other')
        cls.team=Team.objects.create(event=cls.event,slug='one',name='One')
        User=get_user_model()
        cls.member=User.objects.create_user(username='member')
        cls.stranger=User.objects.create_user(username='stranger')
        cls.team.members.add(cls.member)
    def payload(self,**overrides):
        return {'title':'Candidate','summary':'A real project','repo_url':'https://example.org/repo','track':str(self.track.pk),**overrides}
    def test_member_creates_first_submission(self):
        self.client.force_login(self.member)
        r=self.client.post('/projects/new',self.payload())
        self.assertEqual(r.status_code,201)
        self.assertEqual(Project.objects.filter(event=self.event,team=self.team).count(),1)
        self.assertEqual(Project.objects.get(event=self.event,team=self.team).title,'Candidate')
    def test_member_edits_canonical_in_place(self):
        self.client.force_login(self.member)
        self.client.post('/projects/new',self.payload())
        r=self.client.post('/projects/new',self.payload(title='Updated'))
        self.assertEqual(r.status_code,200)
        self.assertTrue(r.json()['updated'])
        self.assertEqual(Project.objects.filter(event=self.event,team=self.team).count(),1)
        self.assertEqual(Project.objects.get(event=self.event,team=self.team).title,'Updated')
    def test_non_member_cannot_submit(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.post('/projects/new',self.payload()).status_code,403)
        self.assertFalse(Project.objects.filter(event=self.event).exists())
    def test_cross_event_track_rejected(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/projects/new',self.payload(track=str(self.other_track.pk))).status_code,400)
        self.assertFalse(Project.objects.filter(event=self.event).exists())
    def test_blank_title_rejected(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/projects/new',self.payload(title='   ')).status_code,400)
    def test_deadline_blocks_edit_not_just_create(self):
        self.client.force_login(self.member)
        self.client.post('/projects/new',self.payload())
        self.event.submissions_close=timezone.now()-timedelta(seconds=1);self.event.save()
        self.assertEqual(self.client.post('/projects/new',self.payload(title='Late')).status_code,403)
        self.assertEqual(Project.objects.get(event=self.event,team=self.team).title,'Candidate')
