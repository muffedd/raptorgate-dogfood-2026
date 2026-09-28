"""Three intentionally different public verdicts, plus offline Ed25519 round trip."""
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, Judge, Project, PublicVote, Score, Team, Track


class PublicVerifyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from datetime import timedelta
        now = timezone.now()
        cls.event = Event.objects.create(slug='verify-event', title='Verify event', active=True,
                 published=True, submissions_close=now-timedelta(days=2), voting_closes=now-timedelta(days=1))
        track = Track.objects.create(event=cls.event, slug='t', name='Track')
        team = Team.objects.create(event=cls.event, slug='team', name='Team')
        project = Project.objects.create(event=cls.event, track=track, team=team, slug='proof', title='Proof project')
        User = get_user_model()
        cls.organizer = User.objects.create_superuser('verify-organizer', 'o@example.com', 'pw')
        cls.judge = Judge.objects.create(event=cls.event, user=User.objects.create_user('verify-judge'), slug='judge')
        Score.objects.create(judge=cls.judge, project=project, criteria={'quality': 4, 'innovation': 4, 'functionality': 4})
        cls.receipt = 'b' * 32
        PublicVote.objects.create(event=cls.event, project=project, voter_key='user:123', receipt=cls.receipt)

    def check(self, kind, artifact):
        return self.client.post('/verify', {'kind': kind, 'artifact': artifact})

    def test_receipt_gate_no_identity_and_bad_tokens(self):
        self.assertContains(self.client.get('/verify'), 'Verify an artifact')
        page = self.check('receipt', self.receipt)
        self.assertContains(page, 'MATCH')
        self.assertNotContains(page, 'user:123')
        self.assertNotContains(page, 'verify-judge')
        self.assertContains(self.check('receipt', 'a'*32), 'NO MATCH')
        self.assertContains(self.check('receipt', 'bad'), 'NO MATCH')
        self.event.published = False
        self.event.save(update_fields=['published'])
        self.assertContains(self.check('receipt', self.receipt), 'NO MATCH')

    def issue_cert(self):
        private = Ed25519PrivateKey.generate()
        pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()).decode()
        self.client.force_login(self.organizer)
        with patch.dict(os.environ, {'CERTIFICATE_PRIVATE_KEY_PEM': pem}):
            issued = self.client.post('/organizer/certificates/issue', {'judge': 'judge'})
        self.assertEqual(issued.status_code, 201)
        self.client.logout()
        return self.client.get(issued.json()['download_path']).json()

    def test_certificate_site_verdict_and_offline_round_trip(self):
        doc = self.issue_cert()
        self.assertContains(self.check('certificate', json.dumps(doc)), 'MATCH')
        modified = copy.deepcopy(doc)
        modified['payload']['review_count'] = 999
        self.assertContains(self.check('certificate', json.dumps(modified)), 'NO MATCH')
        spoofed = copy.deepcopy(doc)
        other = Ed25519PrivateKey.generate()
        from eventhub.certificates import b64, canonical
        spoofed['public_key'] = b64(other.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        spoofed['signature'] = b64(other.sign(canonical(spoofed['payload'])))
        self.assertContains(self.check('certificate', json.dumps(spoofed)), 'not a published issuance')
        script = Path(__file__).resolve().parents[3] / 'verify.py'
        with NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.json') as f:
            json.dump(doc, f); f.flush()
            good = subprocess.run([sys.executable, str(script), f.name, '--trusted-public-key', doc['public_key']], capture_output=True, text=True)
            bad_key = subprocess.run([sys.executable, str(script), f.name, '--trusted-public-key', spoofed['public_key']], capture_output=True, text=True)
            no_key = subprocess.run([sys.executable, str(script), f.name], capture_output=True, text=True)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertIn('matches the supplied trusted organizer key', good.stdout)
            self.assertEqual(bad_key.returncode, 1)
            self.assertIn('identity is NOT verified', no_key.stdout)
            self.assertEqual(no_key.returncode, 0)
            f.seek(0); f.truncate(); json.dump(modified, f); f.flush()
            tampered = subprocess.run([sys.executable, str(script), f.name, '--trusted-public-key', doc['public_key']], capture_output=True, text=True)
            self.assertEqual(tampered.returncode, 1)
            self.assertIn('INVALID', tampered.stdout)
        self.event.published = False; self.event.save(update_fields=['published'])
        self.assertContains(self.check('certificate', json.dumps(doc)), 'not a published issuance')

    def test_record_and_method_limits(self):
        self.client.force_login(self.organizer)
        with patch.dict(os.environ, {'RECORD_SIGNING_KEY': 'unique-test-only-record-key-2026'*2}):
            record = self.client.post('/organizer/records/issue', {'judge': 'judge'})
            self.assertEqual(record.status_code, 201)
            self.client.logout()
            rid = str(record.json()['record_id'])
            self.assertContains(self.check('record', rid), 'MATCH')
        with patch.dict(os.environ, {}, clear=True):
            self.assertContains(self.check('record', rid), 'CHECK UNAVAILABLE')
        self.assertContains(self.check('record', '999999'), 'NO MATCH')
        self.assertContains(self.check('record', '-1'), 'NO MATCH')
        self.assertContains(self.check('certificate', '{not json'), 'NO MATCH')
        self.assertContains(self.check('bogus', 'x'), 'NO MATCH')
        self.assertEqual(self.client.put('/verify').status_code, 405)
