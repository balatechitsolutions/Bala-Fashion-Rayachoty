import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DEBUG", "False").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = [v.strip() for v in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if v.strip()]
CORS_ALLOWED_ORIGINS = [v.strip() for v in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if v.strip()]
INSTALLED_APPS = ["django.contrib.admin","django.contrib.auth","django.contrib.contenttypes","django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles","corsheaders","rest_framework","api"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware","whitenoise.middleware.WhiteNoiseMiddleware","corsheaders.middleware.CorsMiddleware","django.contrib.sessions.middleware.SessionMiddleware","django.middleware.common.CommonMiddleware","django.middleware.csrf.CsrfViewMiddleware","django.contrib.auth.middleware.AuthenticationMiddleware","django.contrib.messages.middleware.MessageMiddleware","django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND":"django.template.backends.django.DjangoTemplates","DIRS":[BASE_DIR / "templates"],"APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.debug","django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASE_URL = os.getenv("DATABASE_URL","").strip()
DATABASES = {
    "default": {
        **dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "60")),
            ssl_require=True,
        ),
        "CONN_HEALTH_CHECKS": True,
    }
} if DATABASE_URL else {"default":{"ENGINE":"django.db.backends.sqlite3","NAME":BASE_DIR/"db.sqlite3"}}

# Shared cache when REDIS_URL is configured; local-memory fallback keeps development
# and deployments without Redis functional (but is not shared across instances).
REDIS_URL = os.getenv("REDIS_URL", "").strip()
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "TIMEOUT": 60,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "bala-fashion-catalog",
            "TIMEOUT": 60,
        }
    }

# Celery uses Redis for non-blocking background push delivery.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "").strip() or "redis://127.0.0.1:6379/0"
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_TRACK_STARTED = True
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR/"staticfiles"
STORAGES = {"default":{"BACKEND":"django.core.files.storage.FileSystemStorage"},"staticfiles":{"BACKEND":"whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# SMTP configuration is supplied through the Render environment. Never commit real credentials.
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
).strip()
EMAIL_HOST = os.getenv("EMAIL_HOST", "").strip()
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "").strip()
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").strip().lower() in ("1", "true", "yes", "on")
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").strip().lower() in ("1", "true", "yes", "on")
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "noreply@bala-fashion.local",
).strip()
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "15"))

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ValueError("Configure only one of EMAIL_USE_TLS or EMAIL_USE_SSL, not both.")
REST_FRAMEWORK = {"DEFAULT_RENDERER_CLASSES":["rest_framework.renderers.JSONRenderer"],"DEFAULT_PARSER_CLASSES":["rest_framework.parsers.JSONParser","rest_framework.parsers.FormParser","rest_framework.parsers.MultiPartParser"],"DEFAULT_THROTTLE_CLASSES":["rest_framework.throttling.AnonRateThrottle","rest_framework.throttling.UserRateThrottle"],"DEFAULT_THROTTLE_RATES":{"anon":"120/hour","user":"600/hour"}}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO","https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Send Django application errors and tracebacks to Render's stdout/stderr logs.
# Keep DEBUG disabled in production; logging does not expose settings or credentials.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "render": {
            "format": "{levelname} {asctime} {name} [{process:d}:{thread:d}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "render",
            "level": "INFO",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "api": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
