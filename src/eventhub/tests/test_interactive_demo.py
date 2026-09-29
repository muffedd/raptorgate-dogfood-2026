"""The disposable public demo never grants privileged or shared accounts."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from eventhub.models import Assignment, Event, Judge, Project, Team, Track
from eventhub.management.commands.seed_interactive import Command

@override_settings(DEMO=True)
class InteractiveDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='interactive-demo',title='Demo',active=True,
            submissions_close=timezone.now()+timedelta(days=7),
            voting_opens=timezone.now()-timedelta(hours=1),
            voting_closes=timezone.now()+timedelta(days=7))
        cls.track=Track.objects.create(event=cls.event,slug='build',name='Build')
        team=Team.objects.create(event=cls.event,slug='sample',name='Sample')
        Project.objects.create(event=cls.event,slug='sample',team=team,track=cls.track,title='Sample')

    def test_role_switch_and_identity_isolation(self):
        self.assertEqual(self.client.get('/demo').status_code,200)
        self.assertEqual(self.client.get('/demo/enter').status_code,405)
        self.assertEqual(self.client.post('/demo/enter').status_code,302)
        participant_id=self.client.session['demo_participant']
        judge_id=self.client.session['demo_judge']
        self.assertNotEqual(participant_id,judge_id)
        User=get_user_model()
        self.assertFalse(User.objects.get(pk=participant_id).has_usable_password())
        self.assertFalse(User.objects.get(pk=judge_id).is_staff)
        self.assertFalse(User.objects.get(pk=judge_id).is_superuser)
        self.assertEqual(self.client.get('/judge/console').status_code,403)
        self.assertEqual(self.client.post('/demo/switch',{'role':'judge'}).status_code,302)
        self.assertEqual(self.client.session['demo_participant'],participant_id)
        self.assertEqual(self.client.session['demo_judge'],judge_id)
        self.assertContains(self.client.get('/judge/console'),'Sample')
        self.assertEqual(Assignment.objects.filter(judge__user_id=judge_id).count(),1)
        from portal.demo_middleware import InteractiveDemoRoleBoundary
        request=type('Request',(),{'path':'/teams/new','method':'POST','session':{'demo_role':'judge'}})()
        self.assertEqual(InteractiveDemoRoleBoundary(lambda r: None)(request).status_code,405)
        self.assertEqual(self.client.post('/demo/switch',{'role':'participant'}).status_code,302)
        self.assertEqual(self.client.session['demo_participant'],participant_id)
        self.assertEqual(self.client.get('/judge/console').status_code,403)
        second=self.client_class()
        self.assertEqual(second.post('/demo/enter').status_code,302)
        self.assertNotEqual(second.session['demo_participant'],participant_id)
        self.assertNotEqual(second.session['demo_judge'],judge_id)

    def test_non_demo_roles_and_public_signup_blocked_by_boundary(self):
        from portal.demo_middleware import InteractiveDemoBoundary
        boundary=InteractiveDemoBoundary(lambda request: None)
        for path in ('/signup/','/admin/','/organizer/publish','/events/new','/api/v1/tokens','/projects/another-project'):
            response=boundary(type('Request',(),{'path':path,'method':'POST'})())
            self.assertEqual(response.status_code,405,path)
        self.assertEqual(self.client.post('/demo/switch',{'role':'organizer'}).status_code,405)

    def test_limit_new_identities(self):
        for i in range(6):
            client=self.client_class()
            self.assertEqual(client.post('/demo/enter').status_code,302)
        self.assertEqual(self.client.post('/demo/enter').status_code,429)

    def test_real_csrf_and_actual_workflows(self):
        from django.test import Client
        browser=Client(enforce_csrf_checks=True)
        self.assertEqual(browser.post('/demo/enter').status_code,403)
        browser.get('/demo')
        token=browser.cookies['csrftoken'].value
        self.assertEqual(browser.post('/demo/enter',HTTP_X_CSRFTOKEN=token).status_code,302)
        token=browser.cookies['csrftoken'].value
        self.assertEqual(browser.post('/teams/new', {'name':'Visitor team'},HTTP_X_CSRFTOKEN=token).status_code,201)
        track=self.track
        self.assertEqual(browser.post('/projects/new',{'title':'Visitor project','track':track.pk,'action':'publish'},HTTP_X_CSRFTOKEN=token).status_code,201)
        self.assertEqual(browser.post('/demo/switch',{'role':'judge'},HTTP_X_CSRFTOKEN=token).status_code,302)
        token=browser.cookies['csrftoken'].value
        self.assertEqual(browser.post('/judge/score/sample',{'functionality':5,'quality':4,'innovation':3},HTTP_X_CSRFTOKEN=token).status_code,200)
        self.assertEqual(browser.post('/demo/switch',{'role':'participant'},HTTP_X_CSRFTOKEN=token).status_code,302)
        token=browser.cookies['csrftoken'].value
        self.assertEqual(browser.get('/ballot').status_code,200)
        self.assertEqual(browser.post('/vote',{'project':'sample','event':'interactive-demo'},HTTP_X_CSRFTOKEN=token).status_code,201)
        self.assertEqual(browser.post('/vote',{'project':'sample','event':'interactive-demo'},HTTP_X_CSRFTOKEN=token).status_code,409)
