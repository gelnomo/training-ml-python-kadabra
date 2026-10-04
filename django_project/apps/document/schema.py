"""
Elasticsearch indices used by Kadabra.

Every index is reached through an **alias** (``kadabra_*``) that points to one
concrete, timestamped index (``kadabra_faces_20261004170000``). Changing a mapping
or a model is then: create a new index, copy or re-encode the documents, and
switch the alias atomically (see ``manage.py rebuild_indices``).

Vector search uses approximate kNN (HNSW): vectors are mapped with
``index: true`` and a ``similarity``, and queried with the ``knn`` search option.
"""
import logging
import math

from constance import config
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from elasticsearch import Elasticsearch, NotFoundError, helpers

from apps.document.embeddings import get_image_encoder, get_text_encoder

logger = logging.getLogger(__name__)

# Number of descriptions sent to the sentence encoder in a single call when bulk indexing.
EMBED_BATCH_SIZE = 64

# Bump when a mapping changes; stored in each index's _meta.
SCHEMA_VERSION = 2

# Indices created by the previous version of the code (no kNN index on faces).
LEGACY_INDICES = {"faces": "celebrity", "movies": "movies_search"}


def elastic_connection():
    return Elasticsearch(
        settings.ELASTICSEARCH_HOST,
        basic_auth=(settings.ELASTICSEARCH_USER, settings.ELASTICSEARCH_PWD),
        verify_certs=settings.ELASTICSEARCH_VERIFY_CERTS,
    )


def to_byte_vector(vector):
    """
    Quantise a vector to int8 for ``element_type: byte`` fields (4x smaller).

    Only used with ``similarity: cosine``, which ignores the vector length, so the
    vector is normalised first and scaled to [-127, 127].
    """
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [max(-128, min(127, round(x / norm * 127))) for x in vector]


class VectorIndex:
    """Base class: alias management, creation and common document helpers."""

    ALIAS = None
    # True when the vector field uses cosine similarity and may be stored as bytes.
    QUANTIZABLE = False
    _ensured = set()

    def __init__(self, es=None):
        self.es = es or elastic_connection()

    # ---- mapping -----------------------------------------------------------------
    def properties(self):
        raise NotImplementedError

    def meta(self):
        return {"schema_version": SCHEMA_VERSION}

    @classmethod
    def element_type(cls):
        if cls.QUANTIZABLE and settings.ELASTICSEARCH_VECTOR_ELEMENT_TYPE == "byte":
            return "byte"
        return "float"

    @classmethod
    def vector_field(cls, dims, similarity):
        field = {"type": "dense_vector", "dims": dims, "index": True, "similarity": similarity}
        if cls.element_type() == "byte":
            field["element_type"] = "byte"
        if settings.ELASTICSEARCH_VECTOR_INDEX_TYPE:
            # e.g. "int8_hnsw" on Elasticsearch versions that support it (not 8.8).
            field["index_options"] = {"type": settings.ELASTICSEARCH_VECTOR_INDEX_TYPE}
        return field

    def prepare_vector(self, vector):
        """Convert a model vector to what the field stores (and must be queried with)."""
        vector = list(vector)
        return to_byte_vector(vector) if self.element_type() == "byte" else vector

    # ---- index lifecycle ---------------------------------------------------------
    def new_index_name(self):
        return f"{self.ALIAS}_{timezone.now().strftime('%Y%m%d%H%M%S%f')}"

    def create_index(self, name):
        self.es.indices.create(
            index=name,
            settings={
                "number_of_shards": settings.ELASTICSEARCH_NUM_SHARDS,
                "number_of_replicas": settings.ELASTICSEARCH_NUM_REPLICAS,
            },
            mappings={"_meta": self.meta(), "properties": self.properties()},
        )
        logger.info("Created index %s", name)

    def concrete_indices(self):
        try:
            return sorted(self.es.indices.get_alias(name=self.ALIAS).keys())
        except NotFoundError:
            return []

    def switch_alias(self, new_index):
        """Point the alias to ``new_index`` in one atomic call. Returns the old indices."""
        old = self.concrete_indices()
        actions = [{"remove": {"index": index, "alias": self.ALIAS}} for index in old]
        actions.append({"add": {"index": new_index, "alias": self.ALIAS}})
        self.es.indices.update_aliases(actions=actions)
        VectorIndex._ensured.discard(self.ALIAS)
        logger.info("Alias %s -> %s (was %s)", self.ALIAS, new_index, old)
        return old

    def check_compatible(self, index_meta):
        """Raise when an existing index was built with different settings."""

    def ensure(self):
        """Create the index + alias on first use; checked once per process."""
        if self.ALIAS in VectorIndex._ensured:
            return
        indices = self.concrete_indices()
        if indices:
            mapping = self.es.indices.get_mapping(index=indices[0])
            self.check_compatible(mapping[indices[0]]["mappings"].get("_meta", {}))
        else:
            name = self.new_index_name()
            self.create_index(name)
            self.es.indices.put_alias(index=name, name=self.ALIAS)
            self._warn_legacy()
        VectorIndex._ensured.add(self.ALIAS)

    def _warn_legacy(self):
        for key, legacy in LEGACY_INDICES.items():
            if self.ALIAS == ALIASES.get(key) and self.es.indices.exists(index=legacy):
                logger.warning(
                    "Legacy index %r exists but %r was just created empty. "
                    "Run `manage.py rebuild_indices %s --source %s` to copy the data.",
                    legacy, self.ALIAS, key, legacy,
                )

    # ---- documents -----------------------------------------------------------------
    def delete_by_document_id(self, document_id):
        try:
            return self.es.delete(index=self.ALIAS, id=document_id)
        except NotFoundError:
            return None

    def get_by_document_id(self, document_id):
        return self.es.get(index=self.ALIAS, id=document_id)

    def check_by_document_id(self, document_id):
        return self.es.exists(index=self.ALIAS, id=document_id)

    def get_mapping(self):
        return self.es.indices.get_mapping(index=self.ALIAS)

    def bulk(self, actions):
        return helpers.bulk(self.es, actions)

    def scan(self, index=None, source=None):
        """Iterate over every document of ``index`` (default: the alias)."""
        return helpers.scan(
            self.es, index=index or self.ALIAS, query={"query": {"match_all": {}}}, _source=source
        )


