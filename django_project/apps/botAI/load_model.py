import tensorflow_hub as hub


class LoadModel(object):
    _instance = None
    _embed = None

    def __new__(self):
        if self._instance is None:
            model_url = "https://tfhub.dev/google/universal-sentence-encoder-large/5"
            print("**** Loading Hub KerasLayer ****")
            self._embed = hub.KerasLayer(model_url)
            self._instance = super(LoadModel, self).__new__(self)
        return self._instance

    def get_embed(self):
        return self._embed
