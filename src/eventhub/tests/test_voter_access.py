"""End-to-end access grants and negative checks on live Django/PostgreSQL."""
from datetime import timedelta
from unittest.mock import patch
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from eventhub.models import Event, PublicVote, VoterAccess
from .t3_helpers import make_event, make_organizer, make_project, make_user

class OpenLinkTests(TestCase):
    def setUp(self):
        self.event=make_event('open-mode',access='open')
        self.project=make_project(self.event)
        self.org=make_organizer('open-org')

    def issue(self):
        self.client.force_login(self.org)
        response=self.client.post('/organizer/vote/open-link',{'event':self.event.slug})
        self.assertEqual(response.status_code,201)
        self.client.logout()
        return response.json()['token']

    def test_unauthorized_issue_and_unverified_ballot(self):
        self.assertEqual(self.client.post('/organizer/vote/open-link',{'event':self.event.slug}).status_code,403)
        self.assertEqual(self.client.get('/ballot').status_code,403)
        self.client.force_login(make_user('registered'))
        self.assertEqual(self.client.get('/ballot').status_code,403)

    def test_one_use_link_grants_one_ballot_and_receipt(self):
        token=self.issue()
        self.assertEqual(VoterAccess.objects.count(),1)
        self.assertNotEqual(VoterAccess.objects.get().secret_hash,token)
        self.assertEqual(self.client.post('/vote/open/redeem',{'event':self.event.slug,'token':token}).status_code,200)
        self.assertEqual(self.client.get('/ballot').status_code,200)
        self.assertEqual(self.client.post('/vote',{'event':self.event.slug,'project':self.project.slug}).status_code,201)
        self.assertEqual(self.client.post('/vote',{'event':self.event.slug,'project':self.project.slug}).status_code,409)
        other=Client()
        self.assertEqual(other.post('/vote/open/redeem',{'event':self.event.slug,'token':token}).status_code,403)
        self.assertEqual(other.get('/ballot').status_code,403)
        self.assertEqual(PublicVote.objects.count(),1)

    def test_forged_or_cross_event_or_expired_link(self):
        token=self.issue()
        self.assertEqual(self.client.post('/vote/open/redeem',{'event':self.event.slug,'token':'not-real-token-with-enough-length'}).status_code,403)
        make_event('foreign-mode',active=False,access='open')
        self.assertEqual(self.client.post('/vote/open/redeem',{'event':'foreign-mode','token':token}).status_code,403)
        self.event.voting_closes=timezone.now()-timedelta(seconds=1);self.event.save()
        self.assertEqual(self.client.post('/vote/open/redeem',{'event':self.event.slug,'token':token}).status_code,403)

    def test_grant_revoked_by_mode_switch(self):
        token=self.issue()
        self.client.post('/vote/open/redeem',{'event':self.event.slug,'token':token})
        Event.objects.filter(pk=self.event.pk).update(voting_access='email')
        self.assertEqual(self.client.get('/ballot').status_code,403)

