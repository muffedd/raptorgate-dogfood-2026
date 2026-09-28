from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from eventhub.models import Assignment, Event, Judge, Project, Score, ScoreAudit, Team, Track
from eventhub.ranking import weighted_score, standings

class JudgingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='evt',title='Event',submissions_close=timezone.now()-timedelta(days=1))
        cls.track=Track.objects.create(event=cls.event,slug='trk',name='Track')
        cls.off_track=Track.objects.create(event=cls.event,slug='off',name='Off')
        cls.team=Team.objects.create(event=cls.event,slug='team',name='Team')
        cls.project=Project.objects.create(event=cls.event,team=cls.team,track=cls.track,slug='prj',title='Project')
        User=get_user_model()
        cls.organizer=User.objects.create_superuser(username='org',email='org@example.org',password='x')
        cls.judge_user=User.objects.create_user(username='judge')
        cls.peer_user=User.objects.create_user(username='peer')
        cls.member=User.objects.create_user(username='member')
        cls.team.members.add(cls.member)
        cls.judge=Judge.objects.create(event=cls.event,slug='jdg',user=cls.judge_user)
        cls.judge.tracks.add(cls.track)
        cls.peer=Judge.objects.create(event=cls.event,slug='peer',user=cls.peer_user)
    def payload(self,**overrides):
        return {'functionality':'4','quality':'3','innovation':'5','comment':'Clear evidence',**overrides}
    def assign(self):
        self.client.force_login(self.organizer)
        return self.client.post('/organizer/assign',{'judge':'jdg','project':'prj'})
    def test_organizer_assigns_matching_track(self):
        r=self.assign()
        self.assertEqual(r.status_code,200)
        self.assertEqual(Assignment.objects.count(),1)
        self.assertFalse(self.assign().json()['assigned'])
    def test_non_organizer_cannot_assign(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/organizer/assign',{'judge':'jdg','project':'prj'}).status_code,403)
    def test_off_track_judge_rejected(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.post('/organizer/assign',{'judge':'peer','project':'prj'}).status_code,400)
    def test_judge_must_have_assignment(self):
        self.client.force_login(self.judge_user)
        self.assertEqual(self.client.post('/judge/score/prj',self.payload()).status_code,403)
    def test_assigned_judge_scores_and_audits_edit(self):
        self.assign();self.client.force_login(self.judge_user)
        self.assertEqual(self.client.post('/judge/score/prj',self.payload()).status_code,200)
        self.assertEqual(self.client.post('/judge/score/prj',self.payload(quality='5')).status_code,200)
        self.assertEqual(Score.objects.count(),1)
        self.assertEqual(ScoreAudit.objects.count(),2)
        self.assertIsNone(ScoreAudit.objects.order_by('pk').first().previous)
        self.assertEqual(ScoreAudit.objects.order_by('pk').last().previous['quality'],3)
        self.assertEqual(ScoreAudit.objects.order_by('pk').first().current['comment'],'Clear evidence')
        self.assertEqual(ScoreAudit.objects.order_by('pk').last().previous['comment'],'Clear evidence')
        self.assertEqual(ScoreAudit.objects.order_by('pk').last().current['comment'],'Clear evidence')
    def test_comment_only_edit_preserves_both_audit_snapshots(self):
        self.assign(); self.client.force_login(self.judge_user)
        self.client.post('/judge/score/prj', self.payload(comment='First private note'))
        self.client.post('/judge/score/prj', self.payload(comment='Revised private note'))
        first, second = ScoreAudit.objects.order_by('pk')
        self.assertIsNone(first.previous)
        self.assertEqual(first.current['comment'], 'First private note')
        self.assertEqual(second.previous['comment'], 'First private note')
        self.assertEqual(second.current['comment'], 'Revised private note')
        self.assertEqual(second.previous['quality'], second.current['quality'])
        self.assertEqual(self.client.get('/organizer/audit').status_code, 403)
        self.client.force_login(self.organizer)
        audit = self.client.get('/organizer/audit').json()['entries']
        self.assertEqual(audit[0]['before']['comment'], 'First private note')
        self.assertEqual(audit[0]['after']['comment'], 'Revised private note')

    def test_score_out_of_range_or_bad_type(self):
        self.assign();self.client.force_login(self.judge_user)
        for bad in ('0','6','NaN','3.5',''):
            with self.subTest(bad=bad):
                self.assertEqual(self.client.post('/judge/score/prj',self.payload(quality=bad)).status_code,400)
        self.assertFalse(Score.objects.exists())
    def test_judge_cannot_score_own_team_even_assigned(self):
        self.team.members.add(self.judge_user)
        self.assign() # organizer assignment is rejected as self-dealing
        self.assertFalse(Assignment.objects.exists())
        Assignment.objects.create(judge=self.judge,project=self.project)
        self.client.force_login(self.judge_user)
        self.assertEqual(self.client.post('/judge/score/prj',self.payload()).status_code,403)
    def test_judge_on_any_competing_team_cannot_score_rival_project(self):
        rival=Team.objects.create(event=self.event,slug='rival',name='Rival')
        rival.members.add(self.judge_user)
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.post('/organizer/assign',{'judge':'jdg','project':'prj'}).status_code,400)
        Assignment.objects.create(judge=self.judge,project=self.project)
        self.client.force_login(self.judge_user)
        self.assertEqual(self.client.post('/judge/score/prj',self.payload()).status_code,403)
        self.assertFalse(Score.objects.exists())

    def test_assignment_list_owner_only(self):
        self.assign()
        self.client.force_login(self.judge_user)
        self.assertEqual(self.client.get('/judge/assignments').json()['assignments'][0]['project'],'prj')
        self.client.force_login(self.peer_user)
        self.assertEqual(self.client.get('/judge/assignments').json()['assignments'],[])
    def test_results_organizer_only_and_publish_after_close(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get('/organizer/results').status_code,403)
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get('/organizer/results').status_code,200)
        self.assertEqual(self.client.post('/organizer/publish').status_code,200)
        self.assertTrue(Event.objects.get(pk=self.event.pk).published)
    def test_publish_rejected_while_submissions_open(self):
        self.event.submissions_close=timezone.now()+timedelta(days=1);self.event.save()
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.post('/organizer/publish').status_code,409)
        self.assertFalse(Event.objects.get(pk=self.event.pk).published)
    def test_weighted_score_invalid(self):
        self.assertIsNone(weighted_score({'quality':4}))
        self.assertIsNone(weighted_score({'functionality':0,'quality':4,'innovation':4}))
        self.assertAlmostEqual(weighted_score({'functionality':4,'quality':3,'innovation':5}),3.9)
    def test_flat_judge_finite_normalization(self):
        Score.objects.create(judge=self.judge,project=self.project,criteria={'functionality':4,'quality':4,'innovation':4})
        rows=standings(self.event)
        self.assertEqual(rows[0]['normalized'],3.0)
        self.assertEqual(rows[0]['raw'],4.0)

    def test_console_assigned_only_and_saved_truth(self):
        self.assign()
        self.client.force_login(self.judge_user)
        response=self.client.get('/judge/console')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Project')
        self.assertContains(response,'Not scored')
        self.assertContains(response,'Not saved')
        self.assertNotContains(response,'peer scores')
        self.client.post('/judge/score/prj',self.payload())
        response=self.client.get('/judge/console/prj')
        self.assertContains(response,'Saved')
        self.assertContains(response,'name="functionality" value="4" required checked')
        self.assertContains(response,'name="quality" value="3" required checked')
        self.assertContains(response,'name="innovation" value="5" required checked')

    def test_console_denies_other_judge_and_unassigned_project(self):
        self.assign()
        self.client.force_login(self.peer_user)
        self.assertEqual(self.client.get('/judge/console').status_code,200)
        self.assertContains(self.client.get('/judge/console'),'queue is empty')
        self.assertEqual(self.client.get('/judge/console/prj').status_code,404)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get('/judge/console').status_code,403)

