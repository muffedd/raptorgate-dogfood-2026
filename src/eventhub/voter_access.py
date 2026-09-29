"""Self-hosted verified-email and one-use open-link ballot admission."""
import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import Event, PublicVote, VoterAccess
from .public_views import action_allowed, event_for_request, voting_open


def _digest(event, secret):
    return hashlib.sha256((str(event.pk)+':'+secret).encode()).hexdigest()


def _active(request, mode):
    event=event_for_request(request)
    return event if event and event.voting_access==mode and voting_open(event) else None


def issue_open_link(request):
    """Superuser creates a one-use token; the link is shown once, not stored."""
    if not request.user.is_authenticated or not request.user.is_superuser:
        return JsonResponse({'error':'Organizer role required'},status=403)
    if request.method!='POST':return HttpResponseNotAllowed(['POST'])
    with transaction.atomic():
        event=_active(request,'open')
        if not event:return JsonResponse({'error':'Open-link voting is not active'},status=403)
        event=Event.objects.select_for_update().get(pk=event.pk)
        if not voting_open(event) or event.voting_access!='open':
            return JsonResponse({'error':'Open-link voting is closed'},status=403)
        secret=secrets.token_urlsafe(32)
        VoterAccess.objects.create(event=event,kind='open',secret_hash=_digest(event,secret),expires_at=event.voting_closes)
    response=JsonResponse({'token':secret,'redeem_path':'/vote/open/redeem','redeem_url':request.build_absolute_uri('/vote/open/redeem?event='+event.slug+'&token='+secret)},status=201)
    response['Cache-Control']='no-store'
    return response


def redeem_open_link(request):
    if request.method=='GET':
        event=_active(request,'open')
        if not event:return JsonResponse({'error':'Open-link voting is not active'},status=403)
        token=request.GET.get('token','')
        if not 20<=len(token)<=128:return JsonResponse({'error':'Invalid token'},status=403)
        # A GET previews a one-use link; only the CSRF-protected POST consumes it.
        row=VoterAccess.objects.filter(event=event,kind='open',secret_hash=_digest(event,token),redeemed_at__isnull=True,expires_at__gt=timezone.now()).first()
        if not row:return JsonResponse({'error':'Token invalid or used'},status=403)
        response=render(request,'voter_access.html',{'event':event,'mode':'open','token':token})
        response['Cache-Control']='no-store'
        response['Referrer-Policy']='no-referrer'
        response['X-Robots-Tag']='noindex, nofollow'
        return response
    if request.method!='POST':return HttpResponseNotAllowed(['GET','POST'])
    secret=request.POST.get('token','')
    if not 20<=len(secret)<=128:return JsonResponse({'error':'Invalid token'},status=403)
    with transaction.atomic():
        event=_active(request,'open')
        if not event:return JsonResponse({'error':'Open-link voting is not active'},status=403)
        event=Event.objects.select_for_update().get(pk=event.pk)
        if not voting_open(event) or event.voting_access!='open':
            return JsonResponse({'error':'Open-link voting is closed'},status=403)
        row=VoterAccess.objects.select_for_update().filter(event=event,kind='open',secret_hash=_digest(event,secret)).first()
        if not row or row.redeemed_at or row.expires_at<=timezone.now():
            return JsonResponse({'error':'Token invalid or used'},status=403)
        key='open:'+str(row.pk)
        if PublicVote.objects.filter(event=event,voter_key=key).exists():
            return JsonResponse({'error':'Already voted'},status=409)
        row.redeemed_at=timezone.now();row.save(update_fields=['redeemed_at'])
        request.session['voter_access']={'event':event.pk,'kind':'open','pk':row.pk}
    return JsonResponse({'ballot_path':'/ballot'},status=200)


