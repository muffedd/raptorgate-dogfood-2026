"""Lifecycle CSV exports preserve scope, privacy and spreadsheet safety."""
import csv
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from eventhub.models import Assignment, Event, Judge, Project, Score, Team, Track


class LifecycleExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.org = User.objects.create_superuser('lifecycle-org', 'org@example.test', 'x')
        cls.member = User.objects.create_user('member', 'member@example.test')
        cls.judge_user = User.objects.create_user('judger', 'judge@example.test')
        cls.event = Event.objects.create(slug='live', title='Live', active=True,
                                         submissions_close=timezone.now() + timedelta(days=1))
        cls.other = Event.objects.create(slug='foreign', title='Foreign',
                                         submissions_close=timezone.now() + timedelta(days=1))
        cls.team = Team.objects.create(event=cls.event, slug='team', name='=Team')
        cls.team.members.add(cls.member)
        cls.empty_team = Team.objects.create(event=cls.event, slug='empty', name='Empty')
        track = Track.objects.create(event=cls.event, slug='track', name='Track')
        cls.project = Project.objects.create(event=cls.event, team=cls.team, track=track,
                                              slug='project', title='=SUM(1,2)',
                                              summary='Summary', submitted_at=timezone.now())
        cls.draft = Project.objects.create(event=cls.event, team=cls.team, track=track,
                                            slug='draft', title='Draft', draft=True,
                                            duplicate_of=cls.project)
        cls.judge = Judge.objects.create(event=cls.event, slug='judge', user=cls.judge_user)
        Assignment.objects.create(judge=cls.judge, project=cls.project)
        Score.objects.create(judge=cls.judge, project=cls.project,
                             criteria={'functionality': 5, 'quality': 4, 'innovation': 3}, comment='\t=BAD()')
        foreign_team = Team.objects.create(event=cls.other, slug='secret', name='Foreign secret')
        foreign_track = Track.objects.create(event=cls.other, slug='track', name='Foreign secret')
        foreign_project = Project.objects.create(event=cls.other, team=foreign_team, track=foreign_track,
                                                  slug='secret', title='Foreign secret')
        foreign_judge = Judge.objects.create(event=cls.other, slug='secret',
                                              user=User.objects.create_user('foreignjudge'))
        Assignment.objects.create(judge=foreign_judge, project=foreign_project)
        Score.objects.create(judge=foreign_judge, project=foreign_project,
                             criteria={'functionality': 1, 'quality': 1, 'innovation': 1})

    def rows(self, kind):
        response = self.client.get(f'/organizer/export/{kind}.csv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn(f'live-{kind}.csv', response['Content-Disposition'])
        self.assertNotIn(b'Foreign secret', response.content)
        return list(csv.DictReader(StringIO(response.content.decode())))

    def test_every_stage_with_empty_team_and_unpublished_results(self):
        self.client.force_login(self.org)
        teams = self.rows('teams')
        self.assertEqual(len(teams), 2)
        self.assertEqual(next(row for row in teams if row['team_slug'] == 'empty')['participant_username'], '')
        self.assertEqual(next(row for row in teams if row['team_slug'] == 'team')['participant_email'], 'member@example.test')
        submissions = self.rows('submissions')
        self.assertEqual(len(submissions), 2)
        self.assertEqual(next(row for row in submissions if row['project_slug'] == 'draft')['duplicate_of'], 'project')
        self.assertEqual(next(row for row in submissions if row['project_slug'] == 'draft')['draft'], 'True')
        assignments = self.rows('assignments')
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]['scored'], 'True')
        scores = self.rows('scores')
        self.assertEqual(len(scores), 1)
        self.assertEqual(scores[0]['functionality'], '5')
        self.assertEqual(scores[0]['comment'], "'\t=BAD()")
        results = self.rows('results')
        self.assertEqual(len(results), 1)  # Existing standings exclude draft and duplicates.
        self.assertEqual(results[0]['published'], 'False')
        self.assertEqual(results[0]['rank'], '1')
        self.assertTrue(results[0]['normalized'])
        for rows, key in ((teams, 'team_name'), (submissions, 'title'), (results, 'title')):
            self.assertTrue(any(row[key].startswith("'=") for row in rows))

    def test_roles_methods_and_no_active_event(self):
        for user in (None, self.member, self.judge_user):
            if user:
                self.client.force_login(user)
            for kind in ('teams', 'submissions', 'assignments', 'scores', 'results'):
                self.assertEqual(self.client.get(f'/organizer/export/{kind}.csv').status_code, 403)
        self.client.force_login(self.org)
        self.assertEqual(self.client.post('/organizer/export/scores.csv').status_code, 405)
        self.assertEqual(self.client.get('/organizer/export/invalid.csv').status_code, 404)
        self.event.active = False
        self.event.save(update_fields=['active'])
        self.assertEqual(self.client.get('/organizer/export/results.csv').status_code, 404)

    def test_empty_datasets_still_have_headers(self):
        self.client.force_login(self.org)
        Score.objects.filter(judge=self.judge).delete()
        Assignment.objects.filter(judge=self.judge).delete()
        self.assertEqual(len(self.rows('scores')), 0)
        self.assertEqual(len(self.rows('assignments')), 0)
        results = self.rows('results')
        self.assertEqual(results[0]['rank'], '')
        self.assertEqual(results[0]['normalized'], '')

    def test_overview_links_to_all_exports(self):
        self.client.force_login(self.org)
        response = self.client.get('/organizer/overview')
        for kind in ('teams', 'submissions', 'assignments', 'scores', 'results'):
            self.assertContains(response, f'/organizer/export/{kind}.csv')
