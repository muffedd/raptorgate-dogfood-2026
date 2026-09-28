"""Role-isolation regression tests: 401/403 boundaries for every protected
endpoint and role.

Conventions locked here, taken from views.py at base 8792fff:
- /api/judge/scores and /api/export.csv answer anonymous callers with a
  JSON 401; every other protected view uses login_required and redirects
  anonymous callers to /login/.
- Organizer means is_superuser on every organizer endpoint (export, assign,
  results, publish, judge invite, rubric, audit).
- Judge means a Judge row on the ACTIVE event (Event.objects.order_by('id')
  .first()); holding a Judge row on any other event grants nothing.
- /judge/accept/<token> is intentionally public so invitees can set a
  password before they have a session.
"""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Assignment, Event, Judge, Project, Team, Track

ORGANIZER_ENDPOINTS = [
    ('get', '/api/export.csv'),
    ('get', '/organizer/results'),
    ('post', '/organizer/publish'),
    ('post', '/organizer/judges/invite'),
    ('get', '/organizer/rubric'),
    ('post', '/organizer/rubric'),
    ('get', '/organizer/audit'),
    ('post', '/organizer/assign'),
]

ANONYMOUS_REDIRECT_ENDPOINTS = [
    ('get', '/projects/new'),
    ('post', '/projects/new'),
    ('post', '/teams/new'),
    ('post', '/teams/any-slug/invite'),
    ('post', '/join/any-token'),
    ('post', '/events/new'),
    ('get', '/judge/assignments'),
    ('post', '/organizer/assign'),
    ('get', '/organizer/results'),
    ('post', '/organizer/publish'),
    ('post', '/organizer/judges/invite'),
    ('get', '/organizer/rubric'),
    ('post', '/organizer/rubric'),
    ('get', '/organizer/audit'),
    ('post', '/judge/score/any-project'),
]


class RoleFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(
            slug='active', title='Active Event',
            submissions_close=timezone.now() + timedelta(days=1))
        # Created after the active event so active_event() never picks it.
        cls.later_event = Event.objects.create(
            slug='later', title='Later Event',
            submissions_close=timezone.now() + timedelta(days=1))
        cls.track = Track.objects.create(event=cls.event, slug='trk', name='Track')
        cls.team = Team.objects.create(event=cls.event, slug='team', name='Team')
        cls.project = Project.objects.create(
            event=cls.event, team=cls.team, track=cls.track,
            slug='proj', title='Project')
        User = get_user_model()
        cls.organizer = User.objects.create_superuser(
            username='tinku-org', email='org@example.org', password='x')
        cls.staffer = User.objects.create_user(username='tinku-staff', is_staff=True)
        cls.super_nostaff = User.objects.create_user(
            username='tinku-nostaff', is_superuser=True, is_staff=False)
        cls.participant = User.objects.create_user(username='tinku-participant')
        cls.team.members.add(cls.participant)
        cls.outsider = User.objects.create_user(username='tinku-outsider')
        cls.judge_user = User.objects.create_user(username='tinku-judge')
        cls.judge = Judge.objects.create(event=cls.event, slug='jdg', user=cls.judge_user)
        cls.judge.tracks.add(cls.track)
        # Holds a Judge row, but only on the non-active event.
        cls.later_judge_user = User.objects.create_user(username='tinku-later-judge')
        cls.later_judge = Judge.objects.create(
            event=cls.later_event, slug='jdg-later', user=cls.later_judge_user)

    def hit(self, method, path, data=None):
        return getattr(self.client, method)(path, data or {})


class AnonymousBoundaryTests(RoleFixtures):
    def test_score_api_answers_anonymous_with_json_401(self):
        r = self.client.get('/api/judge/scores')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()['error'], 'Sign in required')

    def test_csv_export_answers_anonymous_with_json_401(self):
        r = self.client.get('/api/export.csv')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()['error'], 'Sign in required')

    def test_anonymous_redirected_to_login_on_session_pages(self):
        for method, path in ANONYMOUS_REDIRECT_ENDPOINTS:
            with self.subTest(method=method, path=path):
                r = self.hit(method, path)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r['Location'].startswith('/login/'))

    def test_judge_accept_stays_public(self):
        # Invitees reach this without a session; it must not redirect to login.
        r = self.client.post('/judge/accept/not-a-token',
                             {'password': 'Whatever2026!', 'confirm': 'Whatever2026!'})
        self.assertEqual(r.status_code, 404)

    def test_gallery_stays_public(self):
        self.assertEqual(self.client.get('/projects').status_code, 200)


