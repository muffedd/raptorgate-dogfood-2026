from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
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
