from unittest import mock

from constance.test import override_config
from django.test import SimpleTestCase

from apps.botAI import bot_core
from apps.botAI.search_image import SearchImage
from apps.botAI.search_text import SearchText, format_results


def movie_hit(doc_id, score, title=None, year=2000, imdb_id=None):
    return {
        "_id": doc_id,
        "_score": score,
        "_source": {"title": title or doc_id, "year": year, "imdb_id": imdb_id or f"tt{doc_id}"},
    }


ALICE = {"id": "alice", "name": "Alice", "year": 2001}


@override_config(THRESHOLD_TEXT=0.6, K_TEXT=3, TEXT_SEARCH_MODE="vector", TEXT_PREPROCESS=False, THRESHOLD_YEAR=10)
class SearchTextTests(SimpleTestCase):
    def setUp(self):
        self.movies = mock.MagicMock()
        self.movies.encode_one.return_value = [1.0, 0.0]
        for target in ("Movies", "MoviePassages"):
            patcher = mock.patch(f"apps.botAI.search_text.{target}", return_value=self.movies)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_text_only_uses_unfiltered_knn_and_threshold(self):
        self.movies.knn_search.return_value = [movie_hit("a", 0.9), movie_hit("b", 0.5)]
        results = SearchText("a ship sinks", []).search()
        self.movies.knn_search.assert_called_once_with([1.0, 0.0], 3)
        self.assertEqual([r["doc_id"] for r in results], ["a"])

    def test_text_and_actors_filters_by_actor(self):
        self.movies.knn_search.return_value = [movie_hit("a", 0.9)]
        SearchText("a ship sinks", [ALICE]).search()
        self.movies.knn_search.assert_called_once_with([1.0, 0.0], 3, ["alice"])

    def test_falls_back_to_text_only_when_the_actor_filter_finds_nothing(self):
        self.movies.knn_search.side_effect = [[movie_hit("x", 0.3)], [movie_hit("a", 0.9)]]
        results = SearchText("a ship sinks", [ALICE]).search()
        self.assertEqual([r["doc_id"] for r in results], ["a"])
        self.assertEqual(self.movies.knn_search.call_args_list[1], mock.call([1.0, 0.0], 3))

    def test_actors_only_searches_by_actor_with_year_hint(self):
        self.movies.search_by_actors.return_value = [movie_hit("a", 1.5)]
        results = SearchText(None, [ALICE, {"id": "bob", "name": "Bob", "year": None}]).search()
        self.movies.search_by_actors.assert_called_once_with(["alice", "bob"], 3, [2001], 10)
        self.movies.knn_search.assert_not_called()
        self.assertEqual(results[0]["score"], 1.5)  # no text threshold on actor-only search

    def test_nothing_to_search(self):
        self.assertEqual(SearchText(None, []).search(), [])
        self.assertIsNone(SearchText(None, []).process())

    @override_config(TEXT_SEARCH_MODE="hybrid")
    def test_hybrid_reranks_vector_candidates_with_bm25(self):
        self.movies.knn_search.return_value = [movie_hit("a", 0.9), movie_hit("b", 0.85), movie_hit("c", 0.8)]
        self.movies.bm25_rank.return_value = ["c", "b"]
        results = SearchText("heist", [], k=2).search()
        # 10 = k * HYBRID_CANDIDATES_FACTOR vector candidates
        self.movies.knn_search.assert_called_once_with([1.0, 0.0], 10)
        self.movies.bm25_rank.assert_called_once_with("heist", ["a", "b", "c"])
        # RRF: b = 1/62 + 1/62, a = 1/61, c = 1/63 + 1/61
        self.assertEqual([r["doc_id"] for r in results], ["c", "b"])

    @override_config(TEXT_SEARCH_MODE="passages")
    def test_passages_mode_uses_the_passage_index(self):
        self.movies.knn_search.return_value = [movie_hit("a", 0.9)]
        with mock.patch("apps.botAI.search_text.MoviePassages", return_value=self.movies) as passages:
            SearchText("heist", []).search()
        passages.assert_called_once()

    def test_format_results_escapes_html(self):
        text = format_results([{"title": "Fast & <Furious>", "year": 2001, "imdb_id": "tt0232500"}], [{"name": "Vin <D>"}])
        self.assertIn("Vin &lt;D&gt;", text)
        self.assertIn("<b>Fast &amp; &lt;Furious&gt;</b>", text)
        self.assertIn("https://www.imdb.com/title/tt0232500", text)
        self.assertIsNone(format_results([]))


def face_hit(actor_id, score):
    return {"_id": f"{actor_id}-{score}", "_score": score,
            "_source": {"actor_id": actor_id, "name": f" {actor_id.title()} ", "year": 2001}}


@override_config(THRESHOLD_IMAGE=0.735, FACE_MIN_VOTES=1, FACE_KNN_K=10)
class SearchImageTests(SimpleTestCase):
    def test_one_actor_per_face_without_duplicates(self):
        query_results = [
            [face_hit("alice", 0.9), face_hit("alice", 0.8), face_hit("bob", 0.85)],
            [face_hit("bob", 0.95), face_hit("bob", 0.9)],
            [face_hit("alice", 0.8)],  # same actor again -> not repeated
            [face_hit("carol", 0.5)],  # below the threshold -> not recognised
        ]
        with mock.patch.object(SearchImage, "face_encodings", return_value=[1, 2, 3, 4]), \
                mock.patch("apps.botAI.search_image.Faces") as faces:
            faces.return_value.query_face.return_value = query_results
            celebrities = SearchImage(image=None).process()

        faces.return_value.query_face.assert_called_once_with([1, 2, 3, 4], k=10)
        self.assertEqual([c["id"] for c in celebrities], ["alice", "bob"])
        self.assertEqual(celebrities[0]["name"], "Alice")
        self.assertEqual(celebrities[0]["votes"], 2)

    def test_no_face(self):
        with mock.patch.object(SearchImage, "face_encodings", return_value=[]), \
                mock.patch("apps.botAI.search_image.Faces") as faces:
            self.assertEqual(SearchImage(image=None).process(), [])
        faces.assert_not_called()


class UpdateDedupeTests(SimpleTestCase):
    def test_first_time_only(self):
        redis = mock.MagicMock()
        redis.set.side_effect = [True, None]
        with mock.patch.object(bot_core.rd, "__init__", lambda self: setattr(self, "r", redis)):
            self.assertTrue(bot_core.is_new_update(7))
            self.assertFalse(bot_core.is_new_update(7))
        redis.set.assert_called_with("telegram-update-7", 1, nx=True, ex=bot_core.UPDATE_DEDUPE_SECONDS)

    def test_fails_open_when_redis_is_down(self):
        with mock.patch.object(bot_core.rd, "__init__", side_effect=ConnectionError("down")):
            self.assertTrue(bot_core.is_new_update(8))
        self.assertTrue(bot_core.is_new_update(None))
