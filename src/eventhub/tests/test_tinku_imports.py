"""Regression checks at the bundled JSON fixture -> Django model boundary."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.test import TestCase
from eventhub.management.commands import seed_event
from eventhub.models import Event, Project, Score, Team, Track


FIXTURE_PATH = Path(seed_event.__file__).resolve().parents[4] / "fixtures.json"


def import_payload(payload):
    # The management command has a fixed fixture location; replace only its read,
    # leaving parsing and all database operations on the real code path.
    with patch.object(seed_event.Path, "read_text", return_value=json.dumps(payload)):
        call_command("seed_event", stdout=StringIO())


class FixtureImportTests(TestCase):
    """Import boundary cases run under both Django and pytest discovery."""

    def test_official_fixture_import_is_idempotent_and_keeps_score_rows(self):
        payload = json.loads(FIXTURE_PATH.read_text())
        import_payload(payload)
        project_id = Project.objects.get(slug=payload["projects"][0]["id"]).pk
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Track.objects.count(), len(payload["tracks"]))
        self.assertEqual(Team.objects.count(), len(payload["teams"]))
        self.assertEqual(Project.objects.count(), len(payload["projects"]))
        expected_scores = len({(r["judge"], r["project"]) for r in payload["scores"]})
        self.assertEqual(Score.objects.count(), expected_scores)

        import_payload(payload)
        self.assertEqual(Project.objects.get(slug=payload["projects"][0]["id"]).pk, project_id)
        self.assertEqual(Project.objects.count(), len(payload["projects"]))
        self.assertEqual(Score.objects.count(), expected_scores)

    def test_unknown_project_in_late_score_rolls_back_every_imported_row(self):
        payload = json.loads(FIXTURE_PATH.read_text())
        payload["scores"][-1]["project"] = "not-in-this-fixture"
        with self.assertRaisesRegex(KeyError, "not-in-this-fixture"):
            import_payload(payload)
        self.assertFalse(Event.objects.exists())
        self.assertFalse(Track.objects.exists())
        self.assertFalse(Team.objects.exists())
        self.assertFalse(Project.objects.exists())
        self.assertFalse(Score.objects.exists())

    def test_boolean_criterion_in_fixture_must_not_be_imported_as_a_numeric_score(self):
        payload = json.loads(FIXTURE_PATH.read_text())
        payload["scores"][0]["criteria"]["quality"] = True  # bool is an int subclass in Python
        with self.assertRaises((CommandError, ValueError, ValidationError)):
            import_payload(payload)
        self.assertFalse(Event.objects.exists())
        self.assertFalse(Score.objects.exists())

    def test_timezone_less_fixture_deadline_is_rejected_not_interpreted_as_local_time(self):
        payload = json.loads(FIXTURE_PATH.read_text())
        payload["event"]["submissions_close"] = "2026-03-01T18:00:00"
        with self.assertRaises((CommandError, ValueError, ValidationError)):
            import_payload(payload)
        self.assertFalse(Event.objects.exists())
