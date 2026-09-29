"""Public participation is event-scoped and never reveals judge ballots."""
import hashlib
import hmac
import secrets
from datetime import timedelta
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from .models import Event, Project, ProjectComment, PublicVote, PublicVoteAudit, PublicActionAttempt
from .ranking import CRITERIA, standings


def event_for_request(request):
    slug = request.GET.get("event") or request.POST.get("event")
    # Public callers may not switch into a non-active event by guessing its slug.
    event = Event.objects.filter(active=True).order_by("id").first()
    if slug and (not event or slug != event.slug):
        return None
    return event

def eligible(event):
    return Project.objects.filter(event=event, duplicate_of__isnull=True, draft=False)


def voting_open(event):
    now = timezone.now()
    return bool(event.voting_opens and event.voting_closes and event.voting_opens <= now < event.voting_closes)


def action_allowed(event, key, action, ip, limit=12):
    """Lock the event at the call site before checking a rolling minute."""
    since=timezone.now()-timedelta(minutes=1)
    # Opportunistic expiry prevents an unbounded attempt log on long-lived events.
    PublicActionAttempt.objects.filter(event=event,created_at__lt=timezone.now()-timedelta(days=2)).delete()
    if PublicActionAttempt.objects.filter(event=event,actor_key=key,action=action,created_at__gte=since).count() >= limit:
        return False
    PublicActionAttempt.objects.create(event=event,actor_key=key,action=action,observed_ip=ip)
    return True


def voter_key(request, event):
    if event.voting_access == "authenticated" and request.user.is_authenticated:
        return "user:" + str(request.user.pk)
    if event.voting_access in ('open','email'):
        from .voter_access import session_voter_key
        return session_voter_key(request,event)
    return None


def ballot(request):
    event = event_for_request(request)
    if not event:
        return JsonResponse({"error":"No event"}, status=404)
    if not voting_open(event):
        return JsonResponse({"error":"Voting is closed"}, status=403)
    key = voter_key(request, event)
    if not key:
        return JsonResponse({"error":"Verified voter identity required"}, status=403)
    # A stable per-voter pseudorandom order avoids position bias without rerolling on refresh.
    projects = list(eligible(event).select_related("team", "track"))
    projects.sort(key=lambda p: hmac.new(settings.SECRET_KEY.encode(),
        (str(event.pk)+":"+key+":"+str(p.pk)).encode(), hashlib.sha256).digest())
    return render(request, "ballot.html", {"event":event, "projects":projects})


def vote(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    event = event_for_request(request)
    if not event:
        return JsonResponse({"error":"No event"}, status=404)
    key = voter_key(request, event)
    if not key:
        return JsonResponse({"error":"Verified voter identity required"}, status=403)
    if not voting_open(event):
        return JsonResponse({"error":"Voting is closed"}, status=403)
    project = get_object_or_404(eligible(event), slug=request.POST.get("project", ""))
    try:
        with transaction.atomic():
            # Lock the event to serialize the first vote even if no voter row exists yet.
            event = Event.objects.select_for_update().get(pk=event.pk)
            if not voting_open(event):
                return JsonResponse({"error":"Voting is closed"}, status=403)
            if not action_allowed(event,key,"vote",request.META.get("REMOTE_ADDR"),limit=8):
                return JsonResponse({"error":"Too many attempts"}, status=429)
            if PublicVote.objects.filter(event=event, voter_key=key).exists():
                return JsonResponse({"error":"Vote already cast"}, status=409)
            receipt=secrets.token_hex(16)
            PublicVote.objects.create(event=event,project=project,voter_key=key,receipt=receipt)
            PublicVoteAudit.objects.create(event=event,voter_key=key,project=project,action="cast",
                observed_ip=request.META.get("REMOTE_ADDR"))
    except IntegrityError:
        return JsonResponse({"error":"Vote already cast"}, status=409)
    return JsonResponse({"receipt":receipt}, status=201)


def project_detail(request, slug):
    event = event_for_request(request)
    if not event:
        return JsonResponse({"error":"No event"}, status=404)
    project=get_object_or_404(eligible(event),slug=slug)
    if request.method == "POST":
        if not request.user.is_authenticated:
            return JsonResponse({"error":"Sign in required"}, status=401)
        if not voting_open(event):
            return JsonResponse({"error":"Comments are closed"}, status=403)
        body=request.POST.get("body", "").strip()
        if not body or len(body)>2000:
            return JsonResponse({"error":"Comment must be 1-2000 characters"}, status=400)
        with transaction.atomic():
            event=Event.objects.select_for_update().get(pk=event.pk)
            if not voting_open(event):
                return JsonResponse({"error":"Comments are closed"}, status=403)
            if not action_allowed(event,"user:"+str(request.user.pk),"comment",request.META.get("REMOTE_ADDR"),limit=5):
                return JsonResponse({"error":"Too many comments"}, status=429)
            ProjectComment.objects.create(event=event,project=project,author=request.user,body=body)
        return JsonResponse({"commented":True}, status=201)
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET","POST"])
    comments=ProjectComment.objects.filter(event=event,project=project,hidden=False).select_related("author").order_by("created_at","pk")
    return render(request,"project_detail.html",{"event":event,"project":project,"comments":comments})


def public_results(request):
    event=event_for_request(request)
    if not event:
        return JsonResponse({"error":"No event"}, status=404)
    if not (event.published and event.voting_closes and timezone.now() >= event.voting_closes):
        return JsonResponse({"error":"Results are not public"}, status=404)
    # Only aggregate project rankings, never raw individual judge ballots.
    rows = standings(event)
    eligible_count = len(rows)
    scored_count = sum(row['rank'] is not None for row in rows)
    return render(request,"results_public.html",{"event":event,"standings":rows,
        "eligible_count":eligible_count,"scored_count":scored_count,
        "unscored_count":eligible_count-scored_count,
        "rubric_weights": [
            ("Functionality", (event.rubric or CRITERIA)["functionality"] * 100),
            ("Quality", (event.rubric or CRITERIA)["quality"] * 100),
            ("Innovation", (event.rubric or CRITERIA)["innovation"] * 100),
        ]})


def receipt_lookup(request, token):
    # A secret receipt proves that a ballot was accepted, without exposing voter identity.
    event=event_for_request(request)
    if not event:
        return JsonResponse({"error":"No active event"},status=404)
    if not (event.published and event.voting_closes and timezone.now() >= event.voting_closes):
        return JsonResponse({"error":"Not available before results publish"},status=404)
    row=get_object_or_404(PublicVote,event=event,receipt=token)
    return JsonResponse({"project":row.project.slug,"event":event.slug})


def vote_audit(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponseForbidden()
    slug=request.GET.get("event")
    event=get_object_or_404(Event,slug=slug) if slug else event_for_request(request)
    if not event:
        return JsonResponse({"error":"No event"}, status=404)
    rows=PublicVoteAudit.objects.filter(event=event).select_related("project").order_by("-created_at","-pk")[:500]
    return JsonResponse({"entries":[{"project":x.project.slug,"voter_key":x.voter_key,"action":x.action,"at":x.created_at.isoformat()} for x in rows]})


def moderate_comment(request, pk):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return HttpResponseForbidden()
    if request.method != "POST": return HttpResponseNotAllowed(["POST"])
    event=event_for_request(request)
    if not event: return JsonResponse({"error":"No event"}, status=404)
    comment=get_object_or_404(ProjectComment,event=event,pk=pk)
    comment.hidden=True
    comment.save(update_fields=["hidden"])
    return JsonResponse({"hidden":True})
