"""
Settings for `manage.py test`: PostgreSQL (like production), in-memory constance,
no Redis, Celery or Telegram.

    docker compose up -d db elasticsearch
    python manage.py test --settings=ms_data_mining.settings_test

TEST_DATABASE_URL defaults to the docker-compose database. Tests that need a real
Elasticsearch run only when ELASTICSEARCH_TEST_HOST is set (http://localhost:9200).
"""
import os

for key, value in {
    "SECRET_KEY": "test-secret-key",
    "ALLOWED_HOSTS": "*",
    "DATABASE_URL": os.environ.get(
        "TEST_DATABASE_URL", "postgres://kadabra:kadabra@localhost:5432/kadabra"
    ),
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
    "REDIS_DB": "0",
    "REDIS_DB_RES": "1",
    "CORS_ORIGIN_WHITELIST": "http://localhost",
    "CELERY_BROKER_URL": "memory://",
}.items():
    os.environ.setdefault(key, value)

from ms_data_mining.settings import *  # noqa: E402,F401,F403

# Django creates a fresh test database, without the production "ms_data_mining"
# schema, so use the default search_path there.
DATABASES["default"].pop("OPTIONS", None)  # noqa: F405
CONSTANCE_BACKEND = "constance.backends.memory.MemoryBackend"
CELERY_TASK_ALWAYS_EAGER = False
PRELOAD_NLP_MODEL = False
BOT_SECRET_TOKEN = ""
ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_TEST_HOST", "http://localhost:9200")
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# Keep test output readable (tests exercise error paths on purpose).
LOGGING["root"]["level"] = os.environ.get("TEST_LOG_LEVEL", "CRITICAL")  # noqa: F405
