"""Real SMTP transport through a loopback capture, not a mocked send_mail."""
from aiosmtpd.controller import Controller
import socket
from django.test import TestCase, override_settings
from eventhub.models import PublicVote, VoterAccess
from .t3_helpers import make_event, make_project


class Capture:
    def __init__(self):
        self.messages=[]

    async def handle_DATA(self, server, session, envelope):
        self.messages.append((envelope.mail_from, envelope.rcpt_tos,
                              envelope.content.decode('utf-8')))
        return '250 Message accepted'


class RealSMTPTests(TestCase):
    def test_smtp_delivery_redeem_ballot_and_duplicate_guard(self):
        capture=Capture()
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0))
            port=probe.getsockname()[1]
        controller=Controller(capture,hostname='127.0.0.1',port=port)
        controller.start()
        try:
            with override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                    VOTER_EMAIL_FROM='vote@localhost.test',EMAIL_HOST='127.0.0.1',
                    EMAIL_PORT=controller.server.sockets[0].getsockname()[1],EMAIL_USE_TLS=False):
                event=make_event('smtp',access='email')
                project=make_project(event)
                address='reader@localhost.test'
                sent=self.client.post('/vote/email/request',{'event':event.slug,'email':address})
                self.assertEqual(sent.status_code,202)
                self.assertEqual(len(capture.messages),1)
                sender,recipients,body=capture.messages[0]
                self.assertEqual((sender,recipients),('vote@localhost.test',[address]))
                code=body.split('Your one-time voting code: ')[1][:6]
                self.assertEqual(len(code),6)
                self.assertNotIn(code,VoterAccess.objects.get().secret_hash)
                self.assertEqual(self.client.post('/vote/email/redeem',{'event':event.slug,'email':address,'code':code}).status_code,200)
                self.assertEqual(self.client.get('/ballot').status_code,200)
                self.assertEqual(self.client.post('/vote',{'event':event.slug,'project':project.slug}).status_code,201)
                self.assertEqual(self.client.post('/vote',{'event':event.slug,'project':project.slug}).status_code,409)
                self.assertEqual(PublicVote.objects.count(),1)
        finally:
            controller.stop()
