"""Portable Ed25519-signed judge participation certificates.

A certificate asserts a frozen participation count, not judging quality or
individual scores. The private key is supplied at issuance and never stored.
"""
import base64
import binascii
import json
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from django.db import transaction
from django.http import HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from .models import Event, Judge, JudgeCertificate, Score


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def unb64(data):
    return base64.urlsafe_b64decode(data + '=' * (-len(data) % 4))


def signing_key():
    key = os.environ.get('CERTIFICATE_PRIVATE_KEY_PEM', '').replace('\\n', '\n')
    if not key:
        return None
    try:
        value = serialization.load_pem_private_key(key.encode(), password=None)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, Ed25519PrivateKey) else None


def issue(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'error': 'Organizer role required'}, status=403)
    key = signing_key()
    if key is None:
        return JsonResponse({'error': 'Ed25519 signing key not configured'}, status=503)
    with transaction.atomic():
        event = Event.objects.select_for_update().filter(active=True).first()
        if event is None:
            return JsonResponse({'error': 'No active event'}, status=404)
        if not event.published or event.voting_closes is None or timezone.now() < event.voting_closes:
            return JsonResponse({'error': 'Certificates unavailable before public results'}, status=409)
        judge = Judge.objects.filter(event=event, slug=request.POST.get('judge', '')).first()
        if judge is None:
            return JsonResponse({'error': 'Judge not found'}, status=404)
        existing = JudgeCertificate.objects.filter(event=event, judge=judge).first()
        if existing is not None:
            return JsonResponse({'certificate_id': existing.pk, 'already_issued': True})
        count = Score.objects.filter(judge=judge, project__event=event, project__draft=False,
                                     project__duplicate_of__isnull=True).count()
        if count == 0:
            return JsonResponse({'error': 'No eligible reviews'}, status=409)
        payload = {'version': 1, 'kind': 'judge-participation', 'event': event.slug,
                   'judge': judge.slug, 'review_count': count, 'issued_at': timezone.now().isoformat()}
        public = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        row = JudgeCertificate.objects.create(event=event, judge=judge, payload=payload,
                                              public_key=b64(public), signature=b64(key.sign(canonical(payload))))
    return JsonResponse({'certificate_id': row.pk, 'download_path': f'/certificates/{row.pk}.json'}, status=201)


def download(request, pk):
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    row = JudgeCertificate.objects.select_related('event').filter(pk=pk).first()
    if row is None or not row.event.published or row.event.voting_closes is None or timezone.now() < row.event.voting_closes:
        return JsonResponse({'error': 'Certificate not public'}, status=404)
    document = {'payload': row.payload, 'public_key': row.public_key, 'signature': row.signature, 'algorithm': 'Ed25519'}
    try:
        Ed25519PublicKey.from_public_bytes(unb64(row.public_key)).verify(unb64(row.signature), canonical(row.payload))
    except (ValueError, binascii.Error, InvalidSignature):
        # Deliberately fail closed if the stored row was tampered with.
        return JsonResponse({'error': 'Certificate failed signature validation'}, status=409)
    response = JsonResponse(document)
    response['Content-Disposition'] = f'attachment; filename="judge-participation-{row.pk}.json"'
    response['Cache-Control'] = 'no-store'
    return response
