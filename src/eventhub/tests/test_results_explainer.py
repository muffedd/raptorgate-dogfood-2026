from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, Team, Track
from eventhub.ranking import standings


class ExplainStandingsTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(slug='explain', title='Explain', active=True,
                       published=True, submissions_close=timezone.now()-timedelta(days=1),
                       voting_closes=timezone.now()-timedelta(hours=1))
        track = Track.objects.create(event=self.event, slug='t', name='Track')
        team = Team.objects.create(event=self.event, slug='team', name='Team')
        self.projects = [Project.objects.create(event=self.event, track=track, team=team,
                         slug=f'p{i}', title=f'Project {i}') for i in range(4)]
        self.judges = [Judge.objects.create(event=self.event, slug=f'private-judge-{i}',
                        user=get_user_model().objects.create_user(username=f'secret-judge-user-{i}'))
                       for i in range(2)]
        for judge, project, value in ((self.judges[0], self.projects[0], 5),
                                      (self.judges[0], self.projects[1], 4),
                                      (self.judges[1], self.projects[0], 3),
                                      (self.judges[1], self.projects[1], 1),
                                      (self.judges[1], self.projects[2], 3)):
            Score.objects.create(judge=judge, project=project,
                                 criteria={'functionality': value, 'quality': value, 'innovation': value},
                                 comment='Do not publish this comment')

    def test_aggregate_math_and_rank_movement_are_public_but_individuals_are_not(self):
        rows = {row['project']:row for row in standings(self.event)}
        self.assertEqual(rows['p0']['raw'], 4.0)
        self.assertEqual(rows['p0']['reviews'], 2)
        self.assertEqual(rows['p0']['raw_rank'], 1)
        for row in rows.values():
            self.assertNotIn('judge', row)
            self.assertNotIn('comment', row)
            self.assertEqual(row['rank_movement'],
               None if row['rank'] is None else row['raw_rank']-row['rank'])
        self.assertIsNone(rows['p3']['raw_rank'])
        self.assertIsNone(rows['p3']['rank_movement'])
        html = self.client.get('/results').content.decode()
        self.assertIn('Explain Project 0', html)
        self.assertIn('Raw mean', html)
        self.assertIn('Normalized mean', html)
        self.assertIn('Rank movement', html)
        self.assertIn('Judge count', html)
        for secret in ('private-judge-0', 'private-judge-1', 'secret-judge-user-0',
                       'Do not publish this comment'):
            self.assertNotIn(secret, html)
        self.event.published=False; self.event.save(update_fields=['published'])
        self.assertEqual(self.client.get('/results').status_code, 404)