class ConcurrentFirstScoreTests(TransactionTestCase):
    """Real PostgreSQL race: first score must not raise a uniqueness 500."""
    def test_two_first_scores_serialize(self):
        from concurrent.futures import ThreadPoolExecutor
        from django.db import connection
        if connection.vendor != 'postgresql': self.skipTest('Requires PostgreSQL row locks')
        event=Event.objects.create(slug='score-race',title='Score race',submissions_close=timezone.now()-timedelta(days=1))
        track=Track.objects.create(event=event,slug='track',name='Track')
        team=Team.objects.create(event=event,slug='team',name='Team')
        project=Project.objects.create(event=event,team=team,track=track,slug='project',title='Project')
        user=get_user_model().objects.create_user(username='race-judge')
        judge=Judge.objects.create(event=event,slug='judge',user=user); judge.tracks.add(track)
        Assignment.objects.create(judge=judge,project=project)
        def post():
            from django.test import Client
            client=Client();client.force_login(user)
            try:
                return client.post('/judge/score/project',{'functionality':'4','quality':'3','innovation':'5'}).status_code
            finally:
                from django.db import connections
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses=list(executor.map(lambda _:post(),range(2)))
        self.assertEqual(statuses,[200,200])
        self.assertEqual(Score.objects.filter(judge=judge,project=project).count(),1)
        self.assertEqual(ScoreAudit.objects.filter(score__judge=judge,score__project=project).count(),2)

