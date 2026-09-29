"""Seed a separate, disposable database from the already-sanitized fictional snapshot."""
from datetime import timedelta
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from eventhub.models import Event

class Command(BaseCommand):
    help = 'Seed isolated interactive demo once, never fixture credentials.'
    @transaction.atomic
    def handle(self, *args, **kwargs):
        if Event.objects.filter(slug='interactive-demo').exists():
            self.stdout.write('Interactive demo already present; left data untouched.')
            return
        if Event.objects.exists():
            raise CommandError('Refusing to seed a nonempty database')
        call_command('seed_preview', '--if-empty')
        event = Event.objects.get(slug='evt_01')
        now = timezone.now()
        event.slug = 'interactive-demo'
        event.title = 'RaptorGate interactive demo'
        event.submissions_close = now+timedelta(days=14)
        event.voting_opens = now-timedelta(hours=1)
        event.voting_closes = now+timedelta(days=14)
        event.results_publish_at = None
        event.published = False
        event.voting_access = 'authenticated'
        event.save(update_fields=['slug','title','submissions_close','voting_opens','voting_closes','results_publish_at','published','voting_access'])
        self.stdout.write('Disposable interactive demo seeded with fictional projects and unusable fixture accounts.')