class EmailCodeTests(TestCase):
    def setUp(self):
        self.event=make_event('email-mode',access='email')
        self.project=make_project(self.event)
        self.email='voter@example.org'

    def test_no_smtp_fails_closed_without_issuing(self):
        self.assertEqual(self.client.post('/vote/email/request',{'event':self.event.slug,'email':self.email}).status_code,503)
        self.assertEqual(self.client.get('/ballot').status_code,403)
        self.assertFalse(VoterAccess.objects.exists())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',VOTER_EMAIL_FROM='vote@example.org',EMAIL_HOST='smtp.example.org')
    @patch('eventhub.voter_access.send_mail',return_value=1)
    def test_verified_mail_code_once_per_address(self,send):
        response=self.client.post('/vote/email/request',{'event':self.event.slug,'email':self.email})
        self.assertEqual(response.status_code,202)
        code=send.call_args.args[1].rsplit(' ',1)[-1]
        self.assertEqual(len(code),6)
        self.assertNotIn(code,VoterAccess.objects.get().secret_hash)
        self.assertEqual(self.client.get('/ballot').status_code,403)
        self.assertEqual(self.client.post('/vote/email/redeem',{'event':self.event.slug,'email':self.email,'code':'000000' if code!='000000' else '000001'}).status_code,403)
        self.assertEqual(self.client.post('/vote/email/redeem',{'event':self.event.slug,'email':self.email,'code':code}).status_code,200)
        self.assertEqual(self.client.get('/ballot').status_code,200)
        self.assertEqual(self.client.post('/vote',{'event':self.event.slug,'project':self.project.slug}).status_code,201)
        other=Client()
        self.assertEqual(other.post('/vote/email/request',{'event':self.event.slug,'email':self.email}).status_code,409)
        self.assertEqual(other.get('/ballot').status_code,403)
        self.assertEqual(PublicVote.objects.count(),1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',VOTER_EMAIL_FROM='vote@example.org',EMAIL_HOST='smtp.example.org')
    @patch('eventhub.voter_access.send_mail',side_effect=OSError('smtp down'))
    def test_mail_failure_rolls_back_code(self,_):
        self.assertEqual(self.client.post('/vote/email/request',{'event':self.event.slug,'email':self.email}).status_code,503)
        self.assertFalse(VoterAccess.objects.exists())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',VOTER_EMAIL_FROM='vote@example.org',EMAIL_HOST='smtp.example.org')
    @patch('eventhub.voter_access.send_mail',return_value=1)
    def test_attempts_rate_limited(self,send):
        self.client.post('/vote/email/request',{'event':self.event.slug,'email':self.email})
        for _ in range(5):
            self.assertEqual(self.client.post('/vote/email/redeem',{'event':self.event.slug,'email':self.email,'code':'999999'}).status_code,403)
        self.assertEqual(self.client.post('/vote/email/redeem',{'event':self.event.slug,'email':self.email,'code':'999999'}).status_code,429)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',VOTER_EMAIL_FROM='vote@example.org',EMAIL_HOST='smtp.example.org')
    @patch('eventhub.voter_access.send_mail',return_value=1)
    def test_email_grant_cannot_be_reissued_after_redeem(self,send):
        self.client.post('/vote/email/request',{'event':self.event.slug,'email':self.email})
        code=send.call_args.args[1].rsplit(' ',1)[-1]
        self.assertEqual(self.client.post('/vote/email/redeem',{'event':self.event.slug,'email':self.email,'code':code}).status_code,200)
        second=Client()
        self.assertEqual(second.post('/vote/email/request',{'event':self.event.slug,'email':self.email}).status_code,409)
        self.assertEqual(second.get('/ballot').status_code,403)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',VOTER_EMAIL_FROM='vote@example.org',EMAIL_HOST='smtp.example.org')
    @patch('eventhub.voter_access.send_mail',return_value=1)
    def test_email_grant_expires_and_does_not_cross_events(self,send):
        self.client.post('/vote/email/request',{'event':self.event.slug,'email':self.email})
        code=send.call_args.args[1].rsplit(' ',1)[-1]
        VoterAccess.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.client.post('/vote/email/redeem',{'event':self.event.slug,'email':self.email,'code':code}).status_code,403)
        self.assertEqual(self.client.get('/ballot').status_code,403)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',VOTER_EMAIL_FROM='vote@example.org',EMAIL_HOST='smtp.example.org')
    @patch('eventhub.voter_access.send_mail',return_value=1)
    def test_guesses_across_ips_and_addresses_have_separate_limits(self,send):
        self.client.post('/vote/email/request',{'event':self.event.slug,'email':self.email})
        code=send.call_args.args[1].rsplit(' ',1)[-1]
        wrong='000000' if code!='000000' else '000001'
        for i in range(5):
            self.assertEqual(self.client.post('/vote/email/redeem',{'event':self.event.slug,'email':self.email,'code':wrong},REMOTE_ADDR=f'192.0.2.{i+1}').status_code,403)
        self.assertEqual(self.client.post('/vote/email/redeem',{'event':self.event.slug,'email':self.email,'code':code},REMOTE_ADDR='192.0.2.100').status_code,429)
        for i in range(4):
            self.assertEqual(self.client.post('/vote/email/redeem',{'event':self.event.slug,'email':f'other{i}@example.org','code':wrong},REMOTE_ADDR='192.0.2.200').status_code,403)
        self.assertEqual(self.client.post('/vote/email/redeem',{'event':self.event.slug,'email':'other4@example.org','code':'malformed'},REMOTE_ADDR='192.0.2.200').status_code,403)

class ModeCSRFTests(TestCase):
    def setUp(self):
        self.event=make_event('csrf-mode',access='open')
        self.project=make_project(self.event)
        self.org=make_organizer('csrf-org')

    def test_open_link_get_preview_does_not_consume_and_post_needs_csrf(self):
        self.client.force_login(self.org)
        token=self.client.post('/organizer/vote/open-link',{'event':self.event.slug}).json()['token']
        check=Client(enforce_csrf_checks=True)
        preview=check.get('/vote/open/redeem',{'event':self.event.slug,'token':token})
        self.assertEqual(preview.status_code,200)
        self.assertEqual(preview['Cache-Control'],'no-store')
        self.assertEqual(preview['Referrer-Policy'],'no-referrer')
        self.assertFalse(VoterAccess.objects.get().redeemed_at)
        self.assertEqual(check.post('/vote/open/redeem',{'event':self.event.slug,'token':token}).status_code,403)
        self.assertFalse(VoterAccess.objects.get().redeemed_at)
        csrf=check.cookies['csrftoken'].value
        self.assertEqual(check.post('/vote/open/redeem',{'event':self.event.slug,'token':token},HTTP_X_CSRFTOKEN=csrf).status_code,200)

    def test_anonymous_cannot_mint_link_even_with_token_guess(self):
        self.assertEqual(self.client.post('/organizer/vote/open-link',{'event':self.event.slug}).status_code,403)
        self.assertEqual(self.client.get('/vote/open/redeem',{'event':self.event.slug,'token':'x'*30}).status_code,403)
        self.assertFalse(VoterAccess.objects.exists())

class AccessIsolatedByEventTests(TestCase):
    def test_grant_cannot_vote_in_other_active_event(self):
        first=make_event('grant-first',access='open')
        make_project(first,'first-project')
        org=make_organizer('switch-org')
        self.client.force_login(org)
        token=self.client.post('/organizer/vote/open-link',{'event':first.slug}).json()['token']
        self.client.logout()
        self.assertEqual(self.client.post('/vote/open/redeem',{'event':first.slug,'token':token}).status_code,200)
        Event.objects.filter(pk=first.pk).update(active=False)
        second=make_event('grant-second',access='open')
        make_project(second,'second-project')
        self.assertEqual(self.client.get('/ballot').status_code,403)
        self.assertEqual(self.client.post('/vote',{'project':'second-project','event':second.slug}).status_code,403)
        self.assertFalse(PublicVote.objects.exists())

