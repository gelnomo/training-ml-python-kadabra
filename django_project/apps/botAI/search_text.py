from apps.document.schema import Movies
from constance import config
import nltk
import re
from nltk.stem import WordNetLemmatizer
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.corpus import wordnet
from html import escape


class SearchText:
    _stop_words = None

    def __init__(self, message, actors, threshold=None):
        self.message = message
        self.actors = actors or []
        # Read the constance value at call time, not at import time, so admin changes apply.
        self.threshold = threshold if threshold is not None else config.THRESHOLD_TEXT
        self.lemmatizer = WordNetLemmatizer()
        # Load the stop words once per process, as a set for O(1) lookups.
        if SearchText._stop_words is None:
            SearchText._stop_words = frozenset(stopwords.words("english"))

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
            if key not in self._stop_words and key not in exclude_words:
                sentences.append(root_word)

        # Remove duplicates but keep the original word order (set() order is random).
        text = " ".join(dict.fromkeys(sentences))

        return text

    def process(self):
        movies = Movies()
        message = self.message
        if message:
            message = self.__preprocessor_remove_special_chars(self.message)

        films = movies.query_movie(message, self.actors, k=config.K_TEXT)

        result = []
        movie_url = None

        for hit in films["hits"]["hits"]:
            if hit["_score"] < self.threshold:
                continue
            movie_name = escape(str(hit["_source"]["title"]), quote=False)
            if not movie_url:
                movie_url = f"\nLink:\n\t<a href='https://www.imdb.com/title/{escape(str(hit['_source']['imdb_id']))}'>{movie_name}</a>"
            movie_year = hit["_source"]["year"]
            text = f"Movie:\n\t<b>{movie_name}</b>" \
                   f"\nReleased:\n\t{movie_year}\n"
            result.append(text)

        if not result:
            # Let the bot answer with its "not enough information" message.
            return None

        if self.actors:
            names = ", ".join(escape(item["name"], quote=False) for item in self.actors)
            result.insert(0, f"Identified Celebrities: \t<b>{names}</b>\n")
        result.append(f"Best Result: {movie_url}")
        return "\n".join(result)
