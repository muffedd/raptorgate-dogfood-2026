"""Public-only fixture data: no personal details, valid logins, session tokens, or comments."""
import json
from datetime import datetime
from pathlib import Path
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, Team, Track

class Command(BaseCommand):
    help = 'Seed sanitized public preview data without login-capable accounts.'
    def add_arguments(self, parser):
        parser.add_argument('--if-empty', action='store_true')
    @transaction.atomic
    def handle(self, *args, **options):
        if not options['if_empty']:
            raise CommandError('Preview seed is intentionally if-empty only')
        if Event.objects.filter(slug='evt_01', published=True).exists():
            self.stdout.write('Published preview data already present; skipped.')
            return
        existing = list(Event.objects.all())
        User = get_user_model()
        if (len(existing) > 1 or (existing and (existing[0].slug != 'sample-preview' or
                Project.objects.filter(event=existing[0]).count() != 1 or Score.objects.exists())) or
                User.objects.exists() or Session.objects.exists()):
            raise CommandError('Refusing to replace a database with unexpected data')
        if existing:
            # Project protects its track/team, so remove the lone seed row first.
            Project.objects.filter(event=existing[0]).delete()
            existing[0].delete()
        data=json.loads((Path(__file__).resolve().parents[2]/'data'/'preview_seed.json').read_text())
        if len(data['projects']) != 41 or len(data['scores']) != 126:
            raise CommandError('Unexpected preview snapshot counts')
        close=datetime.fromisoformat(data['event']['submissions_close'].replace('Z','+00:00'))
        event=Event.objects.create(slug='evt_01', title=data['event']['name'],
            submissions_close=close, voting_opens=close, voting_closes=close,
            results_publish_at=timezone.now(), published=True, active=True)
        tracks={r['slug']:Track.objects.create(event=event,**r) for r in data['tracks']}
        teams={r['slug']:Team.objects.create(event=event,**r) for r in data['teams']}
        projects={}
        seen={}
        for r in data['projects']:
            p=Project.objects.create(event=event, slug=r['slug'],team=teams[r['team']],
                track=tracks[r['track']],title=r['title'],summary=r['summary'],
                submitted_at=datetime.fromisoformat(r['submitted_at'].replace('Z','+00:00')),
                duplicate_of=seen.get(r['team']))
            seen.setdefault(r['team'],p)
            projects[r['slug']]=p
        judges={}
        for slug in data['judges']:
            user=User(username='preview-'+slug)
            user.set_unusable_password()
            user.save()
            judges[slug]=Judge.objects.create(event=event,slug=slug,user=user)
        for r in data['scores']:
            Score.objects.create(judge=judges[r['judge']],project=projects[r['project']],criteria=r['criteria'])
        self.stdout.write(f'Published public preview: {len(projects)} project rows, {len(data["scores"])} scores; no usable accounts or sessions.')
