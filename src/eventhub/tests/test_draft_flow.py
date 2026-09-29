"""Participant draft lifecycle and submission boundary."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Project, Team, Track


class DraftFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(slug='draft-flow', title='Draft flow',
                                         submissions_close=timezone.now()+timedelta(hours=1))
        cls.track = Track.objects.create(event=cls.event, slug='dev', name='Dev')
        cls.team = Team.objects.create(event=cls.event, slug='one', name='One')
        cls.other = Team.objects.create(event=cls.event, slug='two', name='Two')
        User = get_user_model()
        cls.member = User.objects.create_user(username='draft-member')
        cls.stranger = User.objects.create_user(username='draft-stranger')
        cls.team.members.add(cls.member)
        cls.other.members.add(cls.stranger)

    def payload(self, **extra):
        return {'title':'Private title', 'summary':'Initial', 'track':str(self.track.pk),
                'repo_url':'https://example.com/repo', 'action':'draft', **extra}

    def test_save_return_edit_and_publish_in_place(self):
        self.client.force_login(self.member)
        created = self.client.post('/projects/new', self.payload())
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json()['draft'])
        project = Project.objects.get(team=self.team)
        self.assertTrue(project.draft)
        self.assertIsNone(project.submitted_at)
        self.assertNotContains(self.client.get('/projects'), 'Private title')
        page = self.client.get('/projects/new')
        self.assertContains(page, 'Private title')
        self.assertContains(page, 'has not been submitted')
        self.assertContains(page, 'Publish draft')
        edited = self.client.post('/projects/new', self.payload(title='Edited private'))
        self.assertEqual(edited.status_code, 200)
        self.assertTrue(edited.json()['updated'])
        self.assertEqual(Project.objects.filter(team=self.team).count(), 1)
        self.assertNotContains(self.client.get('/projects'), 'Edited private')
        published = self.client.post('/projects/new', self.payload(title='Published',action='publish'))
        self.assertEqual(published.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.pk, Project.objects.get(team=self.team).pk)
        self.assertFalse(project.draft)
        self.assertIsNotNone(project.submitted_at)
        self.assertContains(self.client.get('/projects'), 'Published')
        self.assertNotContains(self.client.get('/projects/new'), 'Save draft')

    def test_draft_cannot_be_published_or_changed_after_deadline(self):
        self.client.force_login(self.member)
        self.client.post('/projects/new', self.payload())
        self.event.submissions_close = timezone.now()-timedelta(seconds=1)
        self.event.save(update_fields=['submissions_close'])
        self.assertEqual(self.client.post('/projects/new', self.payload(action='publish')).status_code, 403)
        self.assertEqual(self.client.post('/projects/new', self.payload(title='Late')).status_code, 403)
        project = Project.objects.get(team=self.team)
        self.assertTrue(project.draft)
        self.assertEqual(project.title, 'Private title')
        self.assertNotContains(self.client.get('/projects/new'), 'Publish draft')

    def test_draft_is_private_between_teams(self):
        self.client.force_login(self.member)
        self.client.post('/projects/new', self.payload())
        self.client.force_login(self.stranger)
        self.assertNotContains(self.client.get('/projects/new'), 'Private title')
        self.assertEqual(self.client.post('/projects/new', self.payload(title='Theirs')).status_code, 201)
        self.assertEqual(Project.objects.filter(event=self.event).count(), 2)
        self.assertNotContains(self.client.get('/projects'), 'Private title')

    def test_published_cannot_be_silently_unpublished(self):
        self.client.force_login(self.member)
        self.client.post('/projects/new', self.payload(action='publish'))
        result = self.client.post('/projects/new', self.payload(title='Hidden again'))
        self.assertEqual(result.status_code, 409)
        project = Project.objects.get(team=self.team)
        self.assertFalse(project.draft)
        self.assertEqual(project.title, 'Private title')

    def test_invalid_action_rejected_without_creation(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.post('/projects/new',self.payload(action='unpublish')).status_code,400)
        self.assertFalse(Project.objects.filter(team=self.team).exists())
