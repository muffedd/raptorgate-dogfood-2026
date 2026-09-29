"""Bounded organizer import/export of public project metadata for the active event."""
import csv
import json
from io import StringIO
from django.db import transaction, IntegrityError
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from .models import Event, Project, Team, Track, GALLERY_IMAGE_LIMIT, TAG_LIMIT, TAG_MAX_LEN
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

FIELDS = ('project_slug', 'title', 'summary', 'repo_url', 'team_slug', 'track_slug')
EXTRA_FIELDS = ('thumbnail_url', 'demo_video_url', 'live_url', 'gallery_images_json', 'tags_json', 'custom_answers_json')
EXPORT_FIELDS = FIELDS + EXTRA_FIELDS
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
    writer.writerow(EXPORT_FIELDS)
    for row in projects:
        values=(row.slug,row.title,row.summary,row.repo_url,row.team.slug,row.track.slug,
                row.thumbnail_url,row.demo_video_url,row.live_url,
                json.dumps(row.gallery_images,ensure_ascii=False),
                json.dumps(row.tags,ensure_ascii=False),
                json.dumps(row.custom_answers,ensure_ascii=False))
        writer.writerow([safe_cell(v) for v in values])
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
        if reader.fieldnames not in (list(FIELDS),list(EXPORT_FIELDS)):
            return JsonResponse({'error': 'Expected exact project CSV columns'}, status=400)
        enriched=reader.fieldnames == list(EXPORT_FIELDS)
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        return JsonResponse({'error': 'Invalid UTF-8 CSV'}, status=400)
    if not rows or len(rows) > MAX_ROWS or any(None in row or any(v is None for v in row.values()) for row in rows):
        return JsonResponse({'error': 'CSV must have 1-500 complete rows'}, status=400)
    from django.core.validators import validate_slug
    cleaned = []
    seen = set()
    for row in rows:
        slug, title, summary, repo, team_slug, track_slug = (row[field].strip() for field in FIELDS)
        try:
            validate_slug(slug); validate_slug(team_slug); validate_slug(track_slug)
            if repo: URLValidator(schemes=['https', 'http'])(repo)
            if repo.startswith(('+','-','=','@')): raise ValidationError('Invalid formula-like URL')
        except ValidationError:
            return JsonResponse({'error': 'Invalid slug or URL'}, status=400)
        if not slug or len(slug) > 50 or slug in seen or not title or len(title) > 180 or len(summary) > 10000 or len(repo) > 200:
            return JsonResponse({'error': 'Invalid or duplicate project row'}, status=400)
        seen.add(slug)
        extra={'thumbnail_url':'','demo_video_url':'','live_url':'',
               'gallery_images':[],'tags':[],'custom_answers':{}}
        if enriched:
            try:
                for field in ('thumbnail_url','demo_video_url','live_url'):
                    url=row[field].strip()
                    if len(url)>200: raise ValueError('Reference URL too long')
                    if url: URLValidator(schemes=['http','https'])(url)
                    if url.startswith(('+','-','=','@')): raise ValueError('Formula-like URL')
                    extra[field]=url
                images=json.loads(row['gallery_images_json'])
                tags=json.loads(row['tags_json'])
                answers=json.loads(row['custom_answers_json'])
                if not isinstance(images,list) or len(images)>GALLERY_IMAGE_LIMIT:
                    raise ValueError('Invalid gallery')
                for image in images:
                    if not isinstance(image,str) or len(image)>200:
                        raise ValueError('Invalid gallery URL')
                    URLValidator(schemes=['http','https'])(image)
                    if image.startswith(('+','-','=','@')): raise ValueError('Formula-like image URL')
                if not isinstance(tags,list) or len(tags)>TAG_LIMIT or any(
                        not isinstance(tag,str) or not tag.strip() or len(tag)>TAG_MAX_LEN for tag in tags):
                    raise ValueError('Invalid tags')
                if len({tag.casefold() for tag in tags}) != len(tags):
                    raise ValueError('Duplicate tags')
                if not isinstance(answers,dict) or any(
                        not isinstance(k,str) or not isinstance(v,str) or len(v)>500
                        for k,v in answers.items()):
                    raise ValueError('Invalid answers')
                extra.update(gallery_images=images,tags=tags,custom_answers=answers)
            except (ValueError,TypeError,ValidationError):
                return JsonResponse({'error':'Invalid enrichment fields'},status=400)
        cleaned.append((slug, title, summary, repo, team_slug, track_slug, extra))
    try:
        with transaction.atomic():
            event = Event.objects.select_for_update().filter(active=True).first()
            if event is None:
                return JsonResponse({'error': 'No active event'}, status=404)
            if event.published or timezone.now() >= event.submissions_close:
                return JsonResponse({'error': 'Import is closed'}, status=409)
            if enriched:
                definitions={q['key']:q for q in event.custom_questions}
                for *_,extra in cleaned:
                    answers=extra['custom_answers']
                    if any(k not in definitions for k in answers) or any(
                            q['required'] and not answers.get(q['key'], '').strip()
                            for q in definitions.values()):
                        return JsonResponse({'error':'Answers do not match active event questions'},status=400)
            teams = {x.slug:x for x in Team.objects.filter(event=event, slug__in={r[4] for r in cleaned})}
            tracks = {x.slug:x for x in Track.objects.filter(event=event, slug__in={r[5] for r in cleaned})}
            if any(row[4] not in teams or row[5] not in tracks for row in cleaned):
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
                        team=teams[team], track=tracks[track], submitted_at=timezone.now(),**extra)
                for slug, title, summary, repo, team, track, extra in cleaned
            ])
    except IntegrityError:
        return JsonResponse({'error': 'Project slug or team already exists'}, status=409)
    return JsonResponse({'created': len(cleaned)}, status=201)
