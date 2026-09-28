"""Bounded organizer import/export of public project metadata for the active event."""
import csv
from io import StringIO
from django.db import transaction, IntegrityError
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from .models import Event, Project, Team, Track

FIELDS = ('project_slug', 'title', 'summary', 'repo_url', 'team_slug', 'track_slug')
MAX_BYTES = 1024 * 1024
MAX_ROWS = 500
MAX_EXPORT_ROWS = 5000


def safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def projects_csv(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'error': 'Organizer role required'}, status=403)
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    event = Event.objects.filter(active=True).first()
    if event is None:
        return JsonResponse({'error': 'No active event'}, status=404)
    projects = Project.objects.filter(event=event).select_related('team', 'track').order_by('slug')
    if projects.count() > MAX_EXPORT_ROWS:
        return JsonResponse({'error': 'Export exceeds 5000 rows'}, status=413)
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(FIELDS)
    for row in projects:
        writer.writerow([safe_cell(v) for v in (row.slug, row.title, row.summary,
                        row.repo_url, row.team.slug, row.track.slug)])
    response = HttpResponse(out.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="projects.csv"'
    return response


def import_projects_csv(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'error': 'Organizer role required'}, status=403)
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if len(request.body) > MAX_BYTES:
        return JsonResponse({'error': 'CSV exceeds 1 MB'}, status=413)
    try:
        text = request.body.decode('utf-8-sig')
        reader = csv.DictReader(StringIO(text, newline=''), strict=True)
        if reader.fieldnames != list(FIELDS):
            return JsonResponse({'error': 'Expected exact project CSV columns'}, status=400)
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        return JsonResponse({'error': 'Invalid UTF-8 CSV'}, status=400)
    if not rows or len(rows) > MAX_ROWS or any(None in row or any(v is None for v in row.values()) for row in rows):
        return JsonResponse({'error': 'CSV must have 1-500 complete rows'}, status=400)
    from django.core.validators import validate_slug, URLValidator
    from django.core.exceptions import ValidationError
    cleaned = []
    seen = set()
    for row in rows:
        slug, title, summary, repo, team_slug, track_slug = (row[field].strip() for field in FIELDS)
        try:
            validate_slug(slug); validate_slug(team_slug); validate_slug(track_slug)
            if repo: URLValidator(schemes=['https', 'http'])(repo)
        except ValidationError:
            return JsonResponse({'error': 'Invalid slug or URL'}, status=400)
        if not slug or len(slug) > 50 or slug in seen or not title or len(title) > 180 or len(summary) > 10000 or len(repo) > 200:
            return JsonResponse({'error': 'Invalid or duplicate project row'}, status=400)
        seen.add(slug)
        cleaned.append((slug, title, summary, repo, team_slug, track_slug))
    try:
        with transaction.atomic():
        event = Event.objects.select_for_update().filter(active=True).first()
        if event is None:
            return JsonResponse({'error': 'No active event'}, status=404)
        if event.published or timezone.now() >= event.submissions_close:
            return JsonResponse({'error': 'Import is closed'}, status=409)
        teams = {x.slug:x for x in Team.objects.filter(event=event, slug__in={r[4] for r in cleaned})}
        tracks = {x.slug:x for x in Track.objects.filter(event=event, slug__in={r[5] for r in cleaned})}
        if any(team not in teams or track not in tracks for *_, team, track in cleaned):
            return JsonResponse({'error': 'Team or track outside active event'}, status=400)
        if Project.objects.filter(event=event, slug__in=seen).exists():
            return JsonResponse({'error': 'Project slug already exists'}, status=409)
        team_slugs = [r[4] for r in cleaned]
        if len(set(team_slugs)) != len(team_slugs) or Project.objects.filter(
            event=event, team__slug__in=team_slugs, duplicate_of__isnull=True
        ).exists():
            return JsonResponse({'error': 'Each team may have one canonical project'}, status=409)
        Project.objects.bulk_create([
            Project(event=event, slug=slug, title=title, summary=summary, repo_url=repo,
                    team=teams[team], track=tracks[track], submitted_at=timezone.now())
            for slug, title, summary, repo, team, track in cleaned
        ])
    except IntegrityError:
        return JsonResponse({'error': 'Project slug or team already exists'}, status=409)
    return JsonResponse({'created': len(cleaned)}, status=201)
