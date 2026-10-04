import logging

import numpy as np
from constance import config

from apps.document.ranking import vote_actor
from apps.document.schema import Faces, MoviePosters

logger = logging.getLogger(__name__)


class SearchImage:
    """Recognise the actors in a photo with kNN over the indexed face encodings."""

    def __init__(self, image, threshold=None, min_votes=None, k=None):
        self.image = image
        # Read the constance values at call time, not at import time, so admin changes apply.
        self.threshold = threshold if threshold is not None else config.THRESHOLD_IMAGE
        self.min_votes = min_votes if min_votes is not None else config.FACE_MIN_VOTES
        self.k = k or config.FACE_KNN_K

    def face_encodings(self):
        import face_recognition

        # face_recognition expects an 8-bit RGB array (PNG/RGBA uploads would fail otherwise).
        im_src_array = np.array(self.image.convert("RGB"))
        return face_recognition.face_encodings(im_src_array)

    def process(self):
        face_encodings = self.face_encodings()
        if not face_encodings:
            return []

        celebrities = []
        seen_ids = set()
        # One kNN search per face (sent together), then one vote per face.
        for hits in Faces().query_face(face_encodings, k=self.k):
            winner = vote_actor(hits, self.threshold, self.min_votes)
            if winner is None or winner["actor_id"] in seen_ids:
                continue
            seen_ids.add(winner["actor_id"])
            celebrities.append(
                {
                    "name": winner["name"].strip(),
                    "id": winner["actor_id"],
                    "age": winner.get("age"),
                    "birthday": winner.get("birthday"),
                    "year": winner.get("year"),
                    "votes": winner["votes"],
                    "score": winner["score"],
                }
            )
        logger.info("Recognised %d of %d faces", len(celebrities), len(face_encodings))
        return celebrities


class SearchScene:
    """
    Match a photo against movie posters with CLIP when no actor is recognised
    (e.g. a landscape, a spaceship, an animated movie).
    """

    def __init__(self, image, threshold=None, k=None):
        self.image = image
        self.threshold = threshold if threshold is not None else config.THRESHOLD_SCENE
        self.k = k or config.K_TEXT

    def search(self):
        posters = MoviePosters()
        vector = posters.encode_images([self.image])[0]
        hits = posters.knn_search(vector, self.k)
        return [
            {
                "title": hit["_source"]["title"],
                "year": hit["_source"]["year"],
                "imdb_id": hit["_source"]["imdb_id"],
                "score": hit["_score"],
                "doc_id": hit["_id"],
            }
            for hit in hits
            if hit["_score"] >= self.threshold
        ]
