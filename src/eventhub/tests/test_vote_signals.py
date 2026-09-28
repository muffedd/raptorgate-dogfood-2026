from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Project, PublicActionAttempt, PublicVote, PublicVoteAudit, Team, Track


class VoteSignalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(slug='signals', title='Signals', active=True,
                       submissions_close=timezone.now()-timedelta(days=1))
        cls.other = Event.objects.create(slug='other-signals', title='Other',
                       submissions_close=timezone.now()-timedelta(days=1))
        track = Track.objects.create(event=cls.event, slug='t', name='Track')
        team = Team.objects.create(event=cls.event, slug='team', name='Team')
        cls.project = Project.objects.create(event=cls.event, team=team, track=track,
                                             slug='project', title='Project')
        User=get_user_model()
        cls.organizer=User.objects.create_superuser('signal-org','org@example.org','pw')
        cls.participant=User.objects.create_user('signal-participant')

    def test_private_signals_are_aggregate_and_event_scoped(self):
        self.assertEqual(self.client.get('/organizer/vote-signals').status_code, 403)
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get('/organizer/vote-signals').status_code, 403)
        self.client.force_login(self.organizer)
        for i in range(5):
            PublicActionAttempt.objects.create(event=self.event, actor_key='secret-actor',
                 action='vote', observed_ip='203.0.113.7')
        for i in range(2):
            PublicActionAttempt.objects.create(event=self.event, actor_key=f'actor-{i}',
                 action='vote', observed_ip='203.0.113.7')
        PublicActionAttempt.objects.create(event=self.other, actor_key='foreign-actor',
             action='vote', observed_ip='198.51.100.8')
        PublicVote.objects.create(event=self.event, project=self.project, voter_key='secret-actor',
                                  receipt='a'*32)
        PublicVoteAudit.objects.create(event=self.event, project=self.project,
                                       voter_key='secret-actor', action='cast', observed_ip='203.0.113.7')
        page=self.client.get('/organizer/vote-signals')
        self.assertContains(page, 'Vote activity signals, not verdicts')
        self.assertContains(page, '7 logged attempts')
        self.assertContains(page, '1 actor keys')
        self.assertContains(page, '1 IP addresses')
        self.assertContains(page, 'Accepted vote rows')
        for private in ('secret-actor', '203.0.113.7', 'foreign-actor', '198.51.100.8', 'a'*32):
            self.assertNotContains(page, private)
        self.assertEqual(self.client.post('/organizer/vote-signals').status_code, 405)

    def test_empty_and_audit_gap_not_a_verdict(self):
        self.client.force_login(self.organizer)
        PublicVote.objects.create(event=self.event, project=self.project, voter_key='one', receipt='b'*32)
        page=self.client.get('/organizer/vote-signals')
        self.assertContains(page, 'Difference in those counts')
        self.assertContains(page, 'consistency signal, not proof of tampering')
        self.event.active=False; self.event.save(update_fields=['active'])
        self.assertEqual(self.client.get('/organizer/vote-signals').status_code, 404)
