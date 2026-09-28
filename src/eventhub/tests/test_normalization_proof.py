"""Reproducibility, eligibility and no-write checks for ranking evidence."""
import csv
from io import StringIO
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, Team, Track


class NormalizationProofTests(TestCase):
    def setUp(self):
        event = Event.objects.create(slug='proof', title='Proof',
                                     submissions_close=timezone.now()-timedelta(days=1))
        track = Track.objects.create(event=event, slug='t', name='Track')
        team = Team.objects.create(event=event, slug='tm', name='Team')
        self.event = event
        self.projects = [Project.objects.create(event=event, team=team, track=track,
                            slug=slug, title=slug) for slug in ('alpha','beta','empty')]
        self.hidden = Project.objects.create(event=event, team=team, track=track,
                            slug='draft', title='Draft', draft=True)
        u = get_user_model()
        self.judges = [Judge.objects.create(event=event, slug=slug,
                       user=u.objects.create_user(username=slug)) for slug in ('harsh','lenient')]
        for j, pair in zip(self.judges, ((1,2),(4,5))):
            for project, value in zip(self.projects, pair):
                Score.objects.create(judge=j, project=project,
                    criteria={key:value for key in ('functionality','quality','innovation')})
        Score.objects.create(judge=self.judges[0], project=self.hidden,
                             criteria={'functionality':5,'quality':5,'innovation':5})

    def test_proof_shows_rank_and_stats_without_mutation(self):
        before = Score.objects.count()
        output=StringIO()
        call_command('normalization_proof', event='proof', stdout=output)
        lines=output.getvalue().splitlines()
        judges_at=lines.index('judge,valid_reviews,raw_mean,raw_population_stddev')
        rows=list(csv.DictReader(StringIO('\n'.join(lines[:judges_at]))))
        by_slug={r['project']:r for r in rows}
        self.assertEqual(set(by_slug), {'alpha','beta','empty'})
        self.assertEqual(by_slug['alpha']['raw_mean'], '2.5')
        self.assertEqual(by_slug['alpha']['normalized_mean'], '2.0')
        self.assertEqual(by_slug['beta']['raw_mean'], '3.5')
        self.assertEqual(by_slug['beta']['normalized_mean'], '4.0')
        self.assertEqual(by_slug['empty']['raw_position'], '')
        judges=list(csv.DictReader(StringIO('\n'.join(lines[judges_at:]))))
        self.assertEqual({r['judge'] for r in judges}, {'harsh','lenient'})
        self.assertEqual({r['raw_population_stddev'] for r in judges}, {'0.5'})
        self.assertEqual(Score.objects.count(), before)

    def test_unknown_event_rejected(self):
        with self.assertRaises(CommandError):
            call_command('normalization_proof', event='missing', stdout=StringIO())
