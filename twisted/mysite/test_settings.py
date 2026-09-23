# ruff: noqa: E402
"""Deterministic settings for the automated test suite."""

import os

_TEST_ENVIRONMENT = {
    "ALLOWED_HOSTS": "testserver,localhost,127.0.0.1",
    "ARI_INGEST_ENDPOINT": "https://example.invalid/ari/",
    "ARI_SIGNING_SECRET": "test-ari-signing-secret",
    "ARI_WEBHOOK_SECRET": "test-ari-webhook-secret",
    "CSRF_TRUSTED_ORIGINS": "http://testserver",
    "DEBUG": "false",
    "DEBUG_REVIEW": "false",
    "DEFAULT_PFP": "https://example.invalid/avatar.png",
    "HACKATIME_CLIENT_ID": "test-hackatime-client-id",
    "HACKATIME_CLIENT_SECRET": "test-hackatime-client-secret",
    "HACKATIME_REDIRECT_URI": "http://testserver/oauth/hackatime_callback",
    "HCA_CLIENT_ID": "test-hca-client-id",
    "HCA_CLIENT_SECRET": "test-hca-client-secret",
    "HCA_REDIRECT_URI": "http://testserver/oauth/callback",
    "LOGIN_ENABLED": "true",
    "POSTGRES_DB": "django",
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_PASSWORD": "django",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": "django",
    "R2_ACCESS_KEY": "test-r2-access-key",
    "R2_BUCKET": "test-r2-bucket",
    "R2_ENDPOINT": "https://example.invalid/r2",
    "R2_PUBLIC_URL": "https://example.invalid/uploads",
    "R2_SECRET_KEY": "test-r2-secret-key",
    "SECRET_KEY": "test-secret-key-that-is-only-used-by-the-automated-test-suite",
    "SLACK_LOG_CHANNEL": "C_TEST",
    "SLACK_TOKEN": "xoxb-test-token",
}

for _name, _value in _TEST_ENVIRONMENT.items():
    os.environ.setdefault(_name, _value)

from mysite.settings import *  # noqa: F403

DEBUG = False
DEBUG_REVIEW = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

MIDDLEWARE = [
    middleware
    for middleware in MIDDLEWARE  # noqa: F405
    if middleware != "whitenoise.middleware.WhiteNoiseMiddleware"
]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
