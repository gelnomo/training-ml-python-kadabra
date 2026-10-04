import logging

from django.conf import settings
from overrides import override

from apps.document.ranking import chunk_text
from apps.document.schema import MoviePassages, Movies
from apps.movies.models import ElasticSearchMovie
from ms_data_mining.inteface import InterfaceJob

logger = logging.getLogger(__name__)


def movie_row(obj_elasticsearch):
    """The Elasticsearch representation of an ElasticSearchMovie row."""
    movie = obj_elasticsearch.movie

    # select_related avoids one extra query per actor.
    celebrities = [
        {"id": str(item.actor.id), "name": item.actor.name.strip()}
        for item in movie.movieactor_set.select_related("actor").all()
    ]

    description = f"{movie.description}." f"{movie.name}." f"{movie.director_name}"
    year = str(movie.year or "")

    return {
        "id": str(obj_elasticsearch.id),
        "title": movie.name,
        "year": int(year) if year.isnumeric() else 0,
        "imdb_id": str(movie.imdb_id),
        "description": description,
        "celebrities": celebrities,
    }


class ElasticsearchJob(InterfaceJob):
    JOB_MODEL = ElasticSearchMovie

    @override
    def internal_process(self, item_id: str) -> bool:
        obj_elasticsearch = self.JOB_MODEL.objects.select_related("movie").get(
            id=item_id
        )
        row = movie_row(obj_elasticsearch)

        # index() creates or replaces the document, so no exists() round trip is needed.
        Movies().insert_one(row)

        if settings.INDEX_MOVIE_PASSAGES:
            MoviePassages().replace_movie(row, chunk_text(row["description"]))

        if settings.INDEX_MOVIE_POSTERS:
            from apps.movies.jobs.posters import index_poster

            try:
                index_poster(row, obj_elasticsearch.movie)
            except Exception:
                # The poster is optional: don't fail the movie because of it.
                logger.exception("Poster indexing failed for %s", row["imdb_id"])

        return True
