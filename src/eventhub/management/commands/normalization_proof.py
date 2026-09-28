"""Produce a reproducible fixture ranking comparison, without changing event data."""
import csv
from collections import defaultdict
from statistics import mean, pstdev
from django.core.management.base import BaseCommand, CommandError
from eventhub.models import Event, Project, Score
from eventhub.ranking import CRITERIA, standings, weighted_score


class Command(BaseCommand):
    help = 'Print raw and normalized ranking evidence for one event as CSV.'

    def add_arguments(self, parser):
        parser.add_argument('--event', required=True, help='Exact event slug')

    def handle(self, *args, **options):
        event = Event.objects.filter(slug=options['event']).first()
        if event is None:
            raise CommandError('Unknown event')
        normalized = standings(event)
        if not normalized:
            raise CommandError('No eligible projects')
        weights = event.rubric or CRITERIA
        values = defaultdict(list)
        for score in Score.objects.filter(
            project__event=event, judge__event=event,
            project__duplicate_of__isnull=True, project__draft=False,
        ).select_related('judge', 'project'):
            raw = weighted_score(score.criteria, weights)
            if raw is not None:
                values[score.judge.slug].append(raw)
        raw_order = sorted((r for r in normalized if r['raw'] is not None),
                           key=lambda r: (-r['raw'], r['project']))
        raw_rank = {r['project']: idx for idx, r in enumerate(raw_order, 1)}
        writer = csv.writer(self.stdout)
        writer.writerow(['project', 'reviews', 'raw_mean', 'normalized_mean',
                         'raw_position', 'normalized_rank', 'position_change'])
        for idx, row in enumerate(normalized, 1):
            raw_position = raw_rank.get(row['project'])
            # A positive change means the project rose after normalization.
            change = raw_position - idx if raw_position is not None else ''
            writer.writerow([row['project'], row['reviews'],
                             row['raw'] if row['raw'] is not None else '',
                             row['normalized'] if row['normalized'] is not None else '',
                             raw_position or '', row['rank'] or '', change])
        writer.writerow([])
        writer.writerow(['judge', 'valid_reviews', 'raw_mean', 'raw_population_stddev'])
        for judge, scores in sorted(values.items()):
            writer.writerow([judge, len(scores), round(mean(scores), 6),
                             round(pstdev(scores), 6)])