class OrganizerBoundaryTests(RoleFixtures):
    def test_participant_denied_every_organizer_endpoint(self):
        self.client.force_login(self.participant)
        for method, path in ORGANIZER_ENDPOINTS:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.hit(method, path).status_code, 403)

    def test_judge_denied_every_organizer_endpoint(self):
        self.client.force_login(self.judge_user)
        for method, path in ORGANIZER_ENDPOINTS:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.hit(method, path).status_code, 403)

    def test_staff_without_superuser_denied_superuser_gates(self):
        # Locks the is_superuser convention on every organizer endpoint, the
        # baseline that makes the create_event is_staff check anomalous.
        self.client.force_login(self.staffer)
        for method, path in ORGANIZER_ENDPOINTS:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.hit(method, path).status_code, 403)

    def test_organizer_reaches_organizer_surface(self):
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get('/organizer/results').status_code, 200)
        self.assertEqual(self.client.get('/organizer/rubric').status_code, 200)
        self.assertEqual(self.client.get('/organizer/audit').status_code, 200)
        r = self.client.get('/api/export.csv')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b'project_id,project_title'))
        # Submissions are open, so publish stops at the business rule (409),
        # proving the role gate itself was passed.
        self.assertEqual(self.client.post('/organizer/publish').status_code, 409)


class EventCreationRoleTests(RoleFixtures):
    def payload(self, slug):
        return {'name': 'New Event', 'slug': slug,
                'submissions_close': '2027-06-01T00:00:00Z'}

    def test_staff_without_superuser_cannot_create_event(self):
        # DEFECT: create_event gates on is_staff while every other organizer
        # endpoint gates on is_superuser, so a staff account locked out of the
        # whole organizer surface can still mint events. Expected 403; the
        # base tree answers 201.
        self.client.force_login(self.staffer)
        r = self.client.post('/events/new', self.payload('staff-made'))
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Event.objects.filter(slug='staff-made').exists())

    def test_superuser_without_staff_flag_keeps_event_creation(self):
        # Same defect from the other side: a superuser passes every other
        # organizer gate, so losing only event creation is inconsistent.
        # Expected 201; the base tree answers 403.
        self.client.force_login(self.super_nostaff)
        r = self.client.post('/events/new', self.payload('nostaff-made'))
        self.assertEqual(r.status_code, 201)


class JudgeBoundaryTests(RoleFixtures):
    def score_payload(self):
        return {'functionality': '4', 'quality': '3', 'innovation': '5'}

    def test_organizer_is_not_a_judge(self):
        # Superuser status confers no judge rights without a Judge row.
        self.client.force_login(self.organizer)
        self.assertEqual(self.client.get('/api/judge/scores').status_code, 403)
        self.assertEqual(self.client.get('/judge/assignments').status_code, 403)
        self.assertEqual(
            self.client.post('/judge/score/proj', self.score_payload()).status_code, 403)

    def test_participant_denied_judge_endpoints(self):
        self.client.force_login(self.participant)
        self.assertEqual(self.client.get('/api/judge/scores').status_code, 403)
        self.assertEqual(self.client.get('/judge/assignments').status_code, 403)
        self.assertEqual(
            self.client.post('/judge/score/proj', self.score_payload()).status_code, 403)

    def test_judge_role_scoped_to_active_event(self):
        # A Judge row on a non-active event grants nothing on the active one.
        self.client.force_login(self.later_judge_user)
        self.assertEqual(self.client.get('/api/judge/scores').status_code, 403)
        self.assertEqual(self.client.get('/judge/assignments').status_code, 403)
        self.assertEqual(
            self.client.post('/judge/score/proj', self.score_payload()).status_code, 403)

    def test_assigned_judge_scores_but_stays_off_organizer_surface(self):
        Assignment.objects.create(judge=self.judge, project=self.project)
        self.client.force_login(self.judge_user)
        self.assertEqual(
            self.client.post('/judge/score/proj', self.score_payload()).status_code, 200)
        r = self.client.get('/api/judge/scores')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['judge'], 'jdg')
        self.assertEqual(self.client.get('/api/export.csv').status_code, 403)
        self.assertEqual(self.client.get('/organizer/results').status_code, 403)


class SubmitBoundaryTests(RoleFixtures):
    def payload(self):
        return {'title': 'Candidate', 'summary': 'A real project',
                'repo_url': 'https://example.org/repo', 'track': str(self.track.pk)}

    def test_users_without_team_membership_cannot_submit(self):
        # The submit gate is team membership; elevated roles get no bypass.
        for user in (self.organizer, self.judge_user, self.outsider):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                r = self.client.post('/projects/new', self.payload())
                self.assertEqual(r.status_code, 403)
                self.assertEqual(r.json()['error'], 'Join a team before submitting')
        self.assertFalse(Project.objects.filter(
            event=self.event, title='Candidate').exists())
