"""Read-only public checks with separate trust levels for three artifact kinds."""
import binascii
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.http import HttpResponseNotAllowed
from django.shortcuts import render
from django.utils import timezone

from .certificates import canonical, unb64
from .models import Event, JudgeCertificate, JudgeParticipationRecord, PublicVote
from .records import _signature, _signing_key


def _released(event):
    return bool(event.published and event.voting_closes and timezone.now() >= event.voting_closes)


def _verdict(request):
    kind = request.POST.get('kind')
    text = request.POST.get('artifact', '').strip()
    if len(text) > 16384:
        return 'red', 'The submitted value exceeds the 16 KiB limit.'
    if kind == 'certificate':
        try:
            doc = json.loads(text)
            if not isinstance(doc, dict) or set(doc) != {'payload', 'public_key', 'signature', 'algorithm'} or doc['algorithm'] != 'Ed25519' or not isinstance(doc['payload'], dict):
                raise ValueError('Wrong certificate shape')
            public = unb64(doc['public_key'])
            signature = unb64(doc['signature'])
            if len(public) != 32 or len(signature) != 64:
                raise ValueError('Wrong key or signature length')
            Ed25519PublicKey.from_public_bytes(public).verify(signature, canonical(doc['payload']))
        except (ValueError, TypeError, OverflowError, binascii.Error, InvalidSignature):
            return 'red', 'Certificate is malformed or its Ed25519 signature does not match.'
        # A valid self-signed document is not an organizer-issued certificate.
        row = JudgeCertificate.objects.filter(payload=doc['payload'], public_key=doc['public_key'], signature=doc['signature']).select_related('event').first()
        if not row or not _released(row.event):
            return 'red', 'The signature is internally valid, but this certificate is not a published issuance on this site.'
        return 'green', 'This published certificate matches the site-issued snapshot and its Ed25519 signature is valid. It does not prove judging quality or certify the organizer independently.'
    if kind == 'receipt':
        if not re.fullmatch(r'[0-9a-f]{32}', text):
            return 'red', 'Enter the 32-character hexadecimal vote receipt.'
        row = PublicVote.objects.filter(receipt=text).select_related('event', 'project').first()
        if not row or not row.event.active or not _released(row.event):
            return 'red', 'No published accepted ballot matches this receipt in the active event.'
        return 'green', f'Receipt matches an accepted vote for project {row.project.slug} in event {row.event.slug}. This does not reveal voter identity or prove ballot fairness.'
    if kind == 'record':
        if not text.isdecimal() or len(text) > 12:
            return 'red', 'Enter the numeric participation record ID.'
        row = JudgeParticipationRecord.objects.filter(pk=int(text)).select_related('event').first()
        if not row or not _released(row.event):
            return 'red', 'No published participation record matches that ID.'
        key = _signing_key()
        if not key:
            return 'unavailable', 'Record verification is unavailable because this site has no record signing key configured.'
        import hmac
        if not hmac.compare_digest(row.signature, _signature(row.payload, key)):
            return 'red', 'The record does not match this site\'s HMAC signing key.'
        return 'green', f'Participation record {row.pk} matches the server-held key for event {row.event.slug}. This is a server check, not portable proof of judging.'
    return 'red', 'Choose certificate JSON, vote receipt, or participation record ID.'


def verify_page(request):
    if request.method not in ('GET', 'POST'):
        return HttpResponseNotAllowed(['GET', 'POST'])
    verdict, explanation = _verdict(request) if request.method == 'POST' else (None, None)
    event = Event.objects.filter(active=True).first()
    return render(request, 'verify.html', {'event': event, 'verdict': verdict,
                   'explanation': explanation, 'kind': request.POST.get('kind', '') if request.method == 'POST' else ''})
