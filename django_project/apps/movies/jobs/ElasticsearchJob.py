from overrides import override
from apps.document.schema import Movies
from apps.movies.models import ElasticSearchMovie
from ms_data_mining.inteface import InterfaceJob


class ElasticsearchJob(InterfaceJob):
    JOB_MODEL = ElasticSearchMovie

    @override
    def internal_process(self, item_id: str) -> bool:
        obj_elasticsearch = self.JOB_MODEL.objects.select_related("movie").get(
            id=item_id
        )
        movie = obj_elasticsearch.movie

        # select_related avoids one extra query per actor.
        celebrities = [
            {"id": str(item.actor.id), "name": item.actor.name.strip()}
            for item in movie.movieactor_set.select_related("actor").all()
        ]

        description = f"{movie.description}." f"{movie.name}." f"{movie.director_name}"
        year = str(movie.year or "")

        data_dict = {
            "id": str(obj_elasticsearch.id),
            "title": movie.name,
            "year": int(year) if year.isnumeric() else 0,
            "imdb_id": str(movie.imdb_id),
            "description": description,
            "celebrities": celebrities,
        }

        # index() creates or replaces the document, so no exists() round trip is needed.
        Movies().insert_one(data_dict)

        return True
