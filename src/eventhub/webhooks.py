"""Operator-configured results-publication webhook with durable delivery queue.

Callbacks are never sent during the publish request. The endpoint and HMAC
secret come from server environment, not from public or organizer input.
"""
import hashlib
import hmac
import json
import os
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from django.http import HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from .models import Event, WebhookDelivery


def config():
    endpoint = os.environ.get('RESULTS_WEBHOOK_URL', '')
    secret = os.environ.get('RESULTS_WEBHOOK_SECRET', '')
    try:
        url = urlsplit(endpoint)
        valid = (url.scheme == 'https' and url.hostname and url.username is None and
                 url.password is None and url.fragment == '' and url.port in (None, 443) and
                 len(endpoint) <= 500 and len(secret) >= 32)
    except ValueError:
        valid = False
    if not valid:
        return None
    return endpoint, secret.encode()


def queue_publication(event):
    """Call inside publication transaction; unique event/type prevents duplicates."""
    if config() is not None:
        WebhookDelivery.objects.get_or_create(event=event, kind='results.published',
                                               defaults={'payload': {'type': 'results.published', 'event': event.slug}})


def deliveries(request):
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'error': 'Organizer role required'}, status=403)
    event = Event.objects.filter(active=True).first()
    if not event:
        return JsonResponse({'error': 'No active event'}, status=404)
    rows = WebhookDelivery.objects.filter(event=event).order_by('id')
    return JsonResponse({'deliveries': [{'id': row.pk, 'type': row.kind, 'attempts': row.attempts,
                                         'delivered': row.delivered_at is not None,
                                         'last_status': row.last_status} for row in rows]})


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def dispatch_one(row, endpoint, secret):
    body = json.dumps(row.payload, sort_keys=True, separators=(',', ':')).encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    req = Request(endpoint, data=body, headers={
        'Content-Type': 'application/json', 'X-RaptorGate-Delivery': str(row.pk),
        'X-RaptorGate-Signature-256': 'sha256=' + signature,
    }, method='POST')
    try:
        with build_opener(NoRedirect()).open(req, timeout=5) as response:
            status = response.status
    except Exception as exc:
        # Operator-controlled URL, but network is unreliable; bounded status.
        status = ('error:' + type(exc).__name__)[:50]
    row.attempts += 1
    row.last_status = str(status)
    if isinstance(status, int) and 200 <= status < 300:
        row.delivered_at = timezone.now()
    row.save(update_fields=['attempts', 'last_status', 'delivered_at'])
    return row.delivered_at is not None


def dispatch_pending(limit=100):
    settings = config()
    if settings is None:
        return 0, 0
    endpoint, secret = settings
    sent = 0
    attempted = 0
    for row in WebhookDelivery.objects.filter(delivered_at__isnull=True).order_by('id')[:limit]:
        attempted += 1
        sent += int(dispatch_one(row, endpoint, secret))
    return attempted, sent