class TextVectorIndex(VectorIndex):
    """An index whose vectors come from the configured text model."""

    QUANTIZABLE = True

    def __init__(self, es=None, encoder=None):
        super().__init__(es)
        self.encoder = encoder or get_text_encoder()

    def meta(self):
        return {**super().meta(), "text_model": self.encoder.key, "element_type": self.element_type()}

    def check_compatible(self, index_meta):
        model = index_meta.get("text_model", "use-large")
        element_type = index_meta.get("element_type", "float")
        if model != self.encoder.key or element_type != self.element_type():
            raise ImproperlyConfigured(
                f"Index alias {self.ALIAS!r} was built with text model {model!r} ({element_type}) but "
                f"TEXT_EMBEDDING_MODEL={self.encoder.key!r} ({self.element_type()}). "
                f"Run `manage.py rebuild_indices {self.KEY} --reembed`."
            )

    def encode(self, texts):
        return [self.prepare_vector(v) for v in self.encoder.encode(texts)]

    def encode_one(self, text):
        return self.encode([text])[0]


def _actor_ids(celebrities):
    return [str(c["id"]) for c in celebrities or []]


def _actor_filter(actor_ids):
    return {"terms": {"actor_ids": list(actor_ids)}} if actor_ids else None


def _knn(field, vector, k, num_candidates, filter_=None):
    knn = {"field": field, "query_vector": vector, "k": k, "num_candidates": max(num_candidates, k)}
    if filter_:
        knn["filter"] = filter_
    return knn


class Faces(VectorIndex):
    """One document per actor image (one face), 128-d dlib face encoding."""

    ALIAS = "kadabra_faces"
    KEY = "faces"
    SOURCE_FIELDS = ["name", "image_id", "actor_id", "age", "birthday", "year"]

    def properties(self):
        return {
            # face_recognition encodings are compared with Euclidean distance (tolerance 0.6),
            # so l2_norm keeps the model's own notion of similarity: score = 1 / (1 + d^2).
            "face_encoding": self.vector_field(128, "l2_norm"),
            "image_id": {"type": "keyword"},
            "actor_id": {"type": "keyword"},
            "name": {"type": "keyword"},
            "age": {"type": "integer"},
            "birthday": {"type": "date"},
            "year": {"type": "integer"},
        }

    @staticmethod
    def to_document(row):
        return {
            "name": row["name"],
            "image_id": row["image_id"],
            "actor_id": row["actor_id"],
            "face_encoding": list(row["face_encoding"]),
            "age": row.get("age"),
            "birthday": row.get("birthday"),
            "year": row.get("year"),
        }

    def insert_one(self, row):
        """Create or fully replace the document with id ``row["id"]``."""
        self.ensure()
        result = self.es.index(index=self.ALIAS, id=row["id"], document=self.to_document(row))
        logger.debug("Indexed face %s: %s", row["id"], result.get("result"))

    def query_face(self, face_encodings, k=None, num_candidates=None, exclude_ids=None):
        """
        Approximate kNN search, one search per face, sent in a single _msearch call.

        Returns one list of hits (best first) per input face.
        """
        self.ensure()
        k = k or config.FACE_KNN_K
        num_candidates = num_candidates or config.FACE_NUM_CANDIDATES
        filter_ = {"bool": {"must_not": {"ids": {"values": list(exclude_ids)}}}} if exclude_ids else None

        searches = []
        for encoding in face_encodings:
            vector = encoding.tolist() if hasattr(encoding, "tolist") else list(encoding)
            searches.append({"index": self.ALIAS})
            searches.append(
                {
                    "knn": _knn("face_encoding", vector, k, num_candidates, filter_),
                    "size": k,
                    "_source": self.SOURCE_FIELDS,
                }
            )
        if not searches:
            return []

        response = self.es.msearch(searches=searches)
        results = []
        for item in response["responses"]:
            if "error" in item:
                logger.error("Face search failed: %s", item["error"])
                results.append([])
            else:
                results.append(item["hits"]["hits"])
        return results


