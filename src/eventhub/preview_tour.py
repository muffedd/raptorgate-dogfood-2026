"""GET-only previews of owner UI with sanitized fixture context, not live workflows."""
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import render
from .forms import ParticipantSignupForm, ProjectForm
from .models import Event, Judge, Project, Score
from .ranking import standings

PAGES = ('judge', 'ballot', 'organizer', 'standings', 'voter', 'login', 'signup',
         'event', 'questions', 'submit', 'team', 'invite', 'signals')


def page(request, page):
    if not settings.PREVIEW or page not in PAGES:
        raise Http404
    if request.method not in ('GET', 'HEAD'):
        return HttpResponseNotAllowed(['GET', 'HEAD'])
    event = Event.objects.filter(active=True, published=True).first()
    if not event:
        raise Http404
    common = {'event': event, 'tour_page': page, 'tour_pages': PAGES, 'preview_mode': True}
    if page == 'login':
        return render(request, 'login.html', {**common, 'form': AuthenticationForm(request)})
    if page == 'signup':
        return render(request, 'signup.html', {**common, 'form': ParticipantSignupForm()})
    if page == 'voter':
        return render(request, 'voter_access.html', {**common, 'mode': 'email'})
    if page == 'event':
        return render(request, 'event_form.html', common)
    if page == 'questions':
        return render(request, 'event_questions.html', {**common, 'questions_json': '[]'})
    if page == 'team':
        return render(request, 'team_form.html', common)
    if page == 'invite':
        return render(request, 'judge_accept.html', common)
    if page == 'submit':
        return render(request, 'submit.html', {**common, 'form': ProjectForm(event=event),
                                              'project': None, 'can_edit': True})
    if page == 'signals':
        return render(request, 'vote_signals.html', {**common,
            'vote_count': 0, 'cast_count': 0, 'audit_gap': 0,
            'attempt_total': 0, 'vote_attempts': 0, 'rapid_actors': 0,
            'shared_ips': 0, 'duplicate_retries': 0,
            'email_challenges': 0, 'code_guesses': 0})
    projects = list(Project.objects.filter(event=event, duplicate_of__isnull=True, draft=False)
                    .select_related('team', 'track').order_by('title')[:40])
    if page == 'ballot':
        return render(request, 'ballot.html', {**common, 'projects': projects})
    if page == 'standings':
        rows = standings(event)
        return render(request, 'organizer_results.html', {**common,
            'standings': rows, 'project_count': len(rows),
            'score_count': Score.objects.filter(project__event=event).count(), 'assigned_count': 0})
    judges = list(Judge.objects.filter(event=event).select_related('user').order_by('slug')[:40])
    if page == 'organizer':
        progress = [{'slug': j.slug, 'name': j.slug, 'assigned': 0, 'started': 0,
                     'completed': 0, 'not_started': False} for j in judges]
        return render(request, 'organizer_overview.html', {**common,
            'judge_progress': progress, 'projects_count': len(projects),
            'assignments_count': 0,
            'scores_count': Score.objects.filter(project__event=event).count(),
            'export_datasets': ()})
    # A demonstration queue, assembled in memory. This is not an assignment or
    # permission to score. Do not associate a real user or disclose judge scores.
    current = projects[0] if projects else None
    queue = [(type('TourAssignment', (), {'project': p, 'project_id': p.pk})(), False)
             for p in projects[:3]]
    weights = event.rubric or {'functionality': .4, 'quality': .35, 'innovation': .25}
    return render(request, 'judge_console.html', {**common,
        'queue': queue, 'current': current, 'score': None, 'position': 1,
        'total': len(queue), 'completed': 0, 'remaining': len(queue),
        'progress_segments': [False] * len(queue), 'previous': None,
        'following': queue[1][0].project if len(queue) > 1 else None,
        'criteria': [{'key': key, 'label': key.capitalize(),
                      'weight': round(weight * 100), 'selected': None}
                     for key, weight in weights.items()]})
