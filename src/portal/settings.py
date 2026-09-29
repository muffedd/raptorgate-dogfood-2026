import os
from pathlib import Path
from urllib.parse import urlparse
from django.core.exceptions import ImproperlyConfigured
BASE_DIR = Path(__file__).resolve().parent.parent
PREVIEW = os.environ.get('RAPTORGATE_PUBLIC_PREVIEW') == '1'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'local-test-only-secret')
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'portal', 'testserver']
if PREVIEW:
    if DEBUG or SECRET_KEY in ('', 'local-test-only-secret', 'local-demo-key-not-for-production'):
        raise ImproperlyConfigured('Public preview requires DEBUG=0 and a unique DJANGO_SECRET_KEY')
    preview_host = os.environ.get('RAPTORGATE_PREVIEW_HOST', '')
    if not preview_host.endswith('.onrender.com') or preview_host.startswith('.') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789.-' for c in preview_host):
        raise ImproperlyConfigured('Public preview requires an explicit onrender.com host')
    ALLOWED_HOSTS = [preview_host]
    CSRF_TRUSTED_ORIGINS = ['https://' + preview_host]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    SECURE_HSTS_SECONDS = 3600
    X_FRAME_OPTIONS = 'DENY'
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'eventhub']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware']
if PREVIEW:
    MIDDLEWARE += ['portal.preview_middleware.PreviewReadOnlyMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware']
MIDDLEWARE += ['django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware']
if PREVIEW:
    MIDDLEWARE += ['django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'portal.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'portal.wsgi.application'
url = os.environ.get('DATABASE_URL')
if url:
    db=urlparse(url)
    DATABASES={'default': {'ENGINE':'django.db.backends.postgresql','NAME':db.path.lstrip('/'),'USER':db.username,'PASSWORD':db.password,'HOST':db.hostname,'PORT':db.port or 5432}}
else:
    DATABASES={'default': {'ENGINE':'django.db.backends.sqlite3','NAME':str(BASE_DIR/'db.sqlite3')}}
AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE='en-us'
TIME_ZONE='UTC'
USE_TZ=True
STATIC_URL='static/'
STATICFILES_DIRS=[BASE_DIR/'static']
STATIC_ROOT=BASE_DIR/'staticfiles'
STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
          'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage' if PREVIEW else 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
if PREVIEW and not url:
    raise ImproperlyConfigured('Public preview requires DATABASE_URL')
if PREVIEW:
    # No fixture keys or localhost fallback on the public path.
    if 'local-demo-only' in (url or '') or 'localhost' in (url or ''):
        raise ImproperlyConfigured('Public preview cannot use the local fixture database')
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
LOGIN_URL='/login/'

EMAIL_BACKEND = os.environ.get('VOTER_EMAIL_BACKEND', '')
VOTER_EMAIL_FROM = os.environ.get('VOTER_EMAIL_FROM', '')
EMAIL_HOST = os.environ.get('VOTER_SMTP_HOST', '')
EMAIL_PORT = int(os.environ.get('VOTER_SMTP_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('VOTER_SMTP_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('VOTER_SMTP_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('VOTER_SMTP_TLS', '1') == '1'
