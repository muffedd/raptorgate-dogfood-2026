"""Portable certificate boundary: signed snapshot, public gate, independent verification."""
import base64
import json
from datetime import timedelta
from unittest.mock import patch
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, JudgeCertificate, Project, Score, Team, Track


class CertificateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now=timezone.now()
        cls.event=Event.objects.create(slug='cert-event',title='Event',active=True,published=True,
             voting_closes=now-timedelta(hours=1),submissions_close=now-timedelta(days=1))
        cls.track=Track.objects.create(event=cls.event,slug='t',name='Track')
        cls.team=Team.objects.create(event=cls.event,slug='team',name='Team')
        cls.project=Project.objects.create(event=cls.event,track=cls.track,team=cls.team,slug='p',title='Visible')
        User=get_user_model()
        cls.organizer=User.objects.create_superuser('cert-org','cert-org@example.org','pw')
        cls.other=User.objects.create_user('cert-other')
        cls.judge=Judge.objects.create(event=cls.event,user=cls.other,slug='j')
        Score.objects.create(judge=cls.judge,project=cls.project,
                             criteria={'functionality':4,'quality':3,'innovation':5},comment='Private comment')

    def key(self):
        private=Ed25519PrivateKey.generate()
        pem=private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()).decode()
        return private,pem

    def test_issue_download_and_verify_without_server_secret(self):
        private,pem=self.key()
        self.client.force_login(self.organizer)
        with patch.dict('os.environ',{'CERTIFICATE_PRIVATE_KEY_PEM':pem}):
            created=self.client.post('/organizer/certificates/issue',{'judge':'j'})
        self.assertEqual(created.status_code,201)
        pk=created.json()['certificate_id']
        self.assertEqual(JudgeCertificate.objects.count(),1)
        self.client.logout()
        with patch.dict('os.environ',{},clear=True):
            response=self.client.get(f'/certificates/{pk}.json')
        self.assertEqual(response.status_code,200)
        cert=response.json()
        self.assertEqual(cert['algorithm'],'Ed25519')
        self.assertEqual(cert['payload']['review_count'],1)
        self.assertNotIn('Private comment',str(cert))
        self.assertNotIn('criteria',str(cert))
        public=Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(cert['public_key']+'='*((-len(cert['public_key']))%4)))
        signed=json.dumps(cert['payload'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        signature=base64.urlsafe_b64decode(cert['signature']+'='*((-len(cert['signature']))%4))
        public.verify(signature,signed)
        with self.assertRaises(InvalidSignature):
            public.verify(signature,signed+b'x')
        self.assertEqual(private.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw),
                         public.public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw))
        self.client.force_login(self.organizer)
        with patch.dict('os.environ',{'CERTIFICATE_PRIVATE_KEY_PEM':pem}):
            again=self.client.post('/organizer/certificates/issue',{'judge':'j'})
        self.assertEqual(again.status_code,200)
        self.assertEqual(again.json()['certificate_id'],pk)

    def test_denials_key_and_release_gate(self):
        self.assertEqual(self.client.post('/organizer/certificates/issue',{'judge':'j'}).status_code,403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post('/organizer/certificates/issue',{'judge':'j'}).status_code,403)
        self.client.force_login(self.organizer)
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(self.client.post('/organizer/certificates/issue',{'judge':'j'}).status_code,503)
        _,pem=self.key()
        with patch.dict('os.environ',{'CERTIFICATE_PRIVATE_KEY_PEM':pem}):
            pk=self.client.post('/organizer/certificates/issue',{'judge':'j'}).json()['certificate_id']
        JudgeCertificate.objects.filter(pk=pk).update(payload={'tampered':True})
        self.assertEqual(self.client.get(f'/certificates/{pk}.json').status_code,409)
        JudgeCertificate.objects.filter(pk=pk).update(public_key='not_base64!')
        self.assertEqual(self.client.get(f'/certificates/{pk}.json').status_code,409)
        self.event.published=False;self.event.save(update_fields=['published'])
        self.assertEqual(self.client.get(f'/certificates/{pk}.json').status_code,404)
        with patch.dict('os.environ',{'CERTIFICATE_PRIVATE_KEY_PEM':pem}):
            self.assertEqual(self.client.post('/organizer/certificates/issue',{'judge':'j'}).status_code,409)
