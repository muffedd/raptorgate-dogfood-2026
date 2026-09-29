"""Browser form navigation and legacy JSON clients share the submission endpoint."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Project, Team, Track


class BrowserSubmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='browser-form',title='Browser form',active=True,
                                        submissions_close=timezone.now()+timedelta(hours=1))
        cls.track=Track.objects.create(event=cls.event,slug='demo',name='Demo')
        cls.team=Team.objects.create(event=cls.event,slug='browser-team',name='Browser team')
        cls.member=get_user_model().objects.create_user(username='browser-member')
        cls.team.members.add(cls.member)

    def setUp(self):
        self.client.force_login(self.member)
        self.payload={'title':'Browser entry','summary':'In the gallery','track':str(self.track.pk)}

    def post_html(self, **changes):
        return self.client.post('/projects/new',{**self.payload,**changes},
                                HTTP_ACCEPT='text/html,application/xhtml+xml')

    def test_draft_redirects_to_editable_form_without_gallery_leak(self):
        result=self.post_html(action='draft')
        self.assertRedirects(result,'/projects/new')
        self.assertContains(self.client.get(result['Location']),'has not been submitted')
        self.assertNotContains(self.client.get('/projects'),'Browser entry')

    def test_publish_redirects_to_public_project(self):
        self.post_html(action='draft')
        result=self.post_html(action='publish')
        project=Project.objects.get(event=self.event,team=self.team)
        self.assertRedirects(result,'/projects/'+project.slug)
        self.assertContains(self.client.get(result['Location']),'Browser entry')
        self.assertFalse(project.draft)

    def test_invalid_browser_submission_renders_errors_without_mutation(self):
        result=self.post_html(title='   ')
        self.assertEqual(result.status_code,400)
        self.assertContains(result,'This field is required',status_code=400)
        self.assertFalse(Project.objects.filter(event=self.event,team=self.team).exists())

    def test_explicit_json_accept_keeps_api_response(self):
        result=self.client.post('/projects/new',self.payload,HTTP_ACCEPT='application/json')
        self.assertEqual(result.status_code,201)
        self.assertEqual(result.json()['draft'],False)
