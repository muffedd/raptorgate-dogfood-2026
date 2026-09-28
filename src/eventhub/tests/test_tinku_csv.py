"""Regression tests for spreadsheet-formula (CSV) injection in /api/export.csv.

Bug class: CSV injection - cells beginning with =, +, -, @ (optionally after
leading whitespace such as tab or CR) are evaluated as formulas when an
organizer opens the export in a spreadsheet application. The export must
neutralize every attacker-influenced cell, not just some columns.
"""
import csv
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from eventhub.models import Event, Judge, Project, Score, Team, Track

HEADER = ['project_id', 'project_title', 'team', 'track', 'judge',
          'functionality', 'quality', 'innovation']


class CsvExportInjectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = Event.objects.create(
            slug='csv-evt', title='CSV Event',
            submissions_close=timezone.now() - timedelta(days=1))
        cls.track = Track.objects.create(
            event=cls.event, slug='trk', name='Developer tools')
        cls.team = Team.objects.create(
            event=cls.event, slug='team-a', name='NorthKiln')
        cls.project = Project.objects.create(
            event=cls.event, slug='prj-a', team=cls.team, track=cls.track,
            title='Glass Signal')
        User = get_user_model()
        cls.organizer = User.objects.create_superuser(
            username='csv-org', email='org@example.org', password='x')
        judge_user = User.objects.create_user(username='csv-judge')
        cls.judge = Judge.objects.create(
            event=cls.event, slug='jdg_01', user=judge_user)
        cls.score = Score.objects.create(
            judge=cls.judge, project=cls.project,
            criteria={'functionality': 4, 'quality': 3, 'innovation': 5})

    def export_rows(self):
        self.client.force_login(self.organizer)
        response = self.client.get('/api/export.csv')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'], 'text/csv; charset=utf-8')
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8'))))
        self.assertEqual(rows[0], HEADER)
        return rows[1:]

    def row_for(self, project_slug):
        for row in self.export_rows():
            if row[0] == project_slug:
                return row
        self.fail(f'no CSV row for project {project_slug}')

    def assert_neutral(self, cell, original):
        """A neutralized cell must not let a spreadsheet see a formula:
        it needs a leading apostrophe and must preserve the payload text."""
        self.assertTrue(
            cell.startswith("'"),
            f'cell {cell!r} would still execute as a spreadsheet formula')
        self.assertIn(original, cell)

    def test_formula_team_name_neutralized(self):
        for payload in ('=HYPERLINK("http://evil.example","click")', '+1+2',
                        '-2+3', '@SUM(1,1)'):
            with self.subTest(payload=payload):
                self.team.name = payload
                self.team.save(update_fields=['name'])
                self.assert_neutral(self.row_for('prj-a')[2], payload)

    def test_formula_project_title_neutralized(self):
        for payload in ('=1+1', '+cmd', '-10+5', '@NOW()'):
            with self.subTest(payload=payload):
                self.project.title = payload
                self.project.save(update_fields=['title'])
                self.assert_neutral(self.row_for('prj-a')[1], payload)

    def test_whitespace_prefixed_formula_neutralized(self):
        """Tab, CR and spaces before a formula character are a classic
        bypass; the export must still neutralize the cell."""
        for payload in ('\t=1+1', '\r=1+1', '   =2+2', '\t@SUM(1)'):
            with self.subTest(payload=repr(payload)):
                self.project.title = payload
                self.project.save(update_fields=['title'])
                self.assert_neutral(self.row_for('prj-a')[1], payload)

    def test_benign_values_pass_through_byte_identical(self):
        """Non-formula values must not be mangled: no apostrophe is added
        and mid-string formula characters are left alone."""
        self.team.name = 'Team Alpha'
        self.team.save(update_fields=['name'])
        self.project.title = 'C++ tooling @scale = fun'
        self.project.save(update_fields=['title'])
        row = self.row_for('prj-a')
        self.assertEqual(row[0], 'prj-a')
        self.assertEqual(row[1], 'C++ tooling @scale = fun')
        self.assertEqual(row[2], 'Team Alpha')
        self.assertEqual(row[3], 'Developer tools')
        self.assertEqual(row[4], 'jdg_01')

    def test_numeric_criteria_render_plain(self):
        row = self.row_for('prj-a')
        self.assertEqual(row[5:8], ['4', '3', '5'])

    def test_missing_criteria_keys_render_empty(self):
        self.score.criteria = {'quality': 4}
        self.score.save(update_fields=['criteria'])
        row = self.row_for('prj-a')
        self.assertEqual(row[5], '')
        self.assertEqual(row[6], '4')
        self.assertEqual(row[7], '')

    def test_string_criteria_value_neutralized(self):
        """Score.criteria is an unvalidated JSONField also populated by
        fixture/seed imports; a string value such as a planted formula must
        be neutralized in the export exactly like the text columns are."""
        for payload in ('=1+1', '+HYPERLINK("http://evil.example","x")',
                        '-2-2', '@A1', '\t=3+3'):
            with self.subTest(payload=repr(payload)):
                self.score.criteria = {'functionality': payload,
                                       'quality': 4, 'innovation': 3}
                self.score.save(update_fields=['criteria'])
                self.assert_neutral(self.row_for('prj-a')[5], payload)
