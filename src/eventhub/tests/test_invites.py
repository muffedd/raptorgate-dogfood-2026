from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, Track

class JudgeInviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='a',title='A',submissions_close=timezone.now()-timedelta(days=1))
        cls.track=Track.objects.create(event=cls.event,slug='first',name='First')
        other=Event.objects.create(slug='b',title='B',submissions_close=timezone.now()-timedelta(days=1))
        cls.offtrack=Track.objects.create(event=other,slug='other',name='Other')
        User=get_user_model()
        cls.organizer=User.objects.create_superuser(username='admin-inv',email='admin@example.org',password='x')
        cls.outsider=User.objects.create_user(username='outsider')
    def invite(self,**overrides):
        return self.client.post('/organizer/judges/invite',{'email':'new@example.org','tracks':['first'],**overrides})
    def test_only_organizer_can_invite(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.invite().status_code,403)
    def test_email_and_track_validation(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.invite(email='bad').status_code,400)
        self.assertEqual(self.invite(tracks=['other']).status_code,400)
        self.assertEqual(self.invite(tracks=[]).status_code,400)
    def test_invite_one_use_and_password(self):
        self.client.force_login(self.organizer)
        response=self.invite()
        self.assertEqual(response.status_code,201)
        path=response.json()['accept_path']
        self.assertEqual(self.invite().status_code,409)
        self.client.logout()
        self.assertEqual(self.client.post(path,{'password':'x','confirm':'y'}).status_code,400)
        self.assertEqual(self.client.post(path,{'password':'StrongFixturePass2026!','confirm':'StrongFixturePass2026!'}).status_code,200)
        self.assertEqual(self.client.post(path,{'password':'StrongFixturePass2026!','confirm':'StrongFixturePass2026!'}).status_code,404)
        self.assertTrue(get_user_model().objects.get(username='invited:new@example.org').check_password('StrongFixturePass2026!'))
    def test_expired_invite(self):
        self.client.force_login(self.organizer)
        path=self.invite().json()['accept_path']
        judge=Judge.objects.get(event=self.event,user__username='invited:new@example.org')
        judge.invite_expires_at=timezone.now()-timedelta(seconds=1);judge.save()
        self.client.logout()
        self.assertEqual(self.client.post(path,{'password':'StrongFixturePass2026!','confirm':'StrongFixturePass2026!'}).status_code,404)
