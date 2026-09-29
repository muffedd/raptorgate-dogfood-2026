"""An optional event prize survives organizer creation and public rendering."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Project, Team, Track


class EventPrizeTests(TestCase):
    def setUp(self):
        user=get_user_model().objects.create_user('prize-organizer',password='test-only')
        user.is_superuser=True
        user.save(update_fields=['is_superuser'])
        self.client.force_login(user)

    def test_optional_prize_creation_and_public_display(self):
        close=(timezone.now()+timedelta(days=2)).isoformat()
        result=self.client.post('/events/new',{
            'name':'Prize Demo','slug':'prize-demo','prize':'Best Judging Engine',
            'submissions_close':close})
        self.assertEqual(result.status_code,201)
        event=Event.objects.get(slug='prize-demo')
        self.assertEqual(event.prize,'Best Judging Engine')
        event.active=True;event.save(update_fields=['active'])
        team=Team.objects.create(event=event,slug='team',name='Sample team')
        track=Track.objects.create(event=event,slug='track',name='Sample track')
        Project.objects.create(event=event,team=team,track=track,slug='project',title='Sample project')
        self.assertContains(self.client.get('/projects'),'Prize: Best Judging Engine')
        self.assertContains(self.client.get('/projects/project'),'Prize:')
        self.assertContains(self.client.get('/projects/project'),'Best Judging Engine')

    def test_optional_prize_defaults_blank_and_rejects_overlong(self):
        close=(timezone.now()+timedelta(days=2)).isoformat()
        self.assertEqual(self.client.post('/events/new',{
            'name':'Blank Prize','slug':'blank-prize','submissions_close':close}).status_code,201)
        self.assertEqual(Event.objects.get(slug='blank-prize').prize,'')
        self.assertEqual(self.client.post('/events/new',{
            'name':'Long Prize','slug':'long-prize','prize':'x'*241,
            'submissions_close':close}).status_code,400)
        self.assertFalse(Event.objects.filter(slug='long-prize').exists())
        self.assertContains(self.client.get('/events/new'),'name="prize"')
