import csv
import json
from io import StringIO
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from .forms import ProjectForm
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from .models import Event, Judge, Project, Score, Team


def active_event():
    return Event.objects.order_by('id').first()


def home(request):
    return gallery(request)


def gallery(request):
    event=active_event()
    rows=Project.objects.filter(event=event,duplicate_of__isnull=True).select_related('track','team') if event else []
    query=request.GET.get('q','').strip()
    track=request.GET.get('track','').strip()
    if query: rows=rows.filter(title__icontains=query)
    if track: rows=rows.filter(track__slug=track)
    return render(request,'gallery.html',{'event':event,'projects':rows,'query':query,'track':track})


@login_required
def submit(request):
    event=active_event()
    if not event: return JsonResponse({'error':'No event'},status=404)
    if request.method!='POST':
        return render(request,'submit.html',{'event':event,'form':ProjectForm(event=event)})
    # Lock the team before checking the clock and canonical row. This serializes
    # concurrent first submissions in PostgreSQL, where no project yet exists to lock.
    with transaction.atomic():
        team=Team.objects.select_for_update().filter(event=event,members=request.user).first()
        if not team:
            return JsonResponse({'error':'Join a team before submitting'},status=403)
        event=Event.objects.select_for_update().get(pk=event.pk)
        if timezone.now()>=event.submissions_close:
            return JsonResponse({'error':'Submissions are closed'},status=403)
        form=ProjectForm(request.POST,event=event)
        if not form.is_valid():
            return JsonResponse({'error':'Invalid project','fields':form.errors.get_json_data()},status=400)
        canonical=Project.objects.filter(event=event,team=team,duplicate_of__isnull=True).first()
        if canonical:
            project=form.save(commit=False)
            canonical.title=project.title; canonical.summary=project.summary
            canonical.repo_url=project.repo_url; canonical.track=project.track
            canonical.submitted_at=timezone.now()
            canonical.save(update_fields=['title','summary','repo_url','track','submitted_at'])
            return JsonResponse({'project':canonical.slug,'updated':True})
        project=form.save(commit=False)
        project.event=event; project.team=team
        project.slug='team-'+str(team.pk)
        project.submitted_at=timezone.now()
        project.save()
        return JsonResponse({'project':project.slug,'updated':False},status=201)


