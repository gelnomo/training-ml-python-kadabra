import face_recognition
import numpy as np
from apps.document.schema import Faces
from constance import config


class SearchImage:
    def __init__(self, image, threshold=config.THRESHOLD_IMAGE):
        self.image = image
        self.threshold = threshold

    def process(self):
        celebrities_names = []
        im_src_array = np.array(self.image)
        face_encodings = face_recognition.face_encodings(im_src_array)

        if not face_encodings:
            return []

        faces = Faces()
        celebrities = faces.query_face(face_encodings)

        for celebrity in celebrities:
            for hit in celebrity["hits"]["hits"]:
                if float(hit["_score"]) > self.threshold:
                    res = next((sub for sub in celebrities_names if sub['id'] == hit["_source"]["actor_id"]), None)
                    if not res:
                        celebrities_names.append({"name": hit["_source"]["name"].strip(),
                                                  "id": hit["_source"]["actor_id"],
                                                  "age": hit["_source"]["age"],
                                                  "birthday": hit["_source"]["birthday"],
                                                  "year": hit["_source"]["year"]})
        return celebrities_names
