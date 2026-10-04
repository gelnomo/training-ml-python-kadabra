import os
from pathlib import Path
import environ

root = environ.Path(__file__)
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)
# Build paths inside the project like this: BASE_DIR / 'subdir'.
SECRETS_PATH_FILE = os.environ.get("SECRETS_PATH_FILE", None)
environ.Env.read_env(SECRETS_PATH_FILE)
BASE_DIR = Path(__file__).resolve().parent.parent
SITE_ROOT = os.path.abspath(os.path.dirname(__name__))
SECRET_KEY = env("SECRET_KEY", default="")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# Application definition

INSTALLED_APPS = [
    "admin_interface",
    "colorfield",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.forms",
    "django_json_widget",
    "image_uploader_widget",
    "django_celery_results",
    "django_celery_beat",
    "tinymce",
    "constance",
    "rangefilter",
    "phonenumber_field",
    "rest_framework_simplejwt",
    "import_export",
    "django_admin_inline_paginator",
    "adrf",
    # Apps
    "apps.document.apps.DocumentConfig",
    "apps.celebrity.apps.CelebrityConfig",
    "apps.movies.apps.MoviesConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ms_data_mining.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ms_data_mining.wsgi.application"

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["OPTIONS"] = {"options": "-c search_path=ms_data_mining"}
DATABASES["default"]["CONN_MAX_AGE"] = None

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/
PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_ROOT = os.path.join(PROJECT_DIR, "static")
STATIC_URL = "static/"

# CORS SECTION
CORS_ORIGIN_ALLOW_ALL = env.bool("CORS_ORIGIN_ALLOW_ALL", default=True)
CORS_ORIGIN_WHITELIST = env("CORS_ORIGIN_WHITELIST").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", default="").split(",") if o]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    )
}

X_FRAME_OPTIONS = "SAMEORIGIN"
SILENCED_SYSTEM_CHECKS = ["security.W019"]

# REDIS SECTION
REDIS_PORT = env("REDIS_PORT")
REDIS_DB = env("REDIS_DB")
REDIS_DB_RES = env("REDIS_DB_RES")
REDIS_HOST = env("REDIS_HOST")
BROKER_URL = env("CELERY_BROKER_URL")
BROKER_POOL_LIMIT = 3
BROKER_CONNECTION_TIMEOUT = 10

# CELERY SECTION
CELERY_RESULT_BACKEND = "django-db"
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERYD_PREFETCH_MULTIPLIER = 1

# CONSTANCE SECTION
CONSTANCE_REDIS_CONNECTION = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
CONSTANCE_IGNORE_ADMIN_VERSION_CHECK = True
CONSTANCE_SUPERUSER_ONLY = True
CONSTANCE_ADDITIONAL_FIELDS = {
    "time_type_enum": [
        "django.forms.fields.ChoiceField",
        {
            "widget": "django.forms.Select",
            "choices": (
                ("days", "Days"),
                ("seconds", "Seconds"),
                ("microseconds", "Microseconds"),
                ("milliseconds", "Milliseconds"),
                ("minutes", "Minutes"),
                ("hours", "Hours"),
                ("weeks", "Weeks"),
            ),
        },
    ],
    "text_search_mode_enum": [
        "django.forms.fields.ChoiceField",
        {
            "widget": "django.forms.Select",
            "choices": (
                ("vector", "Vector (one vector per movie)"),
                ("hybrid", "Hybrid (vector + BM25 keywords, RRF)"),
                ("passages", "Passages (several vectors per movie)"),
            ),
        },
    ],
}

CONSTANCE_CONFIG = {
    "CONFIG_ADMIN_LIMIT": (30, "page limit app Alert", int),
    "CONFIG_ADMIN_LISTING_IMAGE_HEIGHT": (100, "Thumbline height in admin page", int),
    "CONFIG_ACTOR_ATTEMPTS": (3, "Actor max attempts", int),
    "CONFIG_IMAGE_ATTEMPTS": (3, "Image max attempts", int),
    "TASK_TIME_TYPE": ("minutes", "select time type", "time_type_enum"),
    "TASK_TIME_VALUE": (5, "Integer number", int),
    "MOVIE_LIST_TIME_TYPE": ("days", "select time type", "time_type_enum"),
    "MOVIE_LIST_TIME_VALUE": (30, "Integer number", int),
    "K_TEXT": (3, "Number of movies related to show", int),
    # kNN score for cosine similarity: (1 + cos) / 2. 0.60 means cos >= 0.2.
    # Provisional: pick the value with `manage.py evaluate_search`.
    "THRESHOLD_TEXT": (0.60, "Min text kNN score (cosine: (1+cos)/2); tune with evaluate_search", float),
    # kNN score for l2_norm: 1 / (1 + d^2). 0.735 means distance < 0.6 (face_recognition's tolerance).
    "THRESHOLD_IMAGE": (0.735, "Min face kNN score (1/(1+d^2)); 0.735 = distance 0.6", float),
    "THRESHOLD_YEAR": (10, "Year window (+/-) used to boost photo-only results", int),
    "SIZE_MOVIE_LISTING": (100, "Size movie listing", int),
    "FACE_KNN_K": (10, "Nearest stored faces retrieved per query face (votes)", int),
    "FACE_NUM_CANDIDATES": (100, "HNSW candidates explored per face query", int),
    "FACE_MIN_VOTES": (1, "Min hits above the threshold an actor needs to be recognised", int),
    "TEXT_SEARCH_MODE": ("vector", "vector | hybrid | passages", "text_search_mode_enum"),
    "TEXT_PREPROCESS": (True, "Clean the text with NLTK (lemmas, no stop words) before encoding it", bool),
    "SCENE_SEARCH_ENABLED": (False, "Match photos without faces against movie posters (CLIP)", bool),
    "THRESHOLD_SCENE": (0.62, "Min poster kNN score (cosine: (1+cos)/2); tune with evaluate_search", float),
}

