"""Scoped JSON API: read-only public data and explicit bearer role checks."""
import hashlib
import secrets
from datetime import timedelta
from django.http import HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from .models import APIToken, Assignment, Event, Judge, Project
from .ranking import standings


def _authorized(request):
    header=request.META.get('HTTP_AUTHORIZATION','')
    if not header.startswith('Bearer '):return None
    raw=header[7:]
    if len(raw)!=43 or not raw.isascii():return None
    digest=hashlib.sha256(raw.encode()).hexdigest()
    row=APIToken.objects.select_related('user').filter(token_hash=digest,revoked_at__isnull=True,expires_at__gt=timezone.now(),user__is_active=True).first()
    return row.user if row else None


def _no_store(response):
    response['Cache-Control']='no-store'
    return response


def issue_token(request):
    if request.method!='POST':return HttpResponseNotAllowed(['POST'])
    if not request.user.is_authenticated:return JsonResponse({'error':'Sign in required'},status=401)
    name=request.POST.get('name','').strip()
    if not name or len(name)>80:return JsonResponse({'error':'Name required (max 80)'},status=400)
    raw=secrets.token_urlsafe(32)
    row=APIToken.objects.create(user=request.user,name=name,token_hash=hashlib.sha256(raw.encode()).hexdigest(),expires_at=timezone.now()+timedelta(days=30))
    return _no_store(JsonResponse({'id':row.pk,'token':raw,'expires_at':row.expires_at.isoformat()},status=201))


def revoke_token(request,pk):
    if request.method!='POST':return HttpResponseNotAllowed(['POST'])
    if not request.user.is_authenticated:return JsonResponse({'error':'Sign in required'},status=401)
    changed=APIToken.objects.filter(pk=pk,user=request.user,revoked_at__isnull=True).update(revoked_at=timezone.now())
    return JsonResponse({'revoked':bool(changed)},status=200 if changed else 404)


def active_event(request):
    slug=request.GET.get('event')
    event=Event.objects.filter(active=True).first()
    return event if event and (not slug or slug==event.slug) else None


def projects(request):
    if request.method!='GET':return HttpResponseNotAllowed(['GET'])
    event=active_event(request)
    if not event:return JsonResponse({'error':'No active event'},status=404)
    rows=Project.objects.filter(event=event,draft=False,duplicate_of__isnull=True).select_related('team','track').order_by('slug')[:500]
    return JsonResponse({'event':event.slug,'projects':[{'slug':p.slug,'title':p.title,'summary':p.summary,'repo_url':p.repo_url,'team':p.team.name,'track':p.track.name} for p in rows]})


def results(request):
    if request.method!='GET':return HttpResponseNotAllowed(['GET'])
    event=active_event(request)
    if not event or not (event.published and event.voting_closes and timezone.now()>=event.voting_closes):
        return JsonResponse({'error':'Results are not public'},status=404)
    return JsonResponse({'event':event.slug,'standings':standings(event)})


def assignments(request):
    if request.method!='GET':return HttpResponseNotAllowed(['GET'])
    user=_authorized(request)
    if not user:return JsonResponse({'error':'Bearer token required'},status=401)
    event=active_event(request)
    if not event:return JsonResponse({'error':'No active event'},status=404)
    judge=Judge.objects.filter(event=event,user=user).first()
    if not judge:return JsonResponse({'error':'Judge role required'},status=403)
    rows=Assignment.objects.filter(judge=judge,project__event=event,project__draft=False,project__duplicate_of__isnull=True).select_related('project').order_by('project__slug')
    return JsonResponse({'judge':judge.slug,'assignments':[{'project':a.project.slug,'title':a.project.title} for a in rows]})
