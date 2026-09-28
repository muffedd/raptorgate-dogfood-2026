import json
from datetime import datetime, timedelta
from pathlib import Path
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from eventhub.models import Event, Judge, Project, Score, Team, Track

SESSIONS={
 'organizer':('event-organizer','org_rg_rewrite_fixture_2026'),
 'participant':('event-participant','prt_rg_rewrite_fixture_2026'),
 'judge_a':('judge-jdg_01','ja_rg_rewrite_fixture_2026'),
 'judge_b':('judge-jdg_02','jb_rg_rewrite_fixture_2026'),
}

class Command(BaseCommand):
    help='Load official fixtures and print demo authentication headers.'
    def add_arguments(self,parser):
        parser.add_argument('--if-empty',action='store_true')
    @transaction.atomic
    def handle(self,*args,**opts):
        if opts['if_empty'] and Event.objects.exists():
            self.stdout.write('Existing event kept; seed skipped.')
            for role,(_,token) in SESSIONS.items():
                self.stdout.write(f'{role}: Cookie: sessionid={token}')
            return
        data=json.loads((Path(__file__).resolve().parents[4]/'fixtures.json').read_text())
        e=data['event']
        event,_=Event.objects.update_or_create(slug=e['id'],defaults={'title':e['name'],'submissions_close':datetime.fromisoformat(e['submissions_close'].replace('Z','+00:00'))})
        tracks={}
        for row in data['tracks']:
            tracks[row['id']],_=Track.objects.update_or_create(event=event,slug=row['id'],defaults={'name':row['name']})
        User=get_user_model()
        teams={}
        for row in data['teams']:
            team,_=Team.objects.update_or_create(event=event,slug=row['id'],defaults={'name':row['name']})
            users=[]
            for email in row['members']:
                user,_=User.objects.get_or_create(username='member:'+email.lower(),defaults={'email':email.lower()})
                users.append(user)
            team.members.set(users)
            teams[row['id']]=team
        judges={}
        for row in data['judges']:
            user,_=User.objects.get_or_create(username='judge-'+row['id'],defaults={'email':row['email']})
            judge,_=Judge.objects.update_or_create(event=event,slug=row['id'],defaults={'user':user})
            judge.tracks.set([tracks[t] for t in row['tracks']])
            judges[row['id']]=judge
        projects={}
        for row in data['projects']:
            project,_=Project.objects.update_or_create(event=event,slug=row['id'],defaults={'title':row['title'],'summary':row['summary'],'repo_url':row.get('repo_url',''),'team':teams[row['team']],'track':tracks[row['track']],'submitted_at':datetime.fromisoformat(row['submitted_at'].replace('Z','+00:00'))})
            projects[row['id']]=project
        # The fixture plants one duplicate project on the same team. Keep it for audit,
        # hide the later row from the canonical public gallery.
        seen={}
        for row in data['projects']:
            key=row['team']
            project=projects[row['id']]
            project.duplicate_of=seen.get(key)
            project.save(update_fields=['duplicate_of'])
            seen.setdefault(key,project)
        for row in data['scores']:
            Score.objects.update_or_create(judge=judges[row['judge']],project=projects[row['project']],defaults={'criteria':row['criteria'],'comment':row['comment']})
        for role,(name,token) in SESSIONS.items():
            user,_=User.objects.get_or_create(username=name)
            if role=='organizer':
                user.is_staff=user.is_superuser=True
            user.set_password('OfflineFixtureOnly2026!')
            user.save()
            session=SessionStore()
            payload={'_auth_user_id':str(user.pk),'_auth_user_backend':'django.contrib.auth.backends.ModelBackend','_auth_user_hash':user.get_session_auth_hash()}
            Session.objects.update_or_create(session_key=token,defaults={'session_data':session.encode(payload),'expire_date':timezone.now()+timedelta(days=30)})
            if role.startswith('judge_'):
                judge=judges['jdg_01' if role=='judge_a' else 'jdg_02']
                judge.user=user; judge.save(update_fields=['user'])
            if role=='participant':
                teams[data['teams'][0]['id']].members.add(user)
            self.stdout.write(f'{role}: Cookie: sessionid={token}')
        self.stdout.write(f'Seeded {Project.objects.filter(event=event).count()} projects and {Score.objects.filter(project__event=event).count()} distinct score rows.')
