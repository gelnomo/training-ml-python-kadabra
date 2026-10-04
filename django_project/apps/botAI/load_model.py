import threading

import numpy as np

MODEL_URL = "https://tfhub.dev/google/universal-sentence-encoder-large/5"


class LoadModel(object):
    """
    Process-wide singleton for the Universal Sentence Encoder.

    The model is loaded lazily on the first call to ``get_embed`` (instead of at
    import time from ``settings.py``) so that management commands such as
    ``migrate`` or ``celery beat`` don't pay the cost of loading TensorFlow.
    """

    _instance = None
    _embed = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(LoadModel, cls).__new__(cls)
        return cls._instance

    def get_embed(self):
        if LoadModel._embed is None:
            with LoadModel._lock:
                if LoadModel._embed is None:
                    import tensorflow_hub as hub

                    print("**** Loading Hub KerasLayer ****")
                    LoadModel._embed = hub.KerasLayer(MODEL_URL)
        return LoadModel._embed

    def encode(self, texts):
        """Return one 512-d embedding (as a python list) per input text."""
        import tensorflow as tf

        embeddings = self.get_embed()(tf.constant(list(texts)))
        return np.asarray(embeddings).tolist()
