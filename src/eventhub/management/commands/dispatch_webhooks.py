"""Explicit bounded webhook delivery; run from an operator scheduler."""
from django.core.management.base import BaseCommand
from eventhub.webhooks import dispatch_pending

class Command(BaseCommand):
    help = 'Deliver up to 100 pending results.published callbacks (requires RESULTS_WEBHOOK_URL/SECRET)'
    def handle(self, *args, **options):
        attempted, sent = dispatch_pending()
        self.stdout.write(f'webhook attempts={attempted} delivered={sent}')
