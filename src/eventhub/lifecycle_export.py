"""Organizer-only, event-scoped lifecycle snapshots as spreadsheet-safe CSV."""
import csv
from io import StringIO

from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse

from .bulk import MAX_EXPORT_ROWS, safe_cell
from .models import Assignment, Event, Project, Score, Team
from .ranking import standings

HEADERS = {
    'teams': ('team_slug', 'team_name', 'participant_username', 'participant_email'),
    'submissions': ('project_slug', 'title', 'summary', 'repo_url', 'team_slug', 'track_slug',
                    'submitted_at', 'draft', 'duplicate_of'),
    'assignments': ('project_slug', 'judge_slug', 'judge_username', 'track_slug', 'scored'),
    'scores': ('project_slug', 'judge_slug', 'functionality', 'quality', 'innovation',
               'comment', 'updated_at'),
    'results': ('rank', 'project_slug', 'title', 'reviews', 'raw', 'normalized',
                'raw_rank', 'rank_movement', 'published'),
}


def _timestamp(value):
    return value.isoformat() if value else ''


def _rows(event, dataset):
    if dataset == 'teams':
        # One row per membership; keep teams without members in the snapshot.
        for team in Team.objects.filter(event=event).prefetch_related('members').order_by('slug', 'pk'):
            members = sorted(team.members.all(), key=lambda user: (user.username, user.pk))
            for user in members or [None]:
                yield (team.slug, team.name, user.username if user else '', user.email if user else '')
    elif dataset == 'submissions':
        for project in Project.objects.filter(event=event).select_related('team', 'track', 'duplicate_of').order_by('slug', 'pk'):
            yield (project.slug, project.title, project.summary, project.repo_url,
                   project.team.slug, project.track.slug, _timestamp(project.submitted_at),
                   project.draft, project.duplicate_of.slug if project.duplicate_of else '')
    elif dataset == 'assignments':
        scored = set(Score.objects.filter(judge__event=event, project__event=event)
                     .values_list('judge_id', 'project_id'))
        for assignment in Assignment.objects.filter(judge__event=event, project__event=event).select_related(
                'judge__user', 'project__track').order_by('project__slug', 'judge__slug', 'pk'):
            yield (assignment.project.slug, assignment.judge.slug, assignment.judge.user.username,
                   assignment.project.track.slug, (assignment.judge_id, assignment.project_id) in scored)
    elif dataset == 'scores':
        for score in Score.objects.filter(judge__event=event, project__event=event).select_related(
                'judge', 'project').order_by('project__slug', 'judge__slug', 'pk'):
            criteria = score.criteria if isinstance(score.criteria, dict) else {}
            yield (score.project.slug, score.judge.slug,
                   *(criteria.get(key, '') for key in ('functionality', 'quality', 'innovation')),
                   score.comment, _timestamp(score.updated_at))
    else:
        for row in standings(event):
            yield (row['rank'], row['project'], row['title'], row['reviews'], row['raw'],
                   row['normalized'], row['raw_rank'], row['rank_movement'], event.published)


def export(request, dataset):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'error': 'Organizer role required'}, status=403)
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    if dataset not in HEADERS:
        return JsonResponse({'error': 'Unknown export'}, status=404)
    # Never silently export a different event when none is selected.
    event = Event.objects.filter(active=True).order_by('pk').first()
    if event is None:
        return JsonResponse({'error': 'No active event'}, status=404)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(HEADERS[dataset])
    for count, row in enumerate(_rows(event, dataset), 1):
        if count > MAX_EXPORT_ROWS:
            return JsonResponse({'error': 'Export exceeds 5000 rows'}, status=413)
        writer.writerow([safe_cell(value if value is not None else '') for value in row])
    response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{event.slug}-{dataset}.csv"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
