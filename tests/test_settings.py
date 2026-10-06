"""Test settings - uses SQLite and mocks external services."""
from cv_recruiter.settings import *  # noqa: F401, F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

GEMINI_API_KEY = 'test-key'
LINKEDIN_EMAIL = ''
LINKEDIN_PASSWORD = ''
