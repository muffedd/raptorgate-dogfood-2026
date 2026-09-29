from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event,Project,Team,Track

class EditQuestionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='qedit',title='Q edit',active=True,
            submissions_close=timezone.now()+timedelta(hours=2),
            custom_questions=[{'key':'stack','label':'Stack','required':True}])
        cls.track=Track.objects.create(event=cls.event,slug='demo',name='Demo')
        cls.team=Team.objects.create(event=cls.event,slug='team',name='Team')
        cls.org=get_user_model().objects.create_superuser(username='qeditor',email='qeditor@example.org',password='x')
        cls.participant=get_user_model().objects.create_user(username='participant-qeditor')

    def test_role_and_method_boundary(self):
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get('/organizer/questions').status_code,403)
        self.assertEqual(self.client.post('/organizer/questions',{'custom_questions':'[]'}).status_code,403)
        self.client.force_login(self.org)
        self.assertEqual(self.client.put('/organizer/questions').status_code,405)

    def test_edit_before_submission_and_invalid_rejection(self):
        self.client.force_login(self.org)
        self.assertContains(self.client.get('/organizer/questions'),'Stack')
        self.assertEqual(self.client.post('/organizer/questions',{'custom_questions':'not json'}).status_code,400)
        self.assertEqual(self.client.post('/organizer/questions',{'custom_questions':'[{"key":"bad key","label":"Bad"}]'}).status_code,400)
        self.event.refresh_from_db()
        self.assertEqual(len(self.event.custom_questions),1)
        result=self.client.post('/organizer/questions',{'custom_questions':'[{"key":"new","label":"New question","required":false}]'},HTTP_ACCEPT='text/html')
        self.assertRedirects(result,'/organizer/overview')
        self.event.refresh_from_db()
        self.assertEqual(self.event.custom_questions,[{'key':'new','label':'New question','required':False}])

    def test_existing_submission_freezes_keys_and_required_flags(self):
        Project.objects.create(event=self.event,team=self.team,track=self.track,slug='submitted',title='Submitted')
        self.client.force_login(self.org)
        self.assertEqual(self.client.post('/organizer/questions',{'custom_questions':'[]'}).status_code,409)
        self.assertEqual(self.client.post('/organizer/questions',{'custom_questions':'[{"key":"stack","label":"Stack","required":false}]'}).status_code,409)
        result=self.client.post('/organizer/questions',{'custom_questions':'[{"key":"stack","label":"Technology stack","required":true}]'})
        self.assertEqual(result.status_code,200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.custom_questions[0]['label'],'Technology stack')
