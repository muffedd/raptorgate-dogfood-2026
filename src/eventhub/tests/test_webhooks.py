"""Explicit operator webhook queue: authorization, transaction, signed retry."""
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from eventhub.models import Event, WebhookDelivery
from eventhub.webhooks import config, dispatch_pending

SECRET='not-a-real-key-'*4

class WebhookTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event=Event.objects.create(slug='hook',title='Hook',active=True,
                                        submissions_close=timezone.now()-timedelta(days=1))
        cls.organizer=get_user_model().objects.create_superuser('hook-org','org@example.org','pw')
        cls.other=get_user_model().objects.create_user('hook-other')

    def test_not_configured_does_not_queue_or_send(self):
        self.client.force_login(self.organizer)
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(self.client.post('/organizer/publish').status_code,200)
            self.assertFalse(WebhookDelivery.objects.exists())
            self.assertEqual(dispatch_pending(),(0,0))

    @patch('eventhub.webhooks.build_opener')
    def test_publish_queues_once_and_explicit_command_signs(self, opener):
        self.client.force_login(self.organizer)
        class Response:
            status=204
            def __enter__(self):return self
            def __exit__(self,*args):return False
        opener.return_value.open.return_value=Response()
        with patch.dict('os.environ',{'RESULTS_WEBHOOK_URL':'https://example.org/events',
                                      'RESULTS_WEBHOOK_SECRET':SECRET}):
            self.assertEqual(self.client.post('/organizer/publish').status_code,200)
            self.assertEqual(self.client.post('/organizer/publish').status_code,200)
            self.assertEqual(WebhookDelivery.objects.count(),1)
            self.assertEqual(opener.call_count,0)
            row=WebhookDelivery.objects.get()
            self.assertEqual(row.payload,{'type':'results.published','event':'hook'})
            self.assertEqual(dispatch_pending(),(1,1))
            req=opener.return_value.open.call_args.args[0]
            from hashlib import sha256
            from hmac import new
            self.assertEqual(req.get_header('X-raptorgate-signature-256'),
                             'sha256='+new(SECRET.encode(),req.data,sha256).hexdigest())
            self.assertEqual(dispatch_pending(),(0,0))
            row.refresh_from_db();self.assertEqual(row.attempts,1)
            self.assertIsNotNone(row.delivered_at)

    @patch('eventhub.webhooks.build_opener')
    def test_failed_delivery_remains_pending_and_visible_only_to_organizer(self, opener):
        WebhookDelivery.objects.create(event=self.event,kind='results.published',payload={'type':'results.published','event':'hook'})
        opener.return_value.open.side_effect=TimeoutError('offline')
        with patch.dict('os.environ',{'RESULTS_WEBHOOK_URL':'https://example.org/events',
                                      'RESULTS_WEBHOOK_SECRET':SECRET}):
            self.assertEqual(dispatch_pending(),(1,0))
            row=WebhookDelivery.objects.get();self.assertEqual(row.attempts,1)
            self.assertIsNone(row.delivered_at)
            self.assertEqual(row.last_status,'error:TimeoutError')
            self.assertEqual(self.client.get('/organizer/webhooks/deliveries').status_code,403)
            self.client.force_login(self.other)
            self.assertEqual(self.client.get('/organizer/webhooks/deliveries').status_code,403)
            self.client.force_login(self.organizer)
            rows=self.client.get('/organizer/webhooks/deliveries').json()['deliveries']
            self.assertEqual(rows[0]['attempts'],1)
            self.assertFalse(rows[0]['delivered'])
            self.assertNotIn(SECRET,str(rows))
            self.assertNotIn('example.org',str(rows))

    def test_invalid_config_fails_closed(self):
        for url in ('http://example.org/x','https://user:pass@example.org/x',
                    'https://example.org:8443/x','https://example.org:bad/x','https://example.org/x#frag'):
            with self.subTest(url=url), patch.dict('os.environ',{'RESULTS_WEBHOOK_URL':url,
                                                   'RESULTS_WEBHOOK_SECRET':SECRET}):
                self.assertIsNone(config())
