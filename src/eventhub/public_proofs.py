"""Portable ballot acceptance proof. Receipt holders can disclose their choice."""
from cryptography.hazmat.primitives import serialization
from django.http import HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from .models import Event, PublicVote
from .certificates import signing_key, canonical, b64


def vote_proof(request, token):
    if request.method!='GET':return HttpResponseNotAllowed(['GET'])
    # No cross-event token lookup: only the active event can disclose a choice.
    event=Event.objects.filter(active=True).order_by('id').first()
    if not event or not event.published or not event.voting_closes or timezone.now()<event.voting_closes:
        return JsonResponse({'error':'Proof unavailable before publication'},status=404)
    row=PublicVote.objects.filter(event=event,receipt=token,project__event=event).select_related('project').first()
    if not row:return JsonResponse({'error':'Receipt not found'},status=404)
    key=signing_key()
    if key is None:return JsonResponse({'error':'Signing key not configured'},status=503)
    payload={'version':1,'kind':'public-ballot-acceptance','event':event.slug,
             'project':row.project.slug,'receipt':row.receipt,'cast_at':row.created_at.isoformat()}
    public=key.public_key().public_bytes(encoding=serialization.Encoding.Raw,
                                          format=serialization.PublicFormat.Raw)
    response=JsonResponse({'payload':payload,'public_key':b64(public),
                           'signature':b64(key.sign(canonical(payload))),'algorithm':'Ed25519'})
    response['Cache-Control']='no-store'
    return response
