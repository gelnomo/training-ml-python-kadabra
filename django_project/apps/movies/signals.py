from django.db.models.signals import post_delete
from django.dispatch import receiver
import os
from apps.document.schema import Movies
from apps.movies.models import ElasticSearchMovie


def delete_index_movie(elastic_image):
    try:
        Movies().delete_by_document_id(str(elastic_image.id))
        if os.path.exists(elastic_image.actor_image.path):
            os.remove(elastic_image.actor_image.path)
    except ElasticSearchMovie.DoesNotExist:
        pass


@receiver(post_delete, sender=ElasticSearchMovie)
def movie_post_delete(sender, instance, **kwargs):
    delete_index_movie(instance)
