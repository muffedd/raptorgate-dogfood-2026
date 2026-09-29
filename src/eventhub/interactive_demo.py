"""Disposable, isolated browser journeys. Never grants organizer or staff rights."""
import secrets
from django.contrib.auth import get_user_model, login
from django.db import transaction
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import render
from django.contrib.auth.forms import AuthenticationForm
from .models import Assignment, Event, Judge, Project
from .public_views import action_allowed


def landing(request):
    if request.method not in ('GET', 'HEAD'):
        return HttpResponseNotAllowed(['GET', 'HEAD'])
    ready=bool(request.session.get('demo_participant') and request.session.get('demo_judge'))
    if not ready:
        return render(request, 'login.html', {'demo_entry':True, 'form':AuthenticationForm(request),
            'event':Event.objects.filter(active=True).first()})
    return render(request, 'interactive_demo.html', {
        'event': Event.objects.filter(active=True).first(),
        'demo_ready': ready, 'demo_role': request.session.get('demo_role'),
    })


def enter(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    participant = request.session.get('demo_participant')
    judge_id = request.session.get('demo_judge')
    User = get_user_model()
    if participant and judge_id and User.objects.filter(pk=participant, is_superuser=False, is_staff=False, username__startswith='demo-participant-').exists() and User.objects.filter(pk=judge_id, is_superuser=False, is_staff=False, username__startswith='demo-judge-').exists():
        login(request, User.objects.get(pk=participant))
        request.session['demo_participant'] = participant
        request.session['demo_judge'] = judge_id
        request.session['demo_role'] = 'participant'
        return HttpResponseRedirect('/demo')
    event = Event.objects.filter(active=True, slug='interactive-demo').first()
    if event is None:
        return HttpResponseRedirect('/demo')
    with transaction.atomic():
        Event.objects.select_for_update().get(pk=event.pk)
        # Bounded creation on the real remote address; do not trust client-supplied forwarded headers.
        if User.objects.filter(username__startswith='demo-').count() >= 500:
            return render(request, 'interactive_demo.html', {'event':event,'demo_error':'The demo is at capacity. Please try the read-only preview.'}, status=429)
        if not action_allowed(event, 'ip:'+str(request.META.get('REMOTE_ADDR')), 'demo-enter', request.META.get('REMOTE_ADDR'), limit=6):
            return render(request, 'interactive_demo.html', {'event':event,'demo_error':'Too many new demo sessions. Please wait a minute.'}, status=429)
        suffix = secrets.token_hex(9)
        participant = User.objects.create(username='demo-participant-'+suffix)
        judge_user = User.objects.create(username='demo-judge-'+suffix)
        participant.set_unusable_password(); participant.save(update_fields=['password'])
        judge_user.set_unusable_password(); judge_user.save(update_fields=['password'])
        judge = Judge.objects.create(event=event,slug='demo-'+suffix,user=judge_user)
        project = Project.objects.filter(event=event,draft=False,duplicate_of__isnull=True).select_related('track').order_by('pk').first()
        if project:
            judge.tracks.add(project.track)
            Assignment.objects.create(judge=judge,project=project)
    login(request, participant)
    request.session['demo_participant'] = participant.pk
    request.session['demo_judge'] = judge_user.pk
    request.session['demo_role'] = 'participant'
    return HttpResponseRedirect('/demo')


def switch(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    role = request.POST.get('role')
    if role not in ('participant','judge'):
        return HttpResponseNotAllowed(['POST'])
    User = get_user_model()
    user_id = request.session.get('demo_'+role)
    if not user_id:
        return HttpResponseRedirect('/demo')
    user = User.objects.filter(pk=user_id, is_superuser=False, is_staff=False, username__startswith='demo-'+role+'-').first()
    if not user:
        return HttpResponseRedirect('/demo')
    participant_id = request.session['demo_participant']
    judge_id = request.session['demo_judge']
    login(request, user)
    request.session['demo_participant'] = participant_id
    request.session['demo_judge'] = judge_id
    request.session['demo_role'] = role
    return HttpResponseRedirect('/demo')
