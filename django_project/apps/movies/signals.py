from django.db.models.signals import post_delete
from django.dispatch import receiver
from apps.document.schema import Movies
from apps.movies.models import ElasticSearchMovie


@receiver(post_delete, sender=ElasticSearchMovie)
def movie_post_delete(sender, instance, **kwargs):
    # ElasticSearchMovie has no file on disk (unlike ElasticSearchActorImage),
    # so only the Elasticsearch document has to be removed.
    Movies().delete_by_document_id(str(instance.id))
