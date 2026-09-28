"""Embeddable gallery widget: slug validation, canonical-only visibility,
escaping, no private data, and embedding headers.

The widget's URL is wired by the core owner after review, so these tests
mount the view on a test-only URLConf - no shared urls.py change here.
"""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import path
from django.utils import timezone

from eventhub.models import Event, Judge, Project, Score, Team, Track
from eventhub.widget import widget_gallery

urlpatterns = [
    path('embed/<str:event_slug>/gallery', widget_gallery, name='widget_gallery'),
    path('embed/<slug:event_slug>/gallery', widget_gallery, name='widget_gallery_slug'),
]


@override_settings(ROOT_URLCONF='eventhub.tests.test_widget')
class WidgetGalleryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(
            slug='sample-hack', title='Sample Hack 2026',
            submissions_close=timezone.now() - timedelta(days=1),
        )
        cls.other = Event.objects.create(
            slug='other-event', title='Other Event',
            submissions_close=timezone.now() - timedelta(days=1),
        )
        track = Track.objects.create(event=cls.event, slug='dev', name='Developer tools')
        team = Team.objects.create(event=cls.event, slug='nightshift', name='Nightshift')
        cls.canonical = Project.objects.create(
            event=cls.event, track=track, team=team, slug='quiet-hours',
            title='Quiet Hours', summary='Silences noisy chats.',
            repo_url='https://example.org/repo',
        )
        cls.duplicate = Project.objects.create(
            event=cls.event, track=track, team=team, slug='quiet-hours-2',
            title='Quiet Hours resubmit', duplicate_of=cls.canonical,
        )
        cls.draft = Project.objects.create(
            event=cls.event, track=track, team=team, slug='wip',
            title='Unfinished draft', draft=True,
        )
        cls.xss = Project.objects.create(
            event=cls.event, track=track, team=team, slug='xss',
            title='<script>alert(1)</script>',
            summary='<img src=x onerror=alert(2)>',
        )
        other_track = Track.objects.create(event=cls.other, slug='dev', name='Developer tools')
        other_team = Team.objects.create(event=cls.other, slug='blue', name='Blue Parrot')
        cls.foreign = Project.objects.create(
            event=cls.other, track=other_track, team=other_team, slug='cargo-cult',
            title='Cargo Cult',
        )
        # Judge and score rows exist in the same event and must never leak.
        from django.contrib.auth import get_user_model
        judge_user = get_user_model().objects.create_user(username='widget-judge')
        cls.judge = Judge.objects.create(event=cls.event, slug='jdg_01', user=judge_user)
        cls.judge.tracks.add(track)
        Score.objects.create(
            judge=cls.judge, project=cls.canonical,
            criteria={'functionality': 4, 'quality': 3, 'innovation': 4},
            comment='judge-only comment',
        )

    def url(self, slug):
        return f'/embed/{slug}/gallery'

    def test_valid_slug_renders_canonical_projects(self):
        page = self.client.get(self.url('sample-hack'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Quiet Hours')
        self.assertContains(page, 'Nightshift')
        self.assertContains(page, 'Developer tools')
        self.assertContains(page, 'https://example.org/repo')

    def test_unknown_event_is_404(self):
        self.assertEqual(self.client.get(self.url('no-such-event')).status_code, 404)

    def test_malformed_slug_is_404_not_500(self):
        self.assertEqual(self.client.get(self.url('BAD SLUG!!')).status_code, 404)
        self.assertEqual(self.client.get(self.url('a' * 300)).status_code, 404)

    def test_draft_and_duplicate_are_hidden(self):
        page = self.client.get(self.url('sample-hack'))
        self.assertNotContains(page, 'Unfinished draft')
        self.assertNotContains(page, 'Quiet Hours resubmit')

    def test_other_event_projects_are_hidden(self):
        page = self.client.get(self.url('sample-hack'))
        self.assertNotContains(page, 'Cargo Cult')
        other_page = self.client.get(self.url('other-event'))
        self.assertContains(other_page, 'Cargo Cult')
        self.assertNotContains(other_page, 'Quiet Hours')

    def test_content_is_escaped(self):
        page = self.client.get(self.url('sample-hack'))
        self.assertNotContains(page, '<script>alert(1)</script>')
        body = page.content.decode()
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', body)
        self.assertNotIn('<img src=x onerror=alert(2)>', body)
        self.assertIn('&lt;img src=x onerror=alert(2)&gt;', body)

    def test_no_judge_or_score_data_leaks(self):
        page = self.client.get(self.url('sample-hack'))
        self.assertNotContains(page, 'jdg_01')
        self.assertNotContains(page, 'judge-only comment')
        self.assertNotContains(page, 'widget-judge')
        self.assertNotContains(page, 'functionality')

    def test_embedding_headers(self):
        page = self.client.get(self.url('sample-hack'))
        # Frameable by design (exempt), but locked down and explicit.
        self.assertNotEqual(page.headers.get('X-Frame-Options'), 'DENY')
        csp = page.headers['Content-Security-Policy']
        self.assertIn("default-src 'none'", csp)
        self.assertIn('frame-ancestors *', csp)
        self.assertIn("form-action 'none'", csp)
        self.assertEqual(page.headers['X-Content-Type-Options'], 'nosniff')
        self.assertFalse(page.cookies, 'widget must not set cookies')

    @override_settings(WIDGET_FRAME_ANCESTORS="'self' https://event.example")
    def test_frame_ancestors_setting_is_honored(self):
        page = self.client.get(self.url('sample-hack'))
        csp = page.headers['Content-Security-Policy']
        self.assertIn("frame-ancestors 'self' https://event.example", csp)
