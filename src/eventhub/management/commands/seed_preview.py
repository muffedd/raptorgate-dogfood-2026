"""Public-safe synthetic preview: no fixture logins, session tokens or judge identities."""
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from eventhub.models import Event, Project, Team, Track

class Command(BaseCommand):
    help = 'Create a public sample event without demo credentials or private scores.'
    def add_arguments(self, parser):
        parser.add_argument('--if-empty', action='store_true')
    @transaction.atomic
    def handle(self, *args, **options):
        if not options['if_empty']:
            raise CommandError('Preview seed is intentionally if-empty only')
        if Event.objects.exists():
            self.stdout.write('Existing event kept; preview seed skipped.')
            return
        now = timezone.now()
        event = Event.objects.create(slug='sample-preview', title='RaptorGate sample event',
            submissions_close=now-timedelta(days=1),
            voting_opens=now-timedelta(days=2), voting_closes=now-timedelta(hours=1),
            results_publish_at=now-timedelta(minutes=50), active=True, published=True)
        track = Track.objects.create(event=event, slug='demo', name='Demo')
        team = Team.objects.create(event=event, slug='sample-team', name='Sample team')
        Project.objects.create(event=event, team=team, track=track,
            slug='sample-project', title='Sample project',
            summary='Fictional example for exploring the interface.', submitted_at=now-timedelta(days=2))
        self.stdout.write('Created public sample event with one fictional unscored project; no users or fixture tokens.')
