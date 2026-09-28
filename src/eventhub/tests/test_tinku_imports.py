"""Regression checks at the bundled JSON fixture -> Django model boundary."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from eventhub.management.commands import seed_event
from eventhub.models import Event, Project, Score, Team, Track


FIXTURE_PATH = Path(seed_event.__file__).resolve().parents[4] / "fixtures.json"


def import_payload(payload):
    # The management command has a fixed fixture location; replace only its read,
    # leaving parsing and all database operations on the real code path.
    with patch.object(seed_event.Path, "read_text", return_value=json.dumps(payload)):
        call_command("seed_event", stdout=StringIO())


@pytest.mark.django_db
def test_official_fixture_import_is_idempotent_and_keeps_score_rows():
    payload = json.loads(FIXTURE_PATH.read_text())
    import_payload(payload)
    project_id = Project.objects.get(slug=payload["projects"][0]["id"]).pk
    assert Event.objects.count() == 1
    assert Track.objects.count() == len(payload["tracks"])
    assert Team.objects.count() == len(payload["teams"])
    assert Project.objects.count() == len(payload["projects"])
    assert Score.objects.count() == len({(r["judge"], r["project"]) for r in payload["scores"]})

    import_payload(payload)
    assert Project.objects.get(slug=payload["projects"][0]["id"]).pk == project_id
    assert Project.objects.count() == len(payload["projects"])
    assert Score.objects.count() == len({(r["judge"], r["project"]) for r in payload["scores"]})


@pytest.mark.django_db
def test_unknown_project_in_late_score_rolls_back_every_imported_row():
    payload = json.loads(FIXTURE_PATH.read_text())
    payload["scores"][-1]["project"] = "not-in-this-fixture"
    with pytest.raises(KeyError, match="not-in-this-fixture"):
        import_payload(payload)
    assert not Event.objects.exists()
    assert not Track.objects.exists()
    assert not Team.objects.exists()
    assert not Project.objects.exists()
    assert not Score.objects.exists()


@pytest.mark.django_db
def test_boolean_criterion_in_fixture_must_not_be_imported_as_a_numeric_score():
    payload = json.loads(FIXTURE_PATH.read_text())
    payload["scores"][0]["criteria"]["quality"] = True  # bool is an int subclass in Python
    with pytest.raises((CommandError, ValueError, ValidationError)):
        import_payload(payload)
    assert not Event.objects.exists()
    assert not Score.objects.exists()


@pytest.mark.django_db
def test_timezone_less_fixture_deadline_is_rejected_not_interpreted_as_local_time():
    payload = json.loads(FIXTURE_PATH.read_text())
    payload["event"]["submissions_close"] = "2026-03-01T18:00:00"
    with pytest.raises((CommandError, ValueError, ValidationError)):
        import_payload(payload)
    assert not Event.objects.exists()
