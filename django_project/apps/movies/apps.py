from django.apps import AppConfig


class MoviesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.movies"

    def ready(self):
        import apps.movies.signals  # noqa: F401