CONSTANCE_CONFIG_FIELDSETS = {
    "Admin Page - Options": (
        "CONFIG_ADMIN_LIMIT",
        "CONFIG_ADMIN_LISTING_IMAGE_HEIGHT",
    ),
    "Actor - Options": ("CONFIG_ACTOR_ATTEMPTS", "K_TEXT", "THRESHOLD_TEXT", "THRESHOLD_IMAGE", "THRESHOLD_YEAR"),
    "Image - Options": ("CONFIG_IMAGE_ATTEMPTS",),
    "Request Task Cache - Options": (
        "TASK_TIME_TYPE",
        "TASK_TIME_VALUE",
        "MOVIE_LIST_TIME_TYPE",
        "MOVIE_LIST_TIME_VALUE",
        "SIZE_MOVIE_LISTING"
    ),
    "Search - Options": (
        "FACE_KNN_K",
        "FACE_NUM_CANDIDATES",
        "FACE_MIN_VOTES",
        "TEXT_SEARCH_MODE",
        "TEXT_PREPROCESS",
        "SCENE_SEARCH_ENABLED",
        "THRESHOLD_SCENE",
    ),
}

IMDBID_APIKEY = env("IMDBID_APIKEY", default="")

ELASTICSEARCH_HOST = env("ELASTICSEARCH_HOST", default="")
ELASTICSEARCH_USER = env("ELASTICSEARCH_USER", default="")
ELASTICSEARCH_PWD = env("ELASTICSEARCH_PWD", default="")
ELASTICSEARCH_NUM_SHARDS = env.int("ELASTICSEARCH_NUM_SHARDS", default=1)
ELASTICSEARCH_NUM_REPLICAS = env.int("ELASTICSEARCH_NUM_REPLICAS", default=1)
ELASTICSEARCH_VERIFY_CERTS = env.bool("ELASTICSEARCH_VERIFY_CERTS", default=False)
# "byte" stores text/poster vectors as int8 (4x smaller, cosine indices only).
ELASTICSEARCH_VECTOR_ELEMENT_TYPE = env("ELASTICSEARCH_VECTOR_ELEMENT_TYPE", default="float")
# HNSW variant passed as index_options.type, e.g. "int8_hnsw" on Elasticsearch
# versions that support it (8.8 does not). Empty = Elasticsearch default.
ELASTICSEARCH_VECTOR_INDEX_TYPE = env("ELASTICSEARCH_VECTOR_INDEX_TYPE", default="")

# Text model for the movie vectors: use-large | minilm | minilm-multilingual
# (see apps/document/embeddings.py). Changing it requires `rebuild_indices movies --reembed`.
TEXT_EMBEDDING_MODEL = env("TEXT_EMBEDDING_MODEL", default="use-large")
# Extra indices written by the movie Elasticsearch job (they load extra models in the worker).
INDEX_MOVIE_PASSAGES = env.bool("INDEX_MOVIE_PASSAGES", default=False)
INDEX_MOVIE_POSTERS = env.bool("INDEX_MOVIE_POSTERS", default=False)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10240

BOT_TOKEN = env("BOT_TOKEN", default="")
BOT_USER_NAME = env("BOT_USER_NAME", default="")
BOT_URL = env("BOT_URL", default="")
# Optional secret sent by Telegram in the "X-Telegram-Bot-Api-Secret-Token" header.
BOT_SECRET_TOKEN = env("BOT_SECRET_TOKEN", default="")

# Load the sentence encoder when the app starts instead of on the first request.
# Off by default so migrate / celery beat / shell don't load TensorFlow.
PRELOAD_NLP_MODEL = env.bool("PRELOAD_NLP_MODEL", default=False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        # The Elasticsearch client logs every request at INFO.
        "elastic_transport": {"level": "WARNING"},
    },
}
