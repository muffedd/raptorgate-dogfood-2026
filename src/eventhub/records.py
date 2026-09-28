"""HMAC-verifiable participation snapshots; not a public judge ballot."""
import hashlib
import hmac
import json
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from .models import Event, Judge, JudgeParticipationRecord, Score


def _signature(payload):
    body=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    return hmac.new(settings.SECRET_KEY.encode(),body,hashlib.sha256).hexdigest()


def issue(request):
    if request.method!='POST':return HttpResponseNotAllowed(['POST'])
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'error':'Organizer role required'},status=403)
    with transaction.atomic():
        event=Event.objects.select_for_update().filter(active=True).first()
        if not event:return JsonResponse({'error':'No active event'},status=404)
        if not event.published or not event.voting_closes or timezone.now()<event.voting_closes:
            return JsonResponse({'error':'Records unavailable before public results'},status=409)
        judge=Judge.objects.filter(event=event,slug=request.POST.get('judge','')).first()
        if not judge:return JsonResponse({'error':'Judge not found'},status=404)
        existing=JudgeParticipationRecord.objects.filter(event=event,judge=judge).first()
        if existing:
            return JsonResponse({'record_id':existing.pk,'already_issued':True},status=200)
        count=Score.objects.filter(judge=judge,project__event=event,project__draft=False,project__duplicate_of__isnull=True).count()
        if not count:return JsonResponse({'error':'No eligible reviews'},status=409)
        payload={'version':1,'event':event.slug,'judge':judge.slug,'reviews':count,'issued_at':timezone.now().isoformat()}
        row=JudgeParticipationRecord.objects.create(event=event,judge=judge,review_count=count,payload=payload,signature=_signature(payload))
    return JsonResponse({'record_id':row.pk,'verify_path':f'/records/{row.pk}/verify'},status=201)


def verify(request,pk):
    if request.method!='GET':return HttpResponseNotAllowed(['GET'])
    row=JudgeParticipationRecord.objects.filter(pk=pk).first()
    if not row:return JsonResponse({'error':'Record not found'},status=404)
    event=row.event
    if not event.published or not event.voting_closes or timezone.now()<event.voting_closes:
        return JsonResponse({'error':'Record not published'},status=404)
    valid=hmac.compare_digest(row.signature,_signature(row.payload))
    return JsonResponse({'valid':valid,'record':row.payload,'signature':row.signature,'algorithm':'HMAC-SHA256'},status=200 if valid else 409)
