from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event,Project,Team,Track

class LifecycleFormRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='form-look',title='Form look',active=True,
            submissions_close=timezone.now()+timedelta(hours=1))
        cls.track=Track.objects.create(event=cls.event,slug='demo',name='Demo')
        cls.team=Team.objects.create(event=cls.event,slug='team',name='Team')
        cls.organizer=get_user_model().objects.create_superuser('form-org','form@example.org','x')
        cls.participant=get_user_model().objects.create_user('form-user')
        cls.team.members.add(cls.participant)

    def test_organizer_event_form_uses_shared_layout_and_labels(self):
        self.client.force_login(self.organizer)
        r=self.client.get('/events/new')
        self.assertContains(r,'rg-lifecycle-form')
        self.assertContains(r,'for="event-close"')
        self.assertContains(r,'name="custom_questions"')

    def test_participant_form_has_draft_and_publish_actions(self):
        self.client.force_login(self.participant)
        r=self.client.get('/projects/new')
        self.assertContains(r,'rg-lifecycle-form')
        self.assertContains(r,'value="draft"')
        self.assertContains(r,'value="publish"')
        Project.objects.create(event=self.event,team=self.team,track=self.track,slug='p',title='Draft',draft=True)
        self.assertContains(self.client.get('/projects/new'),'has not been submitted')
