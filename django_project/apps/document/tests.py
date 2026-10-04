import json
import os
import tempfile
import unittest
from io import StringIO
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from apps.document import ranking
from apps.document.schema import (
    Faces,
    MoviePassages,
    Movies,
    VectorIndex,
    elastic_connection,
    to_byte_vector,
)


class FakeEncoder:
    """Deterministic 4-d 'text model': one dimension per keyword."""

    key = "use-large"
    dims = 4
    KEYWORDS = ["space", "love", "war", "heist"]

    def encode(self, texts):
        vectors = []
        for text in texts:
            text = (text or "").lower()
            vector = [float(text.count(word)) for word in self.KEYWORDS]
            vectors.append(vector if any(vector) else [0.1, 0.1, 0.1, 0.1])
        return vectors


def hit(actor_id, score, **source):
    return {"_id": f"doc-{actor_id}-{score}", "_score": score, "_source": {"actor_id": actor_id, "name": actor_id, **source}}


class RankingTests(SimpleTestCase):
    def test_l2_score_matches_face_recognition_tolerance(self):
        self.assertAlmostEqual(ranking.l2_score(0.6), 1 / 1.36)
        self.assertAlmostEqual(ranking.l2_distance(ranking.l2_score(0.42)), 0.42)
        self.assertEqual(ranking.DEFAULT_FACE_THRESHOLD, 0.735)

    def test_cosine_score_round_trip(self):
        self.assertEqual(ranking.cosine_score(0.2), 0.6)
        self.assertAlmostEqual(ranking.score_to_cosine(ranking.cosine_score(-0.3)), -0.3)

    def test_vote_adds_up_the_neighbours_of_each_actor(self):
        hits = [hit("x", 0.95), hit("y", 0.80), hit("y", 0.78), hit("x", 0.50)]
        winner = ranking.vote_actor(hits, threshold=0.735)
        self.assertEqual(winner["actor_id"], "y")
        self.assertEqual(winner["votes"], 2)
        self.assertEqual(winner["score"], 0.80)

    def test_vote_is_weighted_by_score(self):
        hits = [hit("x", 0.90), hit("y", 0.80)]
        self.assertEqual(ranking.vote_actor(hits, 0.735)["actor_id"], "x")
        # One near-identical face beats two distant ones (no threshold, as in evaluation).
        hits = [hit("x", 1.0), hit("y", 0.16), hit("y", 0.16)]
        self.assertEqual(ranking.vote_actor(hits, 0.0)["actor_id"], "x")

    def test_vote_threshold_and_min_votes(self):
        hits = [hit("x", 0.90), hit("y", 0.80), hit("y", 0.78)]
        self.assertIsNone(ranking.vote_actor(hits, threshold=0.95))
        self.assertEqual(ranking.vote_actor(hits, 0.735, min_votes=2)["actor_id"], "y")
        self.assertIsNone(ranking.vote_actor(hits, 0.735, min_votes=3))
        self.assertIsNone(ranking.vote_actor([], 0.0))

    def test_rrf_fuse(self):
        self.assertEqual(ranking.rrf_fuse([["a", "b", "c"], ["c", "a"]]), ["a", "c", "b"])
        self.assertEqual(ranking.rrf_fuse([["a", "b"], []]), ["a", "b"])

    def test_chunk_text(self):
        text = " ".join(str(i) for i in range(10))
        self.assertEqual(ranking.chunk_text(text, 4, 1), ["0 1 2 3", "3 4 5 6", "6 7 8 9"])
        self.assertEqual(ranking.chunk_text("short text", 4, 1), ["short text"])
        self.assertEqual(ranking.chunk_text("", 4, 1), [])
        with self.assertRaises(ValueError):
            ranking.chunk_text(text, 4, 4)

    def test_best_hit_per_key(self):
        hits = [
            {"_source": {"m": "a"}, "_score": 0.9},
            {"_source": {"m": "a"}, "_score": 0.8},
            {"_source": {"m": "b"}, "_score": 0.7},
            {"_source": {"m": "c"}, "_score": 0.6},
        ]
        self.assertEqual([h["_score"] for h in ranking.best_hit_per_key(hits, "m", 2)], [0.9, 0.7])

    def test_pick_threshold(self):
        scored = [(0.9, True), (0.8, True), (0.7, False), (0.6, True), (0.5, False)]
        threshold, table = ranking.pick_threshold(scored)
        self.assertEqual(threshold, 0.6)
        row = next(r for r in table if r["threshold"] == 0.6)
        self.assertEqual((row["answered"], row["correct"]), (4, 3))


