"""Preview boundary tests run in a subprocess because settings are process-wide."""
import os
import subprocess
import sys
from django.test import SimpleTestCase

class PreviewModeTests(SimpleTestCase):
    def test_public_preview_blocks_fixture_credentials_and_writes(self):
        env=os.environ.copy()
        env.update(RAPTORGATE_PUBLIC_PREVIEW='1', DJANGO_DEBUG='0',
                   DJANGO_SECRET_KEY='unique-preview-test-key',
                   RAPTORGATE_PREVIEW_HOST='example.onrender.com',
                   DATABASE_URL='postgres://testuser:testpass@preview-database.example:5432/testdb')
        code='''import django
from django.conf import settings
from django.test import Client
django.setup()
assert settings.ALLOWED_HOSTS == ['example.onrender.com']
assert settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
assert settings.SECURE_SSL_REDIRECT
c=Client(HTTP_HOST='example.onrender.com',HTTP_X_FORWARDED_PROTO='https')
for path in ['/signup/', '/vote', '/organizer/publish', '/events/new', '/verify', '/projects/sample-project']:
    assert c.post(path, {}).status_code == 405
for path in ['/ballot','/signup/','/login/','/organizer/overview']:
    assert c.get(path).status_code == 302
'''
        result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)

    def test_public_preview_fails_closed_without_secure_settings(self):
        env=os.environ.copy()
        env.update(RAPTORGATE_PUBLIC_PREVIEW='1', DJANGO_DEBUG='1',
                   DJANGO_SECRET_KEY='local-demo-key-not-for-production',
                   RAPTORGATE_PREVIEW_HOST='example.onrender.com',
                   DATABASE_URL='postgres://testuser:testpass@preview-database.example:5432/testdb')
        result=subprocess.run([sys.executable,'-c','import django; django.setup()'],env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Public preview requires DEBUG=0',result.stderr)
