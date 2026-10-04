"""
Text and image encoders behind one small interface, so the model can be swapped
from settings (``TEXT_EMBEDDING_MODEL``) without touching the search code.

Models are imported and loaded lazily, on first use, and cached per process.
"""
import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

# key -> (backend, model name, dimensions)
TEXT_MODELS = {
    # Original model: Universal Sentence Encoder large v5 (TensorFlow Hub), English.
    "use-large": ("tfhub", "https://tfhub.dev/google/universal-sentence-encoder-large/5", 512),
    # Smaller and faster sentence-transformers models (PyTorch).
    "minilm": ("sentence-transformers", "sentence-transformers/all-MiniLM-L6-v2", 384),
    # Multilingual: also understands synopses written in Spanish and ~50 other languages.
    "minilm-multilingual": (
        "sentence-transformers",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        384,
    ),
}

# CLIP maps images and text into the same 512-d space.
IMAGE_MODEL = ("sentence-transformers", "clip-ViT-B-32", 512)

_lock = threading.Lock()
_loaded = {}


def _load_sentence_transformer(name):
    with _lock:
        if name not in _loaded:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading sentence-transformers model %s", name)
            _loaded[name] = SentenceTransformer(name)
    return _loaded[name]


class TextEncoder:
    def __init__(self, key):
        if key not in TEXT_MODELS:
            raise ValueError(
                f"Unknown TEXT_EMBEDDING_MODEL {key!r}; choose one of {sorted(TEXT_MODELS)}"
            )
        self.key = key
        self.backend, self.model_name, self.dims = TEXT_MODELS[key]

    def encode(self, texts):
        """Return one vector (python list of floats) per text."""
        texts = list(texts)
        if not texts:
            return []
        if self.backend == "tfhub":
            from apps.botAI.load_model import LoadModel

            return LoadModel().encode(texts)
        model = _load_sentence_transformer(self.model_name)
        return model.encode(texts, normalize_embeddings=True).tolist()

    def warm_up(self):
        self.encode(["warm up"])


class ImageEncoder:
    def __init__(self):
        self.backend, self.model_name, self.dims = IMAGE_MODEL

    def encode_images(self, images):
        """``images``: PIL images. Returns one vector per image."""
        images = [image.convert("RGB") for image in images]
        if not images:
            return []
        model = _load_sentence_transformer(self.model_name)
        return model.encode(images, normalize_embeddings=True).tolist()


def get_text_encoder():
    return TextEncoder(getattr(settings, "TEXT_EMBEDDING_MODEL", "use-large"))


def get_image_encoder():
    return ImageEncoder()