class Movies(TextVectorIndex):
    """One document per movie: metadata, actors and one description vector."""

    ALIAS = "kadabra_movies"
    KEY = "movies"
    SOURCE_FIELDS = ["title", "year", "imdb_id", "actor_ids"]

    def properties(self):
        return {
            "title": {"type": "keyword"},
            "year": {"type": "integer"},
            "imdb_id": {"type": "keyword"},
            "description": {"type": "text"},
            "celebrities": {
                "type": "nested",
                "properties": {"id": {"type": "keyword"}, "name": {"type": "text"}},
            },
            # Flat copy of celebrities.id: a cheap `terms` filter for kNN.
            "actor_ids": {"type": "keyword"},
            "description_vector": self.vector_field(self.encoder.dims, "cosine"),
        }

    @staticmethod
    def to_document(row, vector):
        return {
            "title": row["title"],
            "year": row["year"],
            "imdb_id": row["imdb_id"],
            "description": row["description"],
            "celebrities": row["celebrities"],
            "actor_ids": _actor_ids(row["celebrities"]),
            "description_vector": vector,
        }

    def insert_one(self, row, vector=None):
        """Create or fully replace the document with id ``row["id"]``."""
        self.ensure()
        vector = vector if vector is not None else self.encode_one(row["description"])
        result = self.es.index(index=self.ALIAS, id=row["id"], document=self.to_document(row, vector))
        logger.debug("Indexed movie %s: %s", row["id"], result.get("result"))

    def iter_bulk_actions(self, rows, index=None, vectors=None):
        """Yield bulk actions; descriptions are encoded in batches when vectors aren't given."""
        rows = list(rows)
        for start in range(0, len(rows), EMBED_BATCH_SIZE):
            batch = rows[start : start + EMBED_BATCH_SIZE]
            batch_vectors = (
                vectors[start : start + EMBED_BATCH_SIZE]
                if vectors is not None
                else self.encode([row["description"] for row in batch])
            )
            for row, vector in zip(batch, batch_vectors):
                yield {"_index": index or self.ALIAS, "_id": row["id"], **self.to_document(row, vector)}

    def insert_many(self, rows):
        self.ensure()
        return self.bulk(self.iter_bulk_actions(rows))

    def knn_search(self, vector, k, actor_ids=None, num_candidates=100):
        self.ensure()
        response = self.es.search(
            index=self.ALIAS,
            knn=_knn("description_vector", vector, k, num_candidates, _actor_filter(actor_ids)),
            size=k,
            _source=self.SOURCE_FIELDS,
        )
        return response["hits"]["hits"]

    def search_by_actors(self, actor_ids, size, year_hints=(), year_window=10):
        """
        Photo-only search: movies with at least one recognised actor.
        Score = number of recognised actors in the cast (+0.5 if the year looks right).
        """
        self.ensure()
        should = [
            {"constant_score": {"filter": {"term": {"actor_ids": actor_id}}, "boost": 1.0}}
            for actor_id in actor_ids
        ]
        for year in year_hints:
            should.append(
                {
                    "constant_score": {
                        "filter": {"range": {"year": {"gte": year - year_window, "lte": year + year_window}}},
                        "boost": 0.5,
                    }
                }
            )
        response = self.es.search(
            index=self.ALIAS,
            query={"bool": {"filter": [_actor_filter(actor_ids)], "should": should}},
            size=size,
            _source=self.SOURCE_FIELDS,
        )
        return response["hits"]["hits"]

    def bm25_rank(self, text, ids):
        """Rank the given movie ids by keyword (BM25) relevance of their description."""
        if not ids or not text:
            return []
        self.ensure()
        response = self.es.search(
            index=self.ALIAS,
            query={"bool": {"filter": [{"ids": {"values": list(ids)}}], "must": [{"match": {"description": text}}]}},
            size=len(ids),
            _source=False,
        )
        return [hit["_id"] for hit in response["hits"]["hits"]]

    def query_movie_listing(self, size=None):
        # Read the constance value at call time, not at import time, so admin changes apply.
        size = size if size is not None else config.SIZE_MOVIE_LISTING
        self.ensure()
        return self.es.search(
            index=self.ALIAS,
            query={"match_all": {}},
            size=size,
            sort=[{"title": {"order": "asc"}}],
            _source={"includes": ["title", "year", "imdb_id"]},
        )


