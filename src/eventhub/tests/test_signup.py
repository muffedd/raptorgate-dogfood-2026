from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge


class ParticipantSignupTests(TestCase):
    def payload(self, **overrides):
        return {'username': 'newparticipant', 'password1': 'UniquePassphrase2026!Fly',
                'password2': 'UniquePassphrase2026!Fly', **overrides}

    def test_public_signup_and_login_without_role_grant(self):
        Event.objects.create(slug='signup-event', title='Signup event', submissions_close=timezone.now())
        self.assertEqual(self.client.get('/signup/').status_code, 200)
        response = self.client.post('/signup/', self.payload())
        self.assertRedirects(response, '/login/')
        user = get_user_model().objects.get(username='newparticipant')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(Judge.objects.filter(user=user).exists())
        self.assertTrue(self.client.login(username='newparticipant', password='UniquePassphrase2026!Fly'))
        self.assertEqual(self.client.get('/api/judge/scores').status_code, 403)

    def test_duplicate_username_and_password_validation(self):
        get_user_model().objects.create_user(username='newparticipant')
        for payload in (self.payload(), self.payload(username='different', password1='short', password2='short'),
                        self.payload(username='different', password2='mismatch'),
                        self.payload(username='different', password1='password', password2='password')):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post('/signup/', payload).status_code, 400)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_other_methods_and_authenticated_users(self):
        self.assertEqual(self.client.put('/signup/').status_code, 405)
        self.client.force_login(get_user_model().objects.create_user(username='existing'))
        self.assertRedirects(self.client.post('/signup/', self.payload()), '/projects')
        self.assertFalse(get_user_model().objects.filter(username='newparticipant').exists())

    def test_privilege_fields_injected_into_public_form_are_ignored(self):
        response = self.client.post('/signup/', self.payload(is_staff='on', is_superuser='on'))
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='newparticipant')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(Judge.objects.filter(user=user).exists())
