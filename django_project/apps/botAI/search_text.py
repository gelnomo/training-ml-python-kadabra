from apps.document.schema import Movies
from constance import config
import nltk
import re
from nltk.stem import WordNetLemmatizer
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.corpus import wordnet
from textblob import TextBlob


class SearchText:
    def __init__(self, message, actors, threshold=config.THRESHOLD_TEXT):
        self.message = message
        self.actors = actors
        self.threshold = threshold
        self.lemmatizer = WordNetLemmatizer()
        self._stop_words = stopwords.words('english')

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
        text = str(TextBlob(text).correct())

        return text

    def __preprocessor_remove_special_chars(self, text: str, exclude_words: list = []) -> str:
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
            _word = self.__reduce_lengthening(word)
            _word = self.__get_correct_word(_word)
            root_word = self.lemmatizer.lemmatize(_word, pos=self.__get_wordnet_pos(tag))
            if root_word.lower().strip() not in self._stop_words and root_word.lower().strip() not in exclude_words:
                sentences.append(root_word)

        text = " ".join(set(sentences))

        return text

    def process(self):
        movies = Movies()
        message = self.message
        if message:
            message = self.__preprocessor_remove_special_chars(self.message)

        films = movies.query_movie(message, self.actors, k=config.K_TEXT)
        result = [
            f"Identified Celebrities: \t<b>{', '.join([item['name'] for item in self.actors])}</b>\n" if self.actors else ""]

        movie_url = None

        for hit in films["hits"]["hits"]:
            if hit["_score"] < self.threshold:
                continue
            movie_name = hit["_source"]["title"]
            if not movie_url:
                movie_url = f"\nLink:\n\t<a href='https://www.imdb.com/title/{hit['_source']['imdb_id']}'>{movie_name}</a>"
            movie_year = hit["_source"]["year"]
            text = f"Movie:\n\t<b>{movie_name}</b>" \
                   f"\nReleased:\n\t{movie_year}\n"
            result.append(text)
        result.append(f"Best Result: {movie_url}")
        return "\n".join(result) if result else None