class ConsoleSecurityTests(TestCase):
    def test_console_does_not_show_off_track_or_another_event(self):
        now=timezone.now()
        active=Event.objects.create(slug='active',title='Active',submissions_close=now,active=True)
        other=Event.objects.create(slug='other',title='Other',submissions_close=now)
        user=get_user_model().objects.create_user(username='judge-console')
        judge=Judge.objects.create(event=active,slug='judge',user=user)
        track=Track.objects.create(event=active,slug='first',name='First')
        second=Track.objects.create(event=active,slug='second',name='Second')
        judge.tracks.add(track)
        team=Team.objects.create(event=active,slug='team',name='Team')
        good=Project.objects.create(event=active,slug='good',title='Allowed title',track=track,team=team)
        bad=Project.objects.create(event=active,slug='bad',title='Off track secret',track=second,team=team)
        Assignment.objects.create(judge=judge,project=good)
        Assignment.objects.create(judge=judge,project=bad)
        foreign_track=Track.objects.create(event=other,slug='first',name='First')
        foreign_team=Team.objects.create(event=other,slug='team',name='Team')
        foreign=Project.objects.create(event=other,slug='foreign',title='Other event secret',track=foreign_track,team=foreign_team)
        Assignment.objects.create(judge=judge,project=foreign)
        self.client.force_login(user)
        page=self.client.get('/judge/console')
        self.assertContains(page,'Allowed title')
        self.assertNotContains(page,'Off track secret')
        self.assertNotContains(page,'Other event secret')
        self.assertEqual(self.client.get('/judge/console/bad').status_code,404)
        self.assertEqual(self.client.get('/judge/console/foreign').status_code,404)

class ConsoleTemplateTruthTests(TestCase):
    def test_console_progress_is_segmented_and_honest(self):
        event=Event.objects.create(slug='console-progress',title='Progress Event',submissions_close=timezone.now(),active=True)
        track=Track.objects.create(event=event,slug='dev',name='Developer tools')
        team=Team.objects.create(event=event,slug='team',name='Team')
        user=get_user_model().objects.create_user(username='progress-judge')
        judge=Judge.objects.create(event=event,slug='judge',user=user);judge.tracks.add(track)
        first=Project.objects.create(event=event,team=team,track=track,slug='first',title='Alpha')
        second=Project.objects.create(event=event,team=team,track=track,slug='second',title='Beta')
        Assignment.objects.create(judge=judge,project=first)
        Assignment.objects.create(judge=judge,project=second)
        self.client.force_login(user)
        empty=self.client.get('/judge/console')
        self.assertContains(empty,'0 of 2 complete · 2 remaining')
        self.assertContains(empty,'rg-progress-segment',count=2)
        self.assertNotContains(empty,'rg-progress-segment is-complete')
        Score.objects.create(judge=judge,project=first,criteria={'functionality':4,'quality':4,'innovation':4})
        saved=self.client.get('/judge/console')
        self.assertContains(saved,'1 of 2 complete · 1 remaining')
        self.assertContains(saved,'rg-progress-segment is-complete',count=1)