class MoviePassages(TextVectorIndex):
    """
    Several vectors per movie: the description is split into overlapping passages
    (see ranking.chunk_text), one document per passage.
    """

    ALIAS = "kadabra_movie_passages"
    KEY = "passages"
    SOURCE_FIELDS = ["movie_doc_id", "title", "year", "imdb_id"]

    def properties(self):
        return {
            "movie_doc_id": {"type": "keyword"},
            "title": {"type": "keyword"},
            "year": {"type": "integer"},
            "imdb_id": {"type": "keyword"},
            "actor_ids": {"type": "keyword"},
            "passage": {"type": "text", "index": False},
            "passage_vector": self.vector_field(self.encoder.dims, "cosine"),
        }

    def iter_movie_actions(self, row, passages, vectors, index=None):
        for number, (passage, vector) in enumerate(zip(passages, vectors)):
            yield {
                "_index": index or self.ALIAS,
                "_id": f"{row['id']}_{number}",
                "movie_doc_id": row["id"],
                "title": row["title"],
                "year": row["year"],
                "imdb_id": row["imdb_id"],
                "actor_ids": _actor_ids(row["celebrities"]),
                "passage": passage,
                "passage_vector": vector,
            }

    def replace_movie(self, row, passages):
        """Delete the movie's old passages and index the new ones."""
        self.ensure()
        self.delete_movie(row["id"])
        vectors = self.encode(passages)
        return self.bulk(self.iter_movie_actions(row, passages, vectors))

    def delete_movie(self, movie_doc_id):
        self.ensure()
        # delete_by_query only sees refreshed documents; refresh so passages indexed
        # less than a second ago (e.g. a quick re-index of the same movie) are removed too.
        self.es.indices.refresh(index=self.ALIAS)
        self.es.delete_by_query(
            index=self.ALIAS,
            query={"term": {"movie_doc_id": movie_doc_id}},
            refresh=True,
            conflicts="proceed",
        )

    def knn_search(self, vector, k, actor_ids=None, num_candidates=200, passages_per_movie=5):
        """kNN over passages, then keep the best passage per movie."""
        self.ensure()
        size = k * passages_per_movie
        response = self.es.search(
            index=self.ALIAS,
            knn=_knn("passage_vector", vector, size, num_candidates, _actor_filter(actor_ids)),
            size=size,
            _source=self.SOURCE_FIELDS,
        )
        from apps.document.ranking import best_hit_per_key

        best = best_hit_per_key(response["hits"]["hits"], "movie_doc_id", k)
        # Present them like Movies hits (_id = movie document id).
        return [{**hit, "_id": hit["_source"]["movie_doc_id"]} for hit in best]


class MoviePosters(VectorIndex):
    """
    CLIP image vector of each movie poster, used to match photos of scenes when
    no actor face is recognised.
    """

    ALIAS = "kadabra_movie_posters"
    KEY = "posters"
    QUANTIZABLE = True
    SOURCE_FIELDS = ["title", "year", "imdb_id"]

    def __init__(self, es=None, encoder=None):
        super().__init__(es)
        self.encoder = encoder or get_image_encoder()

    def meta(self):
        return {**super().meta(), "image_model": self.encoder.model_name, "element_type": self.element_type()}

    def properties(self):
        return {
            "title": {"type": "keyword"},
            "year": {"type": "integer"},
            "imdb_id": {"type": "keyword"},
            "poster_url": {"type": "keyword", "index": False},
            "poster_vector": self.vector_field(self.encoder.dims, "cosine"),
        }

    def encode_images(self, images):
        return [self.prepare_vector(v) for v in self.encoder.encode_images(images)]

    def insert_one(self, row, vector, index=None):
        self.ensure()
        self.es.index(
            index=index or self.ALIAS,
            id=row["id"],
            document={
                "title": row["title"],
                "year": row["year"],
                "imdb_id": row["imdb_id"],
                "poster_url": row["poster_url"],
                "poster_vector": vector,
            },
        )

    def knn_search(self, vector, k, num_candidates=100):
        self.ensure()
        response = self.es.search(
            index=self.ALIAS,
            knn=_knn("poster_vector", vector, k, num_candidates),
            size=k,
            _source=self.SOURCE_FIELDS,
        )
        return response["hits"]["hits"]


INDEX_CLASSES = {cls.KEY: cls for cls in (Faces, Movies, MoviePassages, MoviePosters)}
ALIASES = {key: cls.ALIAS for key, cls in INDEX_CLASSES.items()}
