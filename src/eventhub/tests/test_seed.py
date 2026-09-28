from django.core.management import call_command
from django.test import TestCase
from io import StringIO
from eventhub.models import Event

class SeedRestartTests(TestCase):
    def test_existing_event_reprints_four_fixture_headers(self):
        from django.utils import timezone
        Event.objects.create(slug='existing',title='Existing',submissions_close=timezone.now())
        out=StringIO()
        call_command('seed_event','--if-empty',stdout=out)
        text=out.getvalue()
        self.assertIn('Existing event kept; seed skipped.',text)
        for role in ('organizer','participant','judge_a','judge_b'):
            self.assertIn(role+': Cookie: sessionid=',text)
        self.assertEqual(Event.objects.count(),1)
