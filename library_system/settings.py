import os
from pathlib import Path

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()


def _env_flag(name, default='0'):
    return os.getenv(name, default).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_list(name, default=''):
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Security
DEBUG = _env_flag('DEBUG', '0')

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        # Never used outside local development; production must supply SECRET_KEY.
        SECRET_KEY = 'django-insecure-local-development-only'
    else:
        raise ImproperlyConfigured('SECRET_KEY environment variable is required when DEBUG is off.')

_DEFAULT_ALLOWED_HOSTS = 'localhost 127.0.0.1 [::1]'
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', _DEFAULT_ALLOWED_HOSTS).split()

# Applications
INSTALLED_APPS = [
    # Django apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party apps
    'rest_framework',
    'corsheaders',
    # Local apps
    'library',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # CORS
    'django.middleware.security.SecurityMiddleware',
    # Serves the admin/DRF static assets straight from the container, so the
    # image does not need a second web server in front of gunicorn.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# CORS
CORS_ALLOW_ALL_ORIGINS = _env_flag('CORS_ALLOW_ALL_ORIGINS', '1' if DEBUG else '0')
CORS_ALLOWED_ORIGINS = _env_list('CORS_ALLOWED_ORIGINS')

ROOT_URLCONF = 'library_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],  # Add template directories if needed
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'library_system.wsgi.application'

# Database
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
if DB_ENGINE.endswith('sqlite3'):
    # Convenience backend for local runs and the test suite.
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': os.getenv('SQLITE_NAME', str(BASE_DIR / 'db.sqlite3')),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE,
            'NAME': os.getenv('POSTGRES_DB', 'library_db'),
            'USER': os.getenv('POSTGRES_USER', 'library_user'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'library_password'),
            'HOST': os.getenv('DB_HOST', 'db'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }

# Password Validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    # Add more validators as needed
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static Files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

# Default Primary Key Field Type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    # Anonymous clients may browse the catalogue; writes require a logged-in user.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'library.pagination.DefaultPagination',
    'PAGE_SIZE': 10,
    # Renders library.services.exceptions.DomainError as a 400 with a stable body.
    'EXCEPTION_HANDLER': 'library.api_errors.domain_exception_handler',
}

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
# Celery 6 makes this the default; setting it explicitly silences the warning.
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    'check-overdue-loans-daily': {
        'task': 'library.tasks.check_overdue_loans',
        # Runs every day at 08:00 UTC.
        'schedule': crontab(hour=8, minute=0),
    },
}

# Notifications
# Ordered dotted paths to NotificationChannel subclasses. Adding an SMS or push
# channel is a settings change plus one new class; nothing else moves.
NOTIFICATION_CHANNELS = _env_list(
    'NOTIFICATION_CHANNELS', 'library.notifications.email.EmailChannel'
)
# How many overdue reminders check_overdue_loans() buffers before flushing them
# to the channels. Bounds the task's peak memory regardless of backlog size.
OVERDUE_NOTIFICATION_BATCH_SIZE = int(os.getenv('OVERDUE_NOTIFICATION_BATCH_SIZE', '500'))

# Email Configuration
# The console backend prints messages to stdout, which is what the Compose stack
# and the test fixtures rely on; point EMAIL_BACKEND at SMTP in production.
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'admin@library.com')

# Logging - one handler, readable in `docker compose logs`.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {'format': '%(asctime)s %(levelname)-8s %(name)s %(message)s'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'standard'},
    },
    'loggers': {
        # 4xx responses are client errors and are already visible in the access
        # log; only log request failures the server is responsible for.
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
    },
    'root': {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO')},
}
