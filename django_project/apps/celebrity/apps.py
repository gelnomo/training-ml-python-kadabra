from django.apps import AppConfig
from django.conf import settings


class CelebrityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.celebrity"

    def ready(self):
        import apps.celebrity.signals  # noqa: F401

        if getattr(settings, "PRELOAD_NLP_MODEL", False):
            from apps.document.embeddings import get_text_encoder

            get_text_encoder().warm_up()
