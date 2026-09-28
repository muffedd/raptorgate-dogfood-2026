from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Project, ProjectComment, PublicVote, PublicVoteAudit, Team, Track


class PublicParticipationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='vote-event',title='Voting event',submissions_close=timezone.now()-timedelta(days=2), voting_opens=timezone.now()-timedelta(hours=1),voting_closes=timezone.now()+timedelta(hours=1))
        cls.track=Track.objects.create(event=cls.event,slug='tech',name='Tech')
        cls.team=Team.objects.create(event=cls.event,slug='team',name='Team')
        cls.project=Project.objects.create(event=cls.event,team=cls.team,track=cls.track,slug='candidate',title='Candidate')
        cls.hidden=Project.objects.create(event=cls.event,team=cls.team,track=cls.track,slug='hidden',title='Hidden',draft=True)
        cls.other=Event.objects.create(slug='other',title='Other',submissions_close=timezone.now()+timedelta(days=1))
        cls.othertrack=Track.objects.create(event=cls.other,slug='other',name='Other')
        cls.otherteam=Team.objects.create(event=cls.other,slug='other',name='Other')
        cls.otherproject=Project.objects.create(event=cls.other,team=cls.otherteam,track=cls.othertrack,slug='foreign',title='Foreign')
        User=get_user_model()
        cls.voter=User.objects.create_user(username='voter')
        cls.organizer=User.objects.create_superuser(username='organizer',email='org@example.com',password='x')

    def test_ballot_auth_and_isolation(self):
        self.assertEqual(self.client.get('/ballot?event=vote-event').status_code,403)
        self.client.force_login(self.voter)
        page=self.client.get('/ballot?event=vote-event')
        self.assertContains(page,'Candidate')
        self.assertNotContains(page,'Hidden')
        self.assertNotContains(page,'Foreign')

    def test_one_vote_per_event_and_no_cross_event_or_draft(self):
        self.client.force_login(self.voter)
        payload={'event':'vote-event','project':'candidate'}
        self.assertEqual(self.client.post('/vote',payload).status_code,201)
        self.assertEqual(self.client.post('/vote',payload).status_code,409)
        self.assertEqual(self.client.post('/vote',{'event':'vote-event','project':'hidden'}).status_code,404)
        self.assertEqual(self.client.post('/vote',{'event':'vote-event','project':'foreign'}).status_code,404)
        self.assertEqual(PublicVote.objects.filter(event=self.event).count(),1)
        self.assertEqual(PublicVoteAudit.objects.filter(event=self.event).count(),1)

    def test_closed_window_and_unverified_modes_rejected(self):
        self.client.force_login(self.voter)
        self.event.voting_opens=timezone.now()+timedelta(hours=1);self.event.save()
        self.assertEqual(self.client.post('/vote',{'event':'vote-event','project':'candidate'}).status_code,403)
        self.event.voting_opens=timezone.now()-timedelta(hours=1)
        self.event.voting_access='email';self.event.save()
        self.assertEqual(self.client.post('/vote',{'event':'vote-event','project':'candidate'}).status_code,403)

    def test_comments_escape_and_public_results_gate(self):
        self.client.force_login(self.voter)
        url='/projects/candidate?event=vote-event'
        self.assertEqual(self.client.post(url,{'event':'vote-event','body':'<script>alert(1)</script>'}).status_code,201)
        page=self.client.get(url)
        self.assertContains(page,'&lt;script&gt;')
        self.assertNotContains(page,'<script>')
        self.assertEqual(self.client.get('/results?event=vote-event').status_code,404)
        self.event.published=True;self.event.save()
        self.assertEqual(self.client.get('/results?event=vote-event').status_code,404)
        self.event.voting_closes=timezone.now()-timedelta(seconds=1);self.event.save()
        self.assertContains(self.client.get('/results?event=vote-event'),'Candidate')

    def test_organizer_audit_only_for_selected_event(self):
        self.client.force_login(self.voter)
        self.client.post('/vote',{'event':'vote-event','project':'candidate'})
        self.assertEqual(self.client.get('/organizer/vote-audit?event=vote-event').status_code,403)
        self.client.force_login(self.organizer)
        self.assertEqual(len(self.client.get('/organizer/vote-audit?event=vote-event').json()['entries']),1)
        self.assertEqual(len(self.client.get('/organizer/vote-audit?event=other').json()['entries']),0)

class EventSelectionTests(TestCase):
    def test_organizer_selects_new_event_without_changing_default_fixture(self):
        fixture=Event.objects.create(slug='fixture',title='Fixture',submissions_close=timezone.now()-timedelta(days=1))
        later=Event.objects.create(slug='later',title='Later',submissions_close=timezone.now()+timedelta(days=1))
        User=get_user_model()
        guest=User.objects.create_user(username='guest')
        org=User.objects.create_superuser(username='organizer',email='org@example.org',password='x')
        self.assertContains(self.client.get('/projects'),'Fixture')
        self.client.force_login(guest)
        self.assertEqual(self.client.post('/events/select',{'event':'later'}).status_code,403)
        self.client.force_login(org)
        self.assertEqual(self.client.post('/events/select',{'event':'later'}).status_code,200)
        self.assertContains(self.client.get('/projects'),'Later')
        self.client.logout()
        self.assertContains(self.client.get('/projects'),'Later')

class AntiAbuseTests(TestCase):
    def setUp(self):
        self.event=Event.objects.create(slug='abuse',title='Abuse',submissions_close=timezone.now()-timedelta(days=1),voting_opens=timezone.now()-timedelta(hours=1),voting_closes=timezone.now()+timedelta(hours=1))
        track=Track.objects.create(event=self.event,slug='t',name='T')
        team=Team.objects.create(event=self.event,slug='t',name='T')
        self.project=Project.objects.create(event=self.event,team=team,track=track,slug='p',title='P')
        User=get_user_model()
        self.user=User.objects.create_user(username='commenter')
        self.org=User.objects.create_superuser(username='org',email='org@example.com',password='x')

    def test_comment_throttle_and_moderation(self):
        self.client.force_login(self.user)
        path='/projects/p?event=abuse'
        for i in range(5):
            self.assertEqual(self.client.post(path,{'body':f'comment{i}','event':'abuse'}).status_code,201)
        self.assertEqual(self.client.post(path,{'body':'six','event':'abuse'}).status_code,429)
        target=ProjectComment.objects.filter(event=self.event).first()
        self.assertEqual(self.client.post(f'/organizer/comments/{target.pk}/hide',{'event':'abuse'}).status_code,403)
        self.client.force_login(self.org)
        self.assertEqual(self.client.post(f'/organizer/comments/{target.pk}/hide',{'event':'abuse'}).status_code,200)
        self.assertNotContains(self.client.get(path),'comment0')

    def test_vote_throttle_on_repeated_attempts(self):
        self.client.force_login(self.user)
        data={'event':'abuse','project':'p'}
        self.assertEqual(self.client.post('/vote',data).status_code,201)
        for i in range(7): self.assertEqual(self.client.post('/vote',data).status_code,409)
        self.assertEqual(self.client.post('/vote',data).status_code,429)
