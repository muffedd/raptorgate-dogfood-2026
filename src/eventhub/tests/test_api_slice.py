"""T4 partial API contract: explicit bearer tokens, isolated judge reads, public gates."""
from datetime import timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from eventhub.models import APIToken, Assignment, Event, Judge, Project, Score, Team, Track

class APISliceTests(TestCase):
    def setUp(self):
        self.event=Event.objects.create(slug='api',title='API',active=True,
               submissions_close=timezone.now()-timedelta(days=1),
               voting_opens=timezone.now()-timedelta(days=1),voting_closes=timezone.now()+timedelta(days=1))
        self.track=Track.objects.create(event=self.event,slug='dev',name='Dev')
        team=Team.objects.create(event=self.event,slug='team',name='Team')
        self.project=Project.objects.create(event=self.event,team=team,track=self.track,slug='p',title='Visible')
        Project.objects.create(event=self.event,team=team,track=self.track,slug='secret',title='Hidden',draft=True)
        u=get_user_model();self.judge_user=u.objects.create_user(username='api-judge')
        self.other_user=u.objects.create_user(username='api-other')
        self.org=u.objects.create_superuser(username='api-org',email='org@example.org',password='x')
        self.judge=Judge.objects.create(event=self.event,slug='j',user=self.judge_user);self.judge.tracks.add(self.track)
        Assignment.objects.create(judge=self.judge,project=self.project)
        Score.objects.create(judge=self.judge,project=self.project,criteria={'functionality':4,'quality':4,'innovation':4})

    def token(self,user):
        self.client.force_login(user)
        response=self.client.post('/api/v1/tokens',{'name':'client'})
        self.assertEqual(response.status_code,201)
        self.assertEqual(response['Cache-Control'],'no-store')
        data=response.json();self.client.logout()
        self.assertNotEqual(data['token'],APIToken.objects.get(pk=data['id']).token_hash)
        return data

    def test_public_project_scope_and_result_gate(self):
        page=self.client.get('/api/v1/projects')
        self.assertEqual(page.status_code,200)
        self.assertEqual([r['slug'] for r in page.json()['projects']],['p'])
        self.assertEqual(self.client.get('/api/v1/projects?event=foreign').status_code,404)
        self.assertEqual(self.client.get('/api/v1/results').status_code,404)
        self.event.published=True;self.event.voting_closes=timezone.now()-timedelta(seconds=1);self.event.save()
        self.assertEqual(self.client.get('/api/v1/results').status_code,200)

    def test_bearer_judge_assignments_and_revocation(self):
        token=self.token(self.judge_user)
        header={'HTTP_AUTHORIZATION':'Bearer '+token['token']}
        page=self.client.get('/api/v1/judge/assignments',**header)
        self.assertEqual(page.status_code,200)
        self.assertEqual(page.json()['assignments'][0]['project'],'p')
        self.assertEqual(self.client.get('/api/v1/judge/assignments').status_code,401)
        self.assertEqual(self.client.get('/api/v1/judge/assignments',HTTP_AUTHORIZATION='Bearer '+token['token'][:-1]+'z').status_code,401)
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.post(f"/api/v1/tokens/{token['id']}/revoke").status_code,404)
        self.client.force_login(self.judge_user)
        self.assertEqual(self.client.post(f"/api/v1/tokens/{token['id']}/revoke").status_code,200)
        self.assertEqual(self.client.get('/api/v1/judge/assignments',**header).status_code,401)

    def test_bearer_is_user_bound_and_expiry_enforced(self):
        token=self.token(self.other_user)
        header={'HTTP_AUTHORIZATION':'Bearer '+token['token']}
        self.assertEqual(self.client.get('/api/v1/judge/assignments',**header).status_code,403)
        APIToken.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.get('/api/v1/judge/assignments',**header).status_code,401)
        self.assertEqual(self.client.post('/api/v1/tokens',{'name':'x'}).status_code,401)

    def test_seeded_first_event_is_usable_without_selection(self):
        token=self.token(self.judge_user)
        Event.objects.filter(pk=self.event.pk).update(active=False)
        self.assertEqual(self.client.get('/api/v1/projects').json()['event'],self.event.slug)
        self.assertEqual(self.client.get('/api/v1/judge/assignments',HTTP_AUTHORIZATION='Bearer '+token['token']).json()['assignments'][0]['project'],'p')
        self.assertEqual(self.client.get('/api/v1/projects?event=foreign').status_code,404)

    def test_no_event_fails_closed(self):
        token=self.token(self.judge_user)
        Score.objects.all().delete()
        Assignment.objects.all().delete()
        Project.objects.all().delete()
        Event.objects.all().delete()
        self.assertEqual(self.client.get('/api/v1/projects').status_code,404)
        self.assertEqual(self.client.get('/api/v1/judge/assignments',HTTP_AUTHORIZATION='Bearer '+token['token']).status_code,404)