def judge_scores(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error':'Sign in required'},status=401)
    event=active_event()
    if not event: return JsonResponse({'error':'No event'},status=404)
    judge=Judge.objects.filter(event=event,user=request.user).first()
    if not judge: return JsonResponse({'error':'Judge role required'},status=403)
    requested=request.GET.get('judge',judge.slug)
    if requested!=judge.slug:
        return JsonResponse({'error':'Cannot read another judge'},status=403)
    scores=Score.objects.filter(judge=judge,project__event=event).select_related('project').order_by('project__slug')
    return JsonResponse({'judge':judge.slug,'scores':[{'project':s.project.slug,'criteria':s.criteria,'comment':s.comment} for s in scores]})


def export_csv(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error':'Sign in required'},status=401)
    if not request.user.is_superuser:
        return JsonResponse({'error':'Organizer role required'},status=403)
    event=active_event()
    if not event: return JsonResponse({'error':'No event'},status=404)
    stream=StringIO(); writer=csv.writer(stream)
    writer.writerow(['project_id','project_title','team','track','judge','functionality','quality','innovation'])
    for s in Score.objects.filter(project__event=event,judge__event=event).select_related('project__team','project__track','judge').order_by('project__slug','judge__slug'):
        c=s.criteria
        safe=lambda v: "'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v
        writer.writerow([safe(s.project.slug),safe(s.project.title),safe(s.project.team.name),safe(s.project.track.name),safe(s.judge.slug),c.get('functionality',''),c.get('quality',''),c.get('innovation','')])
    return HttpResponse(stream.getvalue(),content_type='text/csv; charset=utf-8')

@login_required
def create_event(request):
    if not request.user.is_staff: return JsonResponse({'error':'Organizer role required'},status=403)
    if request.method!='POST': return render(request,'event_form.html')
    from django.utils.dateparse import parse_datetime
    import re
    name=request.POST.get('name','').strip()
    close=parse_datetime(request.POST.get('submissions_close',''))
    if not name or not close or timezone.is_naive(close):
        return JsonResponse({'error':'Name and UTC deadline required'},status=400)
    slug=request.POST.get('slug','').strip()
    if not re.fullmatch(r'[a-z0-9-]{3,50}',slug):
        return JsonResponse({'error':'Invalid event slug'},status=400)
    event,created=Event.objects.get_or_create(slug=slug,defaults={'title':name,'submissions_close':close})
    if not created: return JsonResponse({'error':'Event slug exists'},status=409)
    return JsonResponse({'event':event.slug},status=201)


@login_required
def create_team(request):
    if request.method!='POST': return render(request,'team_form.html')
    event=active_event()
    if not event: return JsonResponse({'error':'No event'},status=404)
    name=request.POST.get('name','').strip()
    if not name or len(name)>160: return JsonResponse({'error':'Team name required'},status=400)
    import secrets
    from django.utils.text import slugify
    slug=(slugify(name) or 'team')[:50]+'-'+secrets.token_hex(3)
    with transaction.atomic():
        team=Team.objects.create(event=event,slug=slug,name=name)
        team.members.add(request.user)
    return JsonResponse({'team':slug},status=201)


@login_required
def team_invite(request,slug):
    event=active_event()
    team=get_object_or_404(Team,event=event,slug=slug)
    if not team.members.filter(pk=request.user.pk).exists():
        return JsonResponse({'error':'Team member required'},status=403)
    if request.method!='POST': return HttpResponseNotAllowed(['POST'])
    from datetime import timedelta
    import secrets
    with transaction.atomic():
        team=Team.objects.select_for_update().get(pk=team.pk)
        team.invite_token=secrets.token_urlsafe(24)
        team.invite_expires_at=timezone.now()+timedelta(days=7)
        team.save(update_fields=['invite_token','invite_expires_at'])
    return JsonResponse({'invite_path':'/join/'+team.invite_token,'expires_at':team.invite_expires_at.isoformat()})


@login_required
def join_team(request,token):
    if request.method!='POST': return HttpResponseNotAllowed(['POST'])
    with transaction.atomic():
        team=Team.objects.select_for_update().filter(invite_token=token).first()
        if not team or team.invite_expires_at is None or team.invite_expires_at<=timezone.now():
            return JsonResponse({'error':'Invite expired or invalid'},status=404)
        team.members.add(request.user)
    return JsonResponse({'team':team.slug})

@login_required
def judge_assignments(request):
    event=active_event()
    judge=Judge.objects.filter(event=event,user=request.user).first() if event else None
    if not judge: return JsonResponse({'error':'Judge role required'},status=403)
    from .models import Assignment
    rows=Assignment.objects.filter(judge=judge,project__event=event).select_related('project').order_by('project__slug')
    return JsonResponse({'assignments':[{'project':x.project.slug,'title':x.project.title} for x in rows]})


@login_required
def assign_judge(request):
    if not request.user.is_superuser: return JsonResponse({'error':'Organizer role required'},status=403)
    if request.method!='POST': return HttpResponseNotAllowed(['POST'])
    event=active_event()
    judge=get_object_or_404(Judge,event=event,slug=request.POST.get('judge',''))
    project=get_object_or_404(Project,event=event,slug=request.POST.get('project',''),duplicate_of__isnull=True)
    if not judge.tracks.filter(pk=project.track_id).exists():
        return JsonResponse({'error':'Judge is not assigned to this track'},status=400)
    if project.team.members.filter(pk=judge.user_id).exists():
        return JsonResponse({'error':'Judge cannot score own team'},status=400)
    from .models import Assignment
    _,created=Assignment.objects.get_or_create(judge=judge,project=project)
    return JsonResponse({'assigned':created,'project':project.slug})


@login_required
def score_project(request,project_slug):
    if request.method!='POST': return HttpResponseNotAllowed(['POST'])
    event=active_event()
    judge=Judge.objects.filter(event=event,user=request.user).first() if event else None
    if not judge: return JsonResponse({'error':'Judge role required'},status=403)
    project=get_object_or_404(Project,event=event,slug=project_slug,duplicate_of__isnull=True)
    from .models import Assignment, ScoreAudit
    if not Assignment.objects.filter(judge=judge,project=project).exists():
        return JsonResponse({'error':'Assignment required'},status=403)
    if project.team.members.filter(pk=request.user.pk).exists():
        return JsonResponse({'error':'Cannot score own team'},status=403)
    fields=('functionality','quality','innovation')
    try:
        criteria={name:int(request.POST[name]) for name in fields}
    except (ValueError,KeyError,TypeError):
        return JsonResponse({'error':'Every score must be an integer from 1 to 5'},status=400)
    if any(not 1<=value<=5 for value in criteria.values()):
        return JsonResponse({'error':'Every score must be from 1 to 5'},status=400)
    comment=request.POST.get('comment','')[:2000]
    with transaction.atomic():
        score=Score.objects.select_for_update().filter(judge=judge,project=project).first()
        previous=dict(score.criteria) if score else None
        if score:
            score.criteria=criteria;score.comment=comment;score.save(update_fields=['criteria','comment','updated_at'])
        else:
            score=Score.objects.create(judge=judge,project=project,criteria=criteria,comment=comment)
        ScoreAudit.objects.create(score=score,editor=request.user,previous=previous,current=dict(criteria))
    return JsonResponse({'project':project.slug,'criteria':criteria})


@login_required
def results(request):
    if not request.user.is_superuser: return JsonResponse({'error':'Organizer role required'},status=403)
    event=active_event()
    if not event: return JsonResponse({'error':'No event'},status=404)
    from .ranking import standings
    return JsonResponse({'published':event.published,'standings':standings(event)})


@login_required
def publish_results(request):
    if not request.user.is_superuser: return JsonResponse({'error':'Organizer role required'},status=403)
    if request.method!='POST': return HttpResponseNotAllowed(['POST'])
    event=active_event()
    if not event: return JsonResponse({'error':'No event'},status=404)
    with transaction.atomic():
        event=Event.objects.select_for_update().get(pk=event.pk)
        if timezone.now()<event.submissions_close:
            return JsonResponse({'error':'Submissions remain open'},status=409)
        event.published=True;event.results_publish_at=timezone.now();event.save(update_fields=['published','results_publish_at'])
    return JsonResponse({'published':True})

@login_required
def invite_judge(request):
    if not request.user.is_superuser: return JsonResponse({'error':'Organizer role required'},status=403)
    if request.method!='POST': return HttpResponseNotAllowed(['POST'])
    event=active_event()
    email=request.POST.get('email','').strip().lower()
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    try: validate_email(email)
    except ValidationError: return JsonResponse({'error':'Valid email required'},status=400)
    track_ids=request.POST.getlist('tracks')
    if not track_ids or len(set(track_ids))!=len(track_ids):
        return JsonResponse({'error':'Choose one or more distinct tracks'},status=400)
    tracks=list(event.tracks.filter(slug__in=track_ids)) if event else []
    if len(tracks)!=len(track_ids):
        return JsonResponse({'error':'Track outside this event'},status=400)
    import secrets
    from django.contrib.auth import get_user_model
    from django.utils.text import slugify
    from datetime import timedelta
    User=get_user_model()
    with transaction.atomic():
        # The account is not usable until the invitee chooses their own password.
        user,created=User.objects.get_or_create(username='invited:'+email,defaults={'email':email})
        if created: user.set_unusable_password();user.save(update_fields=['password'])
        if Judge.objects.filter(event=event,user=user).exists():
            return JsonResponse({'error':'Judge already invited'},status=409)
        slug='judge-'+secrets.token_hex(5)
        token=secrets.token_urlsafe(24)
        judge=Judge.objects.create(event=event,slug=slug,user=user,invited_at=timezone.now(),invite_token=token,invite_expires_at=timezone.now()+timedelta(days=7))
        judge.tracks.set(tracks)
    return JsonResponse({'accept_path':'/judge/accept/'+token,'judge':judge.slug},status=201)


def accept_judge(request,token):
    if request.method!='POST': return render(request,'judge_accept.html')
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    password=request.POST.get('password','')
    if password!=request.POST.get('confirm',''):
        return JsonResponse({'error':'Passwords do not match'},status=400)
    with transaction.atomic():
        judge=Judge.objects.select_for_update().filter(invite_token=token).select_related('user').first()
        if not judge or not judge.invite_expires_at or judge.invite_expires_at<=timezone.now():
            return JsonResponse({'error':'Invite invalid or expired'},status=404)
        try: validate_password(password,judge.user)
        except ValidationError as exc: return JsonResponse({'error':exc.messages},status=400)
        judge.user.set_password(password);judge.user.save(update_fields=['password'])
        judge.invite_token=None;judge.invite_expires_at=None;judge.save(update_fields=['invite_token','invite_expires_at'])
    return JsonResponse({'accepted':True,'judge':judge.slug})
