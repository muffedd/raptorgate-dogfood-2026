"""Organizer-only descriptive vote activity signals, not fraud verdicts."""
from datetime import timedelta
from django.db.models import Count
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from .models import Event, PublicActionAttempt, PublicVote, PublicVoteAudit


def signals(request):
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'error': 'Organizer role required'}, status=403)
    event = Event.objects.filter(active=True).order_by('id').first()
    if event is None:
        return JsonResponse({'error': 'No active event'}, status=404)
    # Attempt logs expire after two days; this is a window over retained data,
    # not a claim about all activity for this event.
    since = timezone.now()-timedelta(hours=24)
    attempts = PublicActionAttempt.objects.filter(event=event, created_at__gte=since)
    votes = PublicVote.objects.filter(event=event)
    audit = PublicVoteAudit.objects.filter(event=event, action='cast')
    attempt_total = attempts.count()
    vote_attempts = attempts.filter(action='vote')
    rapid_actors = vote_attempts.values('actor_key').annotate(count=Count('pk')).filter(count__gte=5).count()
    # An observed IP is a network address, not an identity. Do not show IPs.
    shared_ips = vote_attempts.exclude(observed_ip__isnull=True).values('observed_ip').annotate(
        actors=Count('actor_key', distinct=True)).filter(actors__gte=3).count()
    cast_count = audit.count()
    vote_count = votes.count()
    context = {'event': event, 'attempt_total': attempt_total,
               'vote_attempts': vote_attempts.count(), 'rapid_actors': rapid_actors,
               'shared_ips': shared_ips, 'cast_count': cast_count, 'vote_count': vote_count,
               'audit_gap': abs(cast_count-vote_count), 'since': since}
    return render(request, 'vote_signals.html', context)
