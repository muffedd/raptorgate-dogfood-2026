from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Assignment, Event, Judge, Project, Score, Team, Track


class BatchAssignmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='batch',title='Batch',active=True,submissions_close=timezone.now()-timedelta(days=1))
        cls.other=Event.objects.create(slug='elsewhere',title='Elsewhere',submissions_close=timezone.now()-timedelta(days=1))
        cls.a=Track.objects.create(event=cls.event,slug='a',name='Alpha')
        cls.b=Track.objects.create(event=cls.event,slug='b',name='Beta')
        cls.team=Team.objects.create(event=cls.event,slug='one',name='One')
        cls.projects=[Project.objects.create(event=cls.event,track=cls.a,team=cls.team,slug=f'a{i}',title=f'A{i}') for i in range(4)]
        cls.bproject=Project.objects.create(event=cls.event,track=cls.b,team=cls.team,slug='b',title='B')
        cls.draft=Project.objects.create(event=cls.event,track=cls.a,team=cls.team,slug='draft',title='Draft',draft=True)
        cls.duplicate=Project.objects.create(event=cls.event,track=cls.a,team=cls.team,slug='duplicate',title='Duplicate',duplicate_of=cls.projects[0])
        cls.foreign_track=Track.objects.create(event=cls.other,slug='a',name='Other')
        cls.foreign_team=Team.objects.create(event=cls.other,slug='other',name='Other')
        cls.foreign=Project.objects.create(event=cls.other,track=cls.foreign_track,team=cls.foreign_team,slug='foreign',title='Foreign')
        U=get_user_model()
        cls.organizer=U.objects.create_superuser('batch-org','batch-org@example.org','pw')
        cls.judges=[]
        for name, tracks in [('alpha1',[cls.a]),('alpha2',[cls.a]),('beta',[cls.b]),('conflicted',[cls.a])]:
            user=U.objects.create_user(name)
            judge=Judge.objects.create(event=cls.event,slug=name,user=user)
            judge.tracks.add(*tracks)
            cls.judges.append(judge)
        cls.team.members.add(cls.judges[-1].user)
        cls.participant=U.objects.create_user('batch-participant')

    def batch(self, **values):
        return self.client.post('/organizer/assign/batch',values)

    def test_balanced_scoped_idempotent_and_competing_team_excluded(self):
        self.client.force_login(self.organizer)
        response=self.batch(reviews_per_project='2',max_per_judge='4')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['created'],9)
        self.assertEqual(response.json()['under_target_projects'],1)
        rows=list(Assignment.objects.all())
        self.assertEqual(len(rows),9)
        self.assertTrue(all(x.project.event_id==self.event.pk and x.project.track_id in x.judge.tracks.values_list('pk',flat=True) for x in rows))
        self.assertFalse(any(x.judge_id==self.judges[-1].pk or x.project_id in (self.draft.pk,self.duplicate.pk,self.foreign.pk) for x in rows))
        self.assertEqual([Assignment.objects.filter(judge=j).count() for j in self.judges], [4,4,1,0])
        self.assertEqual(self.batch(reviews_per_project='2',max_per_judge='4').json()['created'],0)

    def test_existing_assignments_kept_and_caps_respected(self):
        Assignment.objects.create(judge=self.judges[0],project=self.projects[0])
        self.client.force_login(self.organizer)
        result=self.batch(reviews_per_project='1',max_per_judge='2').json()
        self.assertEqual(result['created'],4)
        self.assertEqual(result['under_target_projects'],0)
        self.assertEqual(Assignment.objects.filter(judge=self.judges[0],project=self.projects[0]).count(),1)
        self.assertTrue(all(Assignment.objects.filter(judge=j).count()<=2 for j in self.judges))

    def test_role_method_and_limits(self):
        self.client.force_login(self.participant)
        self.assertEqual(self.batch().status_code,403)
        self.client.force_login(self.judges[0].user)
        self.assertEqual(self.batch().status_code,403)
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get('/organizer/assign/batch').status_code,405)
        for value in ('0','11','NaN','1.2',''):
            self.assertEqual(self.batch(reviews_per_project=value).status_code,400)
        self.assertEqual(self.batch(max_per_judge='101').status_code,400)
        self.assertFalse(Assignment.objects.exists())

    def test_progress_only_counts_live_assignments_and_valid_completion(self):
        Assignment.objects.create(judge=self.judges[0],project=self.projects[0])
        Assignment.objects.create(judge=self.judges[0],project=self.projects[1])
        Assignment.objects.create(judge=self.judges[1],project=self.projects[2])
        Assignment.objects.create(judge=self.judges[0],project=self.foreign)
        Score.objects.create(judge=self.judges[0],project=self.projects[0],criteria={'functionality':4,'quality':3,'innovation':5})
        Score.objects.create(judge=self.judges[0],project=self.projects[1],criteria={'quality':4})
        Score.objects.create(judge=self.judges[0],project=self.projects[3],criteria={'functionality':4,'quality':3,'innovation':5})
        self.client.force_login(self.organizer)
        page=self.client.get('/organizer/overview')
        self.assertEqual(page.status_code,200)
        rows={x['slug']:x for x in page.context['judge_progress']}
        self.assertEqual({k:rows['alpha1'][k] for k in ('assigned','started','completed','not_started')},
                         {'assigned':2,'started':2,'completed':1,'not_started':False})
        self.assertTrue(rows['alpha2']['not_started'])
        self.assertFalse(rows['beta']['not_started'])
        self.assertContains(page,'Not started')
        self.assertContains(page,'Fill assignment gaps')
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get('/organizer/overview').status_code,403)
