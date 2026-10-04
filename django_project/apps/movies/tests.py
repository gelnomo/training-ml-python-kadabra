from unittest import mock

from django.test import TestCase, override_settings

from apps.celebrity.models import Actor
from apps.movies.jobs.ElasticsearchJob import ElasticsearchJob, movie_row
from apps.movies.jobs.MovieJob import MovieJob
from apps.movies.models import ElasticSearchMovie, Movie, MovieActor
from apps.movies.jobs.posters import poster_url

change_chars = MovieJob._MovieJob__change_chars


def escaped(text):
    """What download_page() produces for non-ASCII text: str(bytes) escapes."""
    return str(text.encode("utf-8"))[2:-1]


class ChangeCharsTests(TestCase):
    def test_decodes_utf8_escapes(self):
        for text in ["Penélope Cruz", "Zoë Saldaña", "Björk", "Chiwetel Ejiofor’s"]:
            self.assertEqual(change_chars(escaped(text)), text)

    def test_drops_nbsp_newlines_and_unescapes_quotes(self):
        self.assertEqual(change_chars(escaped("Mía Maestro")), "MíaMaestro")
        self.assertEqual(change_chars(r"Don\'t\nstop"), "Don'tstop")


class CreateActorsTests(TestCase):
    def test_more_names_than_ids_and_empty_values(self):
        movie = Movie.objects.create(name="M", imdb_id="tt1", starts_id="nm1", starts_name="Alice, Bob,")
        MovieJob._MovieJob__create_actors(movie)
        actors = dict(Actor.objects.values_list("name", "imdb_id"))
        self.assertEqual(actors, {"Alice": "nm1", "Bob": None})
        self.assertEqual(MovieActor.objects.filter(movie=movie).count(), 2)

    def test_no_cast(self):
        movie = Movie.objects.create(name="M", imdb_id="tt2")
        MovieJob._MovieJob__create_actors(movie)
        self.assertFalse(Actor.objects.exists())


class MovieIndexingTests(TestCase):
    def setUp(self):
        self.movie = Movie.objects.create(
            name="Heat", imdb_id="tt0113277", year="1995", description="A heist.", director_name="Michael Mann",
            payload={"Poster": "https://example.com/heat.jpg"},
        )
        for name in ("Al Pacino", "Robert De Niro"):
            actor = Actor.objects.create(name=name, slug=name.lower().replace(" ", "-"))
            MovieActor.objects.create(movie=self.movie, actor=actor)
        self.document = ElasticSearchMovie.objects.create(movie=self.movie)

    def test_movie_row(self):
        row = movie_row(self.document)
        self.assertEqual(row["id"], str(self.document.id))
        self.assertEqual(row["year"], 1995)
        self.assertEqual(row["description"], "A heist..Heat.Michael Mann")
        self.assertEqual(sorted(c["name"] for c in row["celebrities"]), ["Al Pacino", "Robert De Niro"])

    def test_year_none(self):
        Movie.objects.filter(id=self.movie.id).update(year=None)
        self.document.refresh_from_db()
        self.assertEqual(movie_row(self.document)["year"], 0)

    @override_settings(INDEX_MOVIE_PASSAGES=False, INDEX_MOVIE_POSTERS=False)
    def test_job_indexes_the_movie_only(self):
        with mock.patch("apps.movies.jobs.ElasticsearchJob.Movies") as movies, \
                mock.patch("apps.movies.jobs.ElasticsearchJob.MoviePassages") as passages:
            self.assertTrue(ElasticsearchJob(1, 3).internal_process(str(self.document.id)))
        movies.return_value.insert_one.assert_called_once()
        passages.assert_not_called()

    @override_settings(INDEX_MOVIE_PASSAGES=True, INDEX_MOVIE_POSTERS=True)
    def test_job_also_indexes_passages_and_poster(self):
        with mock.patch("apps.movies.jobs.ElasticsearchJob.Movies"), \
                mock.patch("apps.movies.jobs.ElasticsearchJob.MoviePassages") as passages, \
                mock.patch("apps.movies.jobs.posters.index_poster", side_effect=OSError("offline")) as poster:
            # A poster failure must not fail the movie.
            self.assertTrue(ElasticsearchJob(1, 3).internal_process(str(self.document.id)))
        row, chunks = passages.return_value.replace_movie.call_args.args
        self.assertEqual(chunks, ["A heist..Heat.Michael Mann"])
        poster.assert_called_once()

    def test_poster_url_from_payload(self):
        self.assertEqual(poster_url(self.movie), "https://example.com/heat.jpg")
        self.movie.payload = {"Poster": "N/A"}
        with override_settings(IMDBID_APIKEY=""):
            self.assertIsNone(poster_url(self.movie))

    @override_settings(INDEX_MOVIE_PASSAGES=True, INDEX_MOVIE_POSTERS=True)
    def test_deleting_removes_all_documents(self):
        with mock.patch("apps.movies.signals.Movies") as movies, \
                mock.patch("apps.movies.signals.MoviePassages") as passages, \
                mock.patch("apps.movies.signals.MoviePosters") as posters:
            document_id = str(self.document.id)
            self.document.delete()
        movies.return_value.delete_by_document_id.assert_called_once_with(document_id)
        passages.return_value.delete_movie.assert_called_once_with(document_id)
        posters.return_value.delete_by_document_id.assert_called_once_with(document_id)
