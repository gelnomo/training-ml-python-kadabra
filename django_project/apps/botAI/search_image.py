import face_recognition
import numpy as np
from apps.document.schema import Faces
from constance import config


class SearchImage:
    def __init__(self, image, threshold=None):
        self.image = image
        # Read the constance value at call time, not at import time, so admin changes apply.
        self.threshold = threshold if threshold is not None else config.THRESHOLD_IMAGE

    def process(self):
        celebrities_names = []
        # face_recognition expects an 8-bit RGB array (PNG/RGBA uploads would fail otherwise).
        im_src_array = np.array(self.image.convert("RGB"))
        face_encodings = face_recognition.face_encodings(im_src_array)

        if not face_encodings:
            return []

        faces = Faces()
        celebrities = faces.query_face(face_encodings)

        seen_ids = set()
        for celebrity in celebrities:
            for hit in celebrity["hits"]["hits"]:
                source = hit["_source"]
                if float(hit["_score"]) > self.threshold and source["actor_id"] not in seen_ids:
                    seen_ids.add(source["actor_id"])
                    celebrities_names.append({"name": source["name"].strip(),
                                              "id": source["actor_id"],
                                              "age": source.get("age"),
                                              "birthday": source.get("birthday"),
                                              "year": source.get("year")})
        return celebrities_names
