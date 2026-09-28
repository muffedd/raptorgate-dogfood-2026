"""Shared fixtures for the T3 adversarial lane. New file, helpers only."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from eventhub.models import Event, Project, Team, Track


def make_event(slug="t3", active=True, access="authenticated", open_window=True,
               published=False, closed=False):
    now = timezone.now()
    kwargs = dict(
        slug=slug,
        title=f"Event {slug}",
        active=active,
        submissions_close=now - timedelta(days=1),
        voting_access=access,
        published=published,
    )
    if open_window:
        kwargs["voting_opens"] = now - timedelta(hours=1)
        kwargs["voting_closes"] = now - timedelta(hours=1) if closed else now + timedelta(hours=1)
    return Event.objects.create(**kwargs)


def make_project(event, slug="proj", title="Project", draft=False, duplicate_of=None):
    track, _ = Track.objects.get_or_create(event=event, slug="t", defaults={"name": "Track"})
    team, _ = Team.objects.get_or_create(event=event, slug="tm", defaults={"name": "Team"})
    return Project.objects.create(event=event, team=team, track=track, slug=slug,
                                  title=title, draft=draft, duplicate_of=duplicate_of)


def make_user(username):
    return get_user_model().objects.create_user(username=username, password="pw-t3")


def make_organizer(username="org"):
    return get_user_model().objects.create_superuser(username=username,
                                                     email=f"{username}@example.com",
                                                     password="pw-t3")


def login_client(client, user):
    client.force_login(user)
    return client
