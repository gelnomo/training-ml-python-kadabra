from overrides import override
from apps.document.schema import Movies
from apps.movies.models import ElasticSearchMovie
from ms_data_mining.inteface import InterfaceJob


class ElasticsearchJob(InterfaceJob):
    JOB_MODEL = ElasticSearchMovie

    @override
    def internal_process(self, item_id: str) -> bool:
        obj_elasticsearch = self.JOB_MODEL.objects.get(id=item_id)
        movies = Movies()

        celebrities = [{"id": str(item.actor.id), "name": item.actor.name.strip()} for item in
                       obj_elasticsearch.movie.movieactor_set.all()]

        data_dict = {
            "id": str(obj_elasticsearch.id),
            "title": obj_elasticsearch.movie.name,
            "year": str(obj_elasticsearch.movie.year),
            "imdb_id": str(obj_elasticsearch.movie.imdb_id),
            "description": obj_elasticsearch.movie.description,
            "celebrities": celebrities
        }

        if movies.check_by_document_id(item_id):
            movies.update_one(data_dict)
        else:
            movies.insert_one(data_dict)

        return True
