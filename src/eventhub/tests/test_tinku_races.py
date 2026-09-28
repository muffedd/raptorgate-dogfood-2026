"""Real overlapping requests for the submission and invitation transaction boundaries.

These tests require PostgreSQL: SQLite does not implement SELECT FOR UPDATE and
its database-wide writer lock produces a different result for these schedules.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event as ThreadEvent, get_ident
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.db.models.query import QuerySet
from django.test import Client, TransactionTestCase
from django.utils import timezone

from eventhub.models import Event, Judge, Project, Team, Track


class ConcurrentPortalTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Real row-lock races require PostgreSQL SELECT FOR UPDATE')
        self.event = Event.objects.create(
            slug='race-event', title='Race event',
            submissions_close=timezone.now() + timedelta(days=1),
        )
        self.track = Track.objects.create(event=self.event, slug='main', name='Main')
        self.member = get_user_model().objects.create_user(username='race-member')
        self.team = Team.objects.create(event=self.event, slug='race-team', name='Race team')
        self.team.members.add(self.member)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def submit_data(self, title):
        return {'title': title, 'summary': title, 'repo_url': 'https://example.org/repo',
                'track': str(self.track.pk)}

    @staticmethod
    def post(client, path, data=None):
        try:
            return client.post(path, data or {})
        finally:
            connections.close_all()

    def test_two_first_submissions_serialize_on_team_and_leave_one_canonical(self):
        first = self.client_for(self.member)
        second = self.client_for(self.member)
        first_at_canonical = ThreadEvent()
        release_first = ThreadEvent()
        first_ident = [None]
        original_first = QuerySet.first
        original_select = QuerySet.select_for_update

        def pause_at_canonical(queryset, *args, **kwargs):
            if queryset.model is Project and not first_at_canonical.is_set():
                first_ident[0] = get_ident()
                first_at_canonical.set()
                if not release_first.wait(10):
                    raise AssertionError('Second submission never reached the team lock')
            return original_first(queryset, *args, **kwargs)

        def observe_team_lock(queryset, *args, **kwargs):
            if queryset.model is Team and first_at_canonical.is_set() and get_ident() != first_ident[0]:
                release_first.set()
            return original_select(queryset, *args, **kwargs)

        with patch.object(QuerySet, 'first', pause_at_canonical), patch.object(QuerySet, 'select_for_update', observe_team_lock):
            with ThreadPoolExecutor(max_workers=2) as executor:
                a = executor.submit(self.post, first, '/projects/new', self.submit_data('First'))
                self.assertTrue(first_at_canonical.wait(10), 'First request never reached canonical lookup')
                b = executor.submit(self.post, second, '/projects/new', self.submit_data('Second'))
                try:
                    responses = (a.result(timeout=20), b.result(timeout=20))
                finally:
                    release_first.set()
        self.assertEqual([response.status_code for response in responses], [201, 200])
        self.assertEqual([response.json()['updated'] for response in responses], [False, True])
        rows = list(Project.objects.filter(event=self.event, team=self.team, duplicate_of__isnull=True))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].title, 'Second')

    def test_two_acceptances_of_one_judge_token_only_one_can_set_password(self):
        invited = get_user_model().objects.create_user(username='invited:race@example.org')
        invited.set_unusable_password()
        invited.save(update_fields=['password'])
        token = 'race-' + uuid4().hex
        judge = Judge.objects.create(
            event=self.event, slug='race-judge', user=invited, invite_token=token,
            invite_expires_at=timezone.now() + timedelta(days=1),
        )
        from django.contrib.auth import password_validation
        real_validate = password_validation.validate_password
        first_validating = ThreadEvent()
        release_first = ThreadEvent()
        first_ident = [None]
        original_select = QuerySet.select_for_update

        def pause_password_check(password, user=None):
            if not first_validating.is_set():
                first_ident[0] = get_ident()
                first_validating.set()
                if not release_first.wait(10):
                    raise AssertionError('Second acceptance never reached the lock')
            return real_validate(password, user)

        def observe_judge_lock(queryset, *args, **kwargs):
            if queryset.model is Judge and first_validating.is_set() and get_ident() != first_ident[0]:
                release_first.set()
            return original_select(queryset, *args, **kwargs)

        path = '/judge/accept/' + token
        with patch.object(password_validation, 'validate_password', pause_password_check), patch.object(QuerySet, 'select_for_update', observe_judge_lock):
            with ThreadPoolExecutor(max_workers=2) as executor:
                a = executor.submit(self.post, Client(), path,
                                    {'password': 'FirstRacePass2026!', 'confirm': 'FirstRacePass2026!'})
                self.assertTrue(first_validating.wait(10), 'First acceptance never locked the token')
                b = executor.submit(self.post, Client(), path,
                                    {'password': 'SecondRacePass2026!', 'confirm': 'SecondRacePass2026!'})
                try:
                    responses = (a.result(timeout=20), b.result(timeout=20))
                finally:
                    release_first.set()
        self.assertEqual([response.status_code for response in responses], [200, 404])
        judge.refresh_from_db()
        invited.refresh_from_db()
        self.assertIsNone(judge.invite_token)
        self.assertTrue(invited.check_password('FirstRacePass2026!'))
        self.assertFalse(invited.check_password('SecondRacePass2026!'))

    def test_concurrent_organizer_invites_for_existing_account_create_one_judge(self):
        """Both requests can read the absent Judge row; the user row already exists."""
        organizer = get_user_model().objects.create_superuser(
            username='race-organizer', email='org@example.org', password='fixture'
        )
        email = 'same-invite@example.org'
        invited = get_user_model().objects.create_user(username='invited:' + email, email=email)
        invited.set_unusable_password()
        invited.save(update_fields=['password'])
        first = self.client_for(organizer)
        second = self.client_for(organizer)
        first_checked = ThreadEvent()
        second_checked = ThreadEvent()
        first_ident = [None]
        real_exists = QuerySet.exists

        def synchronize_absent_judge_checks(queryset):
            exists = real_exists(queryset)
            if queryset.model is Judge and not exists:
                if not first_checked.is_set():
                    first_ident[0] = get_ident()
                    first_checked.set()
                    if not second_checked.wait(10):
                        raise AssertionError('Second invite did not check the absent Judge')
                elif get_ident() != first_ident[0]:
                    second_checked.set()
            return exists

        with patch.object(QuerySet, 'exists', synchronize_absent_judge_checks):
            with ThreadPoolExecutor(max_workers=2) as executor:
                payload = {'email': email, 'tracks': ['main']}
                a = executor.submit(self.post, first, '/organizer/judges/invite', payload)
                self.assertTrue(first_checked.wait(10), 'First invite did not check Judge')
                b = executor.submit(self.post, second, '/organizer/judges/invite', payload)
                responses = (a.result(timeout=20), b.result(timeout=20))
        self.assertEqual(sorted(r.status_code for r in responses), [201, 409])
        self.assertEqual(Judge.objects.filter(event=self.event, user=invited).count(), 1)
