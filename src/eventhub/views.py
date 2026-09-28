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