class QuantizeTests(SimpleTestCase):
    def test_to_byte_vector_normalises_and_scales(self):
        self.assertEqual(to_byte_vector([3.0, 4.0]), [76, 102])
        self.assertEqual(to_byte_vector([0.0, 0.0]), [0, 0])
        self.assertEqual(to_byte_vector([-1.0, 0.0]), [-127, 0])

    @override_settings(ELASTICSEARCH_VECTOR_ELEMENT_TYPE="byte")
    def test_byte_fields_only_for_cosine_indices(self):
        movies = Movies(es=mock.Mock(), encoder=FakeEncoder())
        self.assertEqual(movies.properties()["description_vector"]["element_type"], "byte")
        self.assertEqual(movies.encode_one("space"), [127, 0, 0, 0])
        faces = Faces(es=mock.Mock())
        self.assertNotIn("element_type", faces.properties()["face_encoding"])

    @override_settings(ELASTICSEARCH_VECTOR_INDEX_TYPE="int8_hnsw")
    def test_index_options(self):
        field = Faces(es=mock.Mock()).properties()["face_encoding"]
        self.assertEqual(field["index_options"], {"type": "int8_hnsw"})
        self.assertTrue(field["index"])
        self.assertEqual(field["similarity"], "l2_norm")


class QueryBuildingTests(SimpleTestCase):
    def setUp(self):
        self.es = mock.MagicMock()
        self.es.search.return_value = {"hits": {"hits": []}}
        patcher = mock.patch.object(VectorIndex, "ensure", lambda self: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_movies_knn_filters_by_actor_ids(self):
        Movies(es=self.es, encoder=FakeEncoder()).knn_search([1, 0, 0, 0], k=3, actor_ids=["a1", "a2"])
        knn = self.es.search.call_args.kwargs["knn"]
        self.assertEqual(knn["field"], "description_vector")
        self.assertEqual(knn["k"], 3)
        self.assertEqual(knn["filter"], {"terms": {"actor_ids": ["a1", "a2"]}})
        self.assertNotIn("query", self.es.search.call_args.kwargs)

    def test_movies_knn_without_actors_has_no_filter(self):
        Movies(es=self.es, encoder=FakeEncoder()).knn_search([1, 0, 0, 0], k=3)
        self.assertNotIn("filter", self.es.search.call_args.kwargs["knn"])

    def test_search_by_actors_filters_and_boosts_year(self):
        Movies(es=self.es, encoder=FakeEncoder()).search_by_actors(["a1"], 3, year_hints=[2001], year_window=5)
        query = self.es.search.call_args.kwargs["query"]["bool"]
        self.assertEqual(query["filter"], [{"terms": {"actor_ids": ["a1"]}}])
        year = query["should"][1]["constant_score"]["filter"]["range"]["year"]
        self.assertEqual((year["gte"], year["lte"]), (1996, 2006))

    def test_query_face_uses_one_msearch_with_knn(self):
        self.es.msearch.return_value = {"responses": [{"hits": {"hits": ["h1"]}}, {"error": "boom"}]}
        result = Faces(es=self.es).query_face([[0.1] * 128, [0.2] * 128], k=10, num_candidates=50, exclude_ids=["x"])
        self.assertEqual(result, [["h1"], []])
        searches = self.es.msearch.call_args.kwargs["searches"]
        self.assertEqual(len(searches), 4)
        body = searches[1]
        self.assertEqual(body["knn"]["k"], 10)
        self.assertEqual(body["knn"]["num_candidates"], 50)
        self.assertEqual(body["knn"]["filter"], {"bool": {"must_not": {"ids": {"values": ["x"]}}}})

    def test_text_model_mismatch_is_reported(self):
        movies = Movies(es=self.es, encoder=FakeEncoder())
        with self.assertRaises(ImproperlyConfigured):
            movies.check_compatible({"text_model": "minilm", "element_type": "float"})
        movies.check_compatible({"text_model": "use-large", "element_type": "float"})
        # Indices created before _meta existed were built with USE-large floats.
        movies.check_compatible({})


ES_HOST = os.environ.get("ELASTICSEARCH_TEST_HOST")


class TestFaces(Faces):
    ALIAS = "test_kadabra_faces"


class TestMovies(Movies):
    ALIAS = "test_kadabra_movies"


class TestPassages(MoviePassages):
    ALIAS = "test_kadabra_movie_passages"


@unittest.skipUnless(ES_HOST, "set ELASTICSEARCH_TEST_HOST to run Elasticsearch tests")
@override_settings(ELASTICSEARCH_HOST=ES_HOST or "", ELASTICSEARCH_NUM_REPLICAS=0)
class ElasticsearchIntegrationTests(SimpleTestCase):
    """Runs against a real Elasticsearch (e.g. the docker-compose one)."""

    def setUp(self):
        self.es = elastic_connection()
        self.cleanup()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        # Elasticsearch 8 refuses wildcard deletes, so resolve the names first.
        names = list(self.es.indices.get(index="test_kadabra_*,test_legacy_*", allow_no_indices=True))
        if names:
            self.es.indices.delete(index=",".join(names))
        VectorIndex._ensured.clear()

    @staticmethod
    def face(base, noise):
        return [base + noise * ((i % 3) - 1) for i in range(128)]

    def index_faces(self, faces):
        for doc_id, actor, vector in [
            ("a1", "alice", self.face(0.10, 0.000)),
            ("a2", "alice", self.face(0.10, 0.010)),
            ("a3", "alice", self.face(0.10, 0.015)),
            ("b1", "bob", self.face(0.10, 0.060)),
            ("c1", "carol", self.face(-0.10, 0.0)),
            ("c2", "carol", self.face(-0.10, 0.01)),
        ]:
            faces.insert_one({"id": doc_id, "name": actor, "image_id": doc_id, "actor_id": actor, "face_encoding": vector})
        self.es.indices.refresh(index=faces.ALIAS)

    def test_face_knn_vote(self):
        faces = TestFaces(es=self.es)
        self.index_faces(faces)
        mapping = faces.get_mapping()
        field = next(iter(mapping.values()))["mappings"]["properties"]["face_encoding"]
        self.assertTrue(field["index"])
        self.assertEqual(field["similarity"], "l2_norm")

        [hits] = faces.query_face([self.face(0.10, 0.005)], k=10, num_candidates=50)
        winner = ranking.vote_actor(hits, ranking.DEFAULT_FACE_THRESHOLD)
        self.assertEqual(winner["actor_id"], "alice")
        self.assertEqual(winner["votes"], 3)

        # A face far from everything is not recognised.
        [hits] = faces.query_face([[0.5] * 128], k=10, num_candidates=50)
        self.assertIsNone(ranking.vote_actor(hits, ranking.DEFAULT_FACE_THRESHOLD))

    def test_movie_search_filter_and_fallback(self):
        movies = TestMovies(es=self.es, encoder=FakeEncoder())
        movies.insert_many(
            [
                {"id": "m1", "title": "Space Love", "year": 2001, "imdb_id": "tt1", "description": "space love space",
                 "celebrities": [{"id": "alice", "name": "Alice"}]},
                {"id": "m2", "title": "Space War", "year": 1990, "imdb_id": "tt2", "description": "space war",
                 "celebrities": [{"id": "bob", "name": "Bob"}]},
                {"id": "m3", "title": "Heist", "year": 2010, "imdb_id": "tt3", "description": "heist heist",
                 "celebrities": [{"id": "alice", "name": "Alice"}, {"id": "bob", "name": "Bob"}]},
            ]
        )
        self.es.indices.refresh(index=movies.ALIAS)
        vector = movies.encode_one("space")

        unfiltered = [h["_id"] for h in movies.knn_search(vector, 3)]
        self.assertEqual(unfiltered[:2], ["m1", "m2"] if unfiltered[0] == "m1" else ["m2", "m1"])
        filtered = [h["_id"] for h in movies.knn_search(vector, 3, actor_ids=["bob"])]
        self.assertEqual(filtered[0], "m2")
        self.assertNotIn("m1", filtered)

        by_actor = movies.search_by_actors(["alice", "bob"], 3)
        self.assertEqual(by_actor[0]["_id"], "m3")  # both actors -> highest score

        self.assertEqual(movies.bm25_rank("heist", ["m1", "m3"]), ["m3"])
        listing = movies.query_movie_listing(size=10)
        self.assertEqual([h["_source"]["title"] for h in listing["hits"]["hits"]], ["Heist", "Space Love", "Space War"])

    def test_passages_best_per_movie(self):
        passages = TestPassages(es=self.es, encoder=FakeEncoder())
        row = {"id": "m1", "title": "Mixed", "year": 2000, "imdb_id": "tt1", "celebrities": [{"id": "alice"}]}
        passages.replace_movie(row, ["love love", "space space", "war"])
        passages.replace_movie(row, ["love love", "space space"])  # replaces, doesn't duplicate
        self.es.indices.refresh(index=passages.ALIAS)
        self.assertEqual(self.es.count(index=passages.ALIAS)["count"], 2)
        hits = passages.knn_search(passages.encode_one("space"), k=3)
        self.assertEqual([h["_id"] for h in hits], ["m1"])
        passages.delete_movie("m1")
        self.assertEqual(self.es.count(index=passages.ALIAS)["count"], 0)

    def test_rebuild_faces_from_legacy_index_and_evaluate(self):
        # Old mapping: dense_vector without index/similarity (brute force only).
        self.es.indices.create(
            index="test_legacy_celebrity",
            mappings={"properties": {"face_encoding": {"type": "dense_vector", "dims": 128},
                                     "actor_id": {"type": "keyword"}, "name": {"type": "keyword"},
                                     "image_id": {"type": "keyword"}}},
        )
        for doc_id, actor, base in [("a1", "alice", 0.1), ("a2", "alice", 0.1001), ("b1", "bob", -0.1), ("b2", "bob", -0.1001)]:
            self.es.index(index="test_legacy_celebrity", id=doc_id,
                          document={"face_encoding": [base] * 128, "actor_id": actor, "name": actor, "image_id": doc_id})
        self.es.indices.refresh(index="test_legacy_celebrity")

        with mock.patch.dict("apps.document.schema.INDEX_CLASSES", {"faces": TestFaces}):
            out = StringIO()
            call_command("rebuild_indices", "faces", "--source", "test_legacy_celebrity", stdout=out)
            self.assertIn("4 documents", out.getvalue())
            first = TestFaces(es=self.es).concrete_indices()
            call_command("rebuild_indices", "faces", stdout=StringIO())  # second rebuild from the alias
            second = TestFaces(es=self.es).concrete_indices()
        self.assertNotEqual(first, second)
        self.assertFalse(self.es.indices.exists(index=first[0]))  # old version deleted
        self.assertTrue(self.es.indices.exists(index="test_legacy_celebrity"))  # legacy kept
        self.assertEqual(self.es.count(index=TestFaces.ALIAS)["count"], 4)

        with mock.patch("apps.document.management.commands.evaluate_search.Faces", TestFaces), \
                tempfile.NamedTemporaryFile(suffix=".json") as report_file:
            out = StringIO()
            call_command("evaluate_search", "--faces", "4", "--output", report_file.name, stdout=out)
            report = json.load(open(report_file.name))
        self.assertEqual(report["faces"]["queries"], 4)
        self.assertEqual(report["faces"]["accuracy_no_threshold"], 1.0)

    def test_rebuild_movies_reuses_or_reencodes_vectors(self):
        movies = TestMovies(es=self.es, encoder=FakeEncoder())
        movies.insert_one({"id": "m1", "title": "Space", "year": 2000, "imdb_id": "tt1",
                           "description": "space", "celebrities": [{"id": "alice", "name": "A"}]})
        self.es.indices.refresh(index=movies.ALIAS)
        with mock.patch.dict("apps.document.schema.INDEX_CLASSES", {"movies": TestMovies}), \
                mock.patch("apps.document.schema.get_text_encoder", FakeEncoder), \
                override_settings(ELASTICSEARCH_VECTOR_ELEMENT_TYPE="byte"):
            VectorIndex._ensured.clear()
            call_command("rebuild_indices", "movies", stdout=StringIO())
            doc = self.es.get(index=TestMovies.ALIAS, id="m1")["_source"]
            self.assertEqual(doc["description_vector"], [127, 0, 0, 0])  # float vector quantised
            self.assertEqual(doc["actor_ids"], ["alice"])
            hits = TestMovies(es=self.es, encoder=FakeEncoder()).knn_search([127, 0, 0, 0], 1)
            self.assertEqual(hits[0]["_id"], "m1")
