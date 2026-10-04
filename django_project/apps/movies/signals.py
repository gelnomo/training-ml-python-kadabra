from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.document.schema import MoviePassages, MoviePosters, Movies
from apps.movies.models import ElasticSearchMovie


@receiver(post_delete, sender=ElasticSearchMovie)
def movie_post_delete(sender, instance, **kwargs):
    # ElasticSearchMovie has no file on disk (unlike ElasticSearchActorImage),
    # so only the Elasticsearch documents have to be removed.
    document_id = str(instance.id)
    Movies().delete_by_document_id(document_id)
    if settings.INDEX_MOVIE_PASSAGES:
        MoviePassages().delete_movie(document_id)
    if settings.INDEX_MOVIE_POSTERS:
        MoviePosters().delete_by_document_id(document_id)
