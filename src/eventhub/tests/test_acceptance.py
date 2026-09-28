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

class TeamAndEventTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='fixture',title='Fixture',submissions_close=timezone.now()+timedelta(days=1))
        User=get_user_model()
        cls.member=User.objects.create_user(username='member2')
        cls.guest=User.objects.create_user(username='guest2')
        cls.organizer=User.objects.create_superuser(username='org2',email='org2@example.org',password='x')
    def test_team_creation_adds_owner(self):
        self.client.force_login(self.member)
        r=self.client.post('/teams/new',{'name':'New Team'})
        self.assertEqual(r.status_code,201)
        self.assertTrue(Team.objects.get(slug=r.json()['team']).members.filter(pk=self.member.pk).exists())
    def test_non_member_cannot_mint_invite(self):
        team=Team.objects.create(event=self.event,slug='locked',name='Locked')
        self.client.force_login(self.guest)
        self.assertEqual(self.client.post('/teams/locked/invite').status_code,403)
    def test_invite_roundtrip_and_expiration(self):
        team=Team.objects.create(event=self.event,slug='open-team',name='Open')
        team.members.add(self.member)
        self.client.force_login(self.member)
        r=self.client.post('/teams/open-team/invite')
        self.assertEqual(r.status_code,200)
        path=r.json()['invite_path']
        self.client.force_login(self.guest)
        self.assertEqual(self.client.post(path).status_code,200)
        self.assertTrue(team.members.filter(pk=self.guest.pk).exists())
        team.refresh_from_db();team.invite_expires_at=timezone.now()-timedelta(seconds=1);team.save()
        self.assertEqual(self.client.post(path).status_code,404)
    def test_bad_invite_is_404(self):
        self.client.force_login(self.guest)
        self.assertEqual(self.client.post('/join/does-not-exist').status_code,404)
    def test_event_creation_requires_organizer(self):
        self.client.force_login(self.guest)
        r=self.client.post('/events/new',{'name':'New','slug':'new','submissions_close':'2027-01-01T00:00:00Z'})
        self.assertEqual(r.status_code,403)
    def test_event_creation_validates_deadline_and_slug(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.post('/events/new',{'name':'New','slug':'new','submissions_close':'not-a-date'}).status_code,400)
        self.assertEqual(self.client.post('/events/new',{'name':'New','slug':'Bad Slug','submissions_close':'2027-01-01T00:00:00Z'}).status_code,400)
        self.assertEqual(self.client.post('/events/new',{'name':'New','slug':'new','submissions_close':'2027-01-01T00:00:00Z'}).status_code,201)
        self.assertEqual(self.client.post('/events/new',{'name':'New','slug':'new','submissions_close':'2027-01-01T00:00:00Z'}).status_code,409)