def request_email_code(request):
    if request.method=='GET':
        event=_active(request,'email')
        if not event:return JsonResponse({'error':'Email voting is not active'},status=403)
        response=render(request,'voter_access.html',{'event':event,'mode':'email'})
        response['Cache-Control']='no-store'
        return response
    if request.method!='POST':return HttpResponseNotAllowed(['GET','POST'])
    event=_active(request,'email')
    if not event:return JsonResponse({'error':'Email voting is not active'},status=403)
    # Without an SMTP sender, no email is verified. Console/file backends are disabled.
    if settings.EMAIL_BACKEND != 'django.core.mail.backends.smtp.EmailBackend' or not getattr(settings,'VOTER_EMAIL_FROM',None) or not settings.EMAIL_HOST:
        return JsonResponse({'error':'Email delivery unavailable'},status=503)
    email=request.POST.get('email','').strip().lower()
    try:validate_email(email)
    except ValidationError:return JsonResponse({'error':'Valid email required'},status=400)
    if len(email)>254:return JsonResponse({'error':'Email too long'},status=400)
    with transaction.atomic():
        event=Event.objects.select_for_update().get(pk=event.pk)
        if event.voting_access!='email' or not voting_open(event):
            return JsonResponse({'error':'Email voting is closed'},status=403)
        if not action_allowed(event,'email:'+hashlib.sha256(email.encode()).hexdigest(),'email',request.META.get('REMOTE_ADDR'),limit=3):
            return JsonResponse({'error':'Too many requests'},status=429)
        # Refuse another code for a verified address. One address has one identity.
        row=VoterAccess.objects.filter(event=event,kind='email',identity=email).first()
        key='email:'+hashlib.sha256(email.encode()).hexdigest()
        if PublicVote.objects.filter(event=event,voter_key=key).exists():
            return JsonResponse({'error':'Already voted'},status=409)
        code=f'{secrets.randbelow(1000000):06d}'
        digest=_digest(event,email+':'+code)
        if row and row.redeemed_at:
            return JsonResponse({'error':'Address already verified'},status=409)
        if row:
            row.secret_hash=digest;row.expires_at=min(event.voting_closes,timezone.now()+timedelta(minutes=10));row.redeemed_at=None;row.save(update_fields=['secret_hash','expires_at','redeemed_at'])
        else:
            VoterAccess.objects.create(event=event,kind='email',identity=email,secret_hash=digest,
                expires_at=min(event.voting_closes,timezone.now()+timedelta(minutes=10)))
        try:
            delivered=send_mail('RaptorGate voting code',f'Your one-time voting code: {code}',settings.VOTER_EMAIL_FROM,[email],fail_silently=False)
        except Exception:
            transaction.set_rollback(True)
            return JsonResponse({'error':'Email delivery failed'},status=503)
        if delivered!=1:
            transaction.set_rollback(True)
            return JsonResponse({'error':'Email delivery failed'},status=503)
    return JsonResponse({'code_sent':True},status=202)


def redeem_email_code(request):
    if request.method!='POST':return HttpResponseNotAllowed(['POST'])
    event=_active(request,'email')
    if not event:return JsonResponse({'error':'Email voting is not active'},status=403)
    email=request.POST.get('email','').strip().lower()
    code=request.POST.get('code','')
    if len(email)>254 or not email or len(code)>64:
        return JsonResponse({'error':'Invalid code'},status=403)
    with transaction.atomic():
        event=Event.objects.select_for_update().get(pk=event.pk)
        if event.voting_access!='email' or not voting_open(event):
            return JsonResponse({'error':'Email voting is closed'},status=403)
        # Rate limit all guesses by email and IP, even when no valid row exists.
        ip=request.META.get('REMOTE_ADDR') or 'unknown'
        # Independent per-address and per-network budgets: rotating either one
        # cannot erase the other. Include malformed guesses in both budgets.
        email_hash=hashlib.sha256(email.encode()).hexdigest()
        address_ok=action_allowed(event,'verify-email:'+email_hash,'verify',ip,limit=5)
        network_ok=action_allowed(event,'verify-ip:'+ip,'verify',ip,limit=20)
        if not address_ok or not network_ok:
            return JsonResponse({'error':'Too many attempts'},status=429)
        if len(code)!=6 or not code.isascii() or not code.isdigit():
            return JsonResponse({'error':'Invalid code'},status=403)
        row=VoterAccess.objects.select_for_update().filter(event=event,kind='email',identity=email,secret_hash=_digest(event,email+':'+code)).first()
        if not row or row.redeemed_at or row.expires_at<=timezone.now():
            return JsonResponse({'error':'Invalid code'},status=403)
        if PublicVote.objects.filter(event=event,voter_key='email:'+hashlib.sha256(email.encode()).hexdigest()).exists():
            return JsonResponse({'error':'Already voted'},status=409)
        row.redeemed_at=timezone.now();row.save(update_fields=['redeemed_at'])
        request.session['voter_access']={'event':event.pk,'kind':'email','pk':row.pk}
    return JsonResponse({'ballot_path':'/ballot'},status=200)


def session_voter_key(request,event):
    grant=request.session.get('voter_access') or {}
    if grant.get('event')!=event.pk or grant.get('kind')!=event.voting_access:return None
    row=VoterAccess.objects.filter(pk=grant.get('pk'),event=event,kind=event.voting_access,redeemed_at__isnull=False).first()
    if not row or row.expires_at<=timezone.now():return None
    if row.kind=='open':return 'open:'+str(row.pk)
    return 'email:'+hashlib.sha256(row.identity.encode()).hexdigest()
