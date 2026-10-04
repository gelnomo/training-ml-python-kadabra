"""
Build a new version of a search index and switch its alias to it atomically.

Examples:
    # First migration from the old indices (faces were brute force, movies used l2_norm):
    python manage.py rebuild_indices faces  --source celebrity
    python manage.py rebuild_indices movies --source movies_search

    # After changing TEXT_EMBEDDING_MODEL or ELASTICSEARCH_VECTOR_ELEMENT_TYPE:
    python manage.py rebuild_indices movies --reembed

    # Optional indices:
    python manage.py rebuild_indices passages
    python manage.py rebuild_indices posters
"""
import logging

from django.core.management.base import BaseCommand, CommandError

from apps.document.ranking import chunk_text
from apps.document.schema import (
    EMBED_BATCH_SIZE,
    INDEX_CLASSES,
    Movies,
    to_byte_vector,
)

logger = logging.getLogger(__name__)

MOVIE_FIELDS = ["title", "year", "imdb_id", "description", "celebrities"]


class Command(BaseCommand):
    help = "Rebuild a search index (new mapping/model) and switch its alias with no downtime."

    def add_arguments(self, parser):
        parser.add_argument("index", choices=sorted(INDEX_CLASSES))
        parser.add_argument(
            "--source",
            help="Index or alias to copy from (default: the current alias). "
            "Use `celebrity` / `movies_search` to migrate the old indices.",
        )
        parser.add_argument(
            "--reembed",
            action="store_true",
            help="movies: re-encode every description with the configured text model.",
        )
        parser.add_argument(
            "--keep-old",
            action="store_true",
            help="Don't delete the indices the alias pointed to before.",
        )

    def handle(self, *args, **options):
        index_class = INDEX_CLASSES[options["index"]]
        target = index_class()
        new_index = target.new_index_name()
        target.create_index(new_index)

        try:
            builder = getattr(self, f"build_{options['index']}")
            count = builder(target, new_index, options)
        except Exception:
            target.es.indices.delete(index=new_index, ignore_unavailable=True)
            raise

        target.es.indices.refresh(index=new_index)
        old = target.switch_alias(new_index)
        self.stdout.write(
            self.style.SUCCESS(f"{target.ALIAS} -> {new_index} ({count} documents)")
        )

        if old and not options["keep_old"]:
            target.es.indices.delete(index=",".join(old))
            self.stdout.write(f"Deleted previous indices: {', '.join(old)}")

    # ---- per index -------------------------------------------------------------------
    @staticmethod
    def _source_index(target, options):
        source = options.get("source") or target.ALIAS
        if not target.es.indices.exists(index=source):
            raise CommandError(f"Source index {source!r} does not exist")
        return source

    def build_faces(self, target, new_index, options):
        source = self._source_index(target, options)

        def actions():
            for hit in target.scan(index=source):
                document = target.to_document({**hit["_source"], "id": hit["_id"]})
                yield {"_index": new_index, "_id": hit["_id"], **document}

        count, _ = target.bulk(actions())
        return count

    @staticmethod
    def _source_meta(target, source):
        mapping = target.es.indices.get_mapping(index=source)
        first = next(iter(mapping.values()))
        return first["mappings"].get("_meta", {})

    def build_movies(self, target, new_index, options):
        source = self._source_index(target, options)
        meta = self._source_meta(target, source)
        same_model = meta.get("text_model", "use-large") == target.encoder.key
        source_is_float = meta.get("element_type", "float") == "float"
        reembed = options["reembed"] or not same_model or not source_is_float
        if reembed:
            self.stdout.write(f"Re-encoding descriptions with {target.encoder.key!r}...")

        rows, vectors = [], []
        for hit in target.scan(index=source, source=MOVIE_FIELDS + ["description_vector"]):
            doc = hit["_source"]
            rows.append({"id": hit["_id"], **{field: doc.get(field) for field in MOVIE_FIELDS}})
            if not reembed:
                vector = doc["description_vector"]
                vectors.append(to_byte_vector(vector) if target.element_type() == "byte" else vector)

        count, _ = target.bulk(
            target.iter_bulk_actions(rows, index=new_index, vectors=None if reembed else vectors)
        )
        return count

    def build_passages(self, target, new_index, options):
        movies = Movies(es=target.es, encoder=target.encoder)
        source = options.get("source") or movies.ALIAS
        if not target.es.indices.exists(index=source):
            raise CommandError(f"Source index {source!r} does not exist")

        def actions():
            batch = []
            for hit in target.scan(index=source, source=MOVIE_FIELDS):
                row = {"id": hit["_id"], **{f: hit["_source"].get(f) for f in MOVIE_FIELDS}}
                batch.append((row, chunk_text(row["description"])))
                if sum(len(p) for _, p in batch) >= EMBED_BATCH_SIZE:
                    yield from self._passage_actions(target, batch, new_index)
                    batch = []
            yield from self._passage_actions(target, batch, new_index)

        count, _ = target.bulk(actions())
        return count

    @staticmethod
    def _passage_actions(target, batch, new_index):
        texts = [passage for _, passages in batch for passage in passages]
        vectors = iter(target.encode(texts))
        for row, passages in batch:
            row_vectors = [next(vectors) for _ in passages]
            yield from target.iter_movie_actions(row, passages, row_vectors, index=new_index)

    def build_posters(self, target, new_index, options):
        from apps.movies.jobs.ElasticsearchJob import movie_row
        from apps.movies.jobs.posters import index_poster
        from apps.movies.models import ElasticSearchMovie

        count = 0
        queryset = ElasticSearchMovie.objects.select_related("movie").iterator()
        for obj in queryset:
            try:
                if index_poster(movie_row(obj), obj.movie, posters=target, index=new_index):
                    count += 1
            except Exception as ex:
                logger.warning("Poster of %s skipped: %s", obj.movie.imdb_id, ex)
        return count
