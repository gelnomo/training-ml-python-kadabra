import logging
from html import escape

import nltk
import re
from constance import config
from nltk.stem import WordNetLemmatizer
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.corpus import wordnet

from apps.document.ranking import rrf_fuse
from apps.document.schema import Movies, MoviePassages

logger = logging.getLogger(__name__)

# How many vector candidates the hybrid mode re-ranks with BM25.
HYBRID_CANDIDATES_FACTOR = 5


class SearchText:
    """
    Find movies from a text synopsis and/or the actors recognised in a photo.

    * text only        -> kNN on the description vectors
    * text + actors    -> kNN **filtered** to movies with those actors
                          (falls back to text only if the filter finds nothing)
    * actors only      -> movies containing the actors, most actors first

    ``TEXT_SEARCH_MODE`` (constance) picks the text strategy:
    ``vector`` (one vector per movie), ``hybrid`` (vector candidates re-ranked
    with BM25 keywords through Reciprocal Rank Fusion) or ``passages``
    (several vectors per movie).
    """

    _stop_words = None

    def __init__(self, message, actors, threshold=None, mode=None, k=None, preprocess=None):
        self.message = message
        self.actors = actors or []
        # Read the constance values at call time, not at import time, so admin changes apply.
        self.threshold = threshold if threshold is not None else config.THRESHOLD_TEXT
        self.mode = mode or config.TEXT_SEARCH_MODE
        self.k = k or config.K_TEXT
        self.preprocess = preprocess if preprocess is not None else config.TEXT_PREPROCESS
        self.lemmatizer = WordNetLemmatizer()

    @classmethod
    def stop_words(cls):
        # Loaded once per process, as a set for O(1) lookups.
        if cls._stop_words is None:
            cls._stop_words = frozenset(stopwords.words("english"))
        return cls._stop_words

    @staticmethod
    def __reduce_lengthening(text: str) -> str:
        """
        Reduces repeated characters in a word to two characters.

        Args:
            text (str): The input text.

        Returns:
            str: Text with reduced lengthening.

        """
        pattern = re.compile(r"(\w)\1{2,}", re.IGNORECASE)
        return pattern.sub(r"\1\1", text)

    @staticmethod
    def __get_wordnet_pos(treebank_tag: str) -> str:
        """
        Maps the treebank POS tags to WordNet POS tags.

        Parameters:
            treebank_tag (str): The POS tag from the treebank.

        Returns:
            str: The corresponding WordNet POS tag.

        """
        if treebank_tag.startswith('J'):
            return wordnet.ADJ
        elif treebank_tag.startswith('V'):
            return wordnet.VERB
        elif treebank_tag.startswith('N'):
            return wordnet.NOUN
        elif treebank_tag.startswith('R'):
            return wordnet.ADV
        else:
            return wordnet.ADJ_SAT

    def __get_correct_word(self, text: str) -> str:
        """
        Performs spelling correction on the input text using TextBlob.

        Args:
            text (str): The input text.

        Returns:
            str: Text with spelling corrections.

        """
        text = self.__reduce_lengthening(text)
        # text = str(TextBlob(text).correct())

        return text

    def __preprocessor_remove_special_chars(self, text: str, exclude_words: tuple = ()) -> str:
        """
        Preprocesses the text by removing special characters, numbers, and applying lemmatization or stemming.

        Args:
            text (str): The input text.

        Returns:
            str: Preprocessed text.

        """

        text = text.lower().strip()
        text = re.sub(r"[^\w\s]|[0-9]", " ", text)
        text = re.sub(r"[!@#~`%^&*(){};:/<>?\|_]", " ", text)
        tokens = word_tokenize(text)
        tokens_pos = nltk.pos_tag(tokens)
        sentences = []
        for word, tag in tokens_pos:
            # __get_correct_word already reduces lengthening.
            _word = self.__get_correct_word(word)
            root_word = self.lemmatizer.lemmatize(_word, pos=self.__get_wordnet_pos(tag))
            key = root_word.lower().strip()
            if key not in self.stop_words() and key not in exclude_words:
                sentences.append(root_word)

        # Remove duplicates but keep the original word order (set() order is random).
        text = " ".join(dict.fromkeys(sentences))

        return text

    def clean_text(self):
        if not self.message:
            return None
        if not self.preprocess:
            return self.message.strip() or None
        return self.__preprocessor_remove_special_chars(self.message) or None

    @staticmethod
    def _result(hit):
        source = hit["_source"]
        return {
            "title": source["title"],
            "year": source.get("year"),
            "imdb_id": source.get("imdb_id"),
            "score": hit["_score"],
            "doc_id": hit["_id"],
        }

    def _text_hits(self, text, actor_ids, k, threshold):
        index = MoviePassages() if self.mode == "passages" else Movies()
        vector = index.encode_one(text)
        candidates = k * HYBRID_CANDIDATES_FACTOR if self.mode == "hybrid" else k

        hits = []
        if actor_ids:
            hits = [h for h in index.knn_search(vector, candidates, actor_ids) if h["_score"] >= threshold]
            if not hits:
                logger.info("No text match with actors %s; retrying without the actor filter", actor_ids)
        if not hits:
            hits = [h for h in index.knn_search(vector, candidates) if h["_score"] >= threshold]

        if self.mode == "hybrid" and len(hits) > 1:
            by_id = {hit["_id"]: hit for hit in hits}
            keyword_rank = Movies().bm25_rank(self.message, list(by_id))
            hits = [by_id[doc_id] for doc_id in rrf_fuse([list(by_id), keyword_rank]) if doc_id in by_id]

        return hits[:k]

    def search(self, k=None, threshold=None):
        """Return the ranked results as dicts: title, year, imdb_id, score, doc_id."""
        k = k or self.k
        threshold = self.threshold if threshold is None else threshold
        actor_ids = [item["id"] for item in self.actors]
        text = self.clean_text()

        if text:
            hits = self._text_hits(text, actor_ids, k, threshold)
        elif actor_ids:
            years = [int(a["year"]) for a in self.actors if str(a.get("year") or "").isdigit()]
            hits = Movies().search_by_actors(actor_ids, k, years, config.THRESHOLD_YEAR)
        else:
            hits = []

        return [self._result(hit) for hit in hits]

    def process(self):
        return format_results(self.search(), self.actors)


def format_results(results, actors=()):
    """Telegram (HTML) reply for a list of search results, or None."""
    if not results:
        # Let the bot answer with its "not enough information" message.
        return None

    lines = []
    if actors:
        names = ", ".join(escape(item["name"], quote=False) for item in actors)
        lines.append(f"Identified Celebrities: \t<b>{names}</b>\n")

    for result in results:
        movie_name = escape(str(result["title"]), quote=False)
        lines.append(f"Movie:\n\t<b>{movie_name}</b>\nReleased:\n\t{result['year']}\n")

    best = results[0]
    lines.append(
        f"Best Result: \nLink:\n\t<a href='https://www.imdb.com/title/{escape(str(best['imdb_id']))}'>"
        f"{escape(str(best['title']), quote=False)}</a>"
    )
    return "\n".join(lines)
