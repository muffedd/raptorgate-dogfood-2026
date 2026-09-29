import json
from datetime import timedelta
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import TestCase
from django.utils import timezone
from eventhub.models import PublicVote
from .t3_helpers import make_event, make_project
from eventhub.certificates import canonical, unb64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

def verify(document, trusted):
    try:
        Ed25519PublicKey.from_public_bytes(unb64(trusted)).verify(unb64(document["signature"]),canonical(document["payload"]))
        return True, "valid"
    except (InvalidSignature,ValueError):
        return False, "invalid"


class SignedVoteProofTests(TestCase):
    def test_publication_key_and_offline_verification(self):
        event=make_event('signed-vote')
        project=make_project(event)
        vote=PublicVote.objects.create(event=event,project=project,voter_key='user:7',receipt='f'*32)
        path=f'/receipt/{vote.receipt}/proof'
        self.assertEqual(self.client.get(path).status_code,404)
        event.published=True
        event.voting_closes=timezone.now()-timedelta(seconds=1)
        event.save()
        self.assertEqual(self.client.get(path).status_code,503)
        with patch('eventhub.public_proofs.signing_key',return_value=Ed25519PrivateKey.generate()):
            result=self.client.get(path)
            self.assertEqual(result.status_code,200)
            self.assertEqual(result['Cache-Control'],'no-store')
            document=result.json()
            self.assertEqual(document['payload']['project'],project.slug)
            self.assertNotIn('voter_key',json.dumps(document))
            self.assertTrue(verify(document,document['public_key'])[0])
            document['payload']['project']='wrong'
            self.assertFalse(verify(document,document['public_key'])[0])
        self.assertEqual(self.client.get('/receipt/'+'e'*32+'/proof').status_code,404)
