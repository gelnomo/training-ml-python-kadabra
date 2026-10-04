import re
from dateutil.relativedelta import relativedelta
from overrides import override
import face_recognition
from apps.document.schema import Faces
from apps.celebrity.models import ElasticSearchActorImage
from ms_data_mining.inteface import InterfaceJob
import pandas as pd
import cv2
from deepface import DeepFace


class ElasticsearchJob(InterfaceJob):
    JOB_MODEL = ElasticSearchActorImage

    @staticmethod
    def get_encoding(obj_actor_image):
        image = face_recognition.load_image_file(obj_actor_image.path)
        face_locations = face_recognition.face_locations(image)
        face_encodings = face_recognition.face_encodings(image, face_locations)
        return face_encodings, image

    @override
    def internal_process(self, item_id: str) -> bool:
        obj_elasticsearch = self.JOB_MODEL.objects.select_related(
            "actor_image__actor"
        ).get(id=item_id)
        face_encodings, image = self.get_encoding(obj_elasticsearch.actor_image)
        if not face_encodings:
            # Nothing to index: skip the (expensive) DeepFace age estimation.
            return False

        try:
            detected_face = cv2.resize(image, (224, 224))

            objs = DeepFace.analyze(img_path=detected_face,
                                    actions=['age'],
                                    silent=True,
                                    enforce_detection=False,
                                    )
            age = objs[0]['age']
        except Exception as ex:
            age = None
            print(ex)

        future_date = None
        try:
            birthday = obj_elasticsearch.actor_image.actor.birthday
            if birthday and len(birthday) <= 7:
                birthday = re.sub(r"[^\d]", "", birthday)
            birthday = pd.to_datetime(birthday)
            if birthday and age is not None:
                future_date = (birthday + relativedelta(years=age)).year
        except Exception as ex:
            birthday = None
            print(ex)

        # One document per actor image: ActorImageJob only keeps images with exactly one face.
        data_dict = {
            "id": str(obj_elasticsearch.id),
            "name": obj_elasticsearch.actor_image.actor.name,
            "image_id": str(obj_elasticsearch.actor_image.id),
            "actor_id": str(obj_elasticsearch.actor_image.actor.id),
            "face_encoding": face_encodings[0].tolist(),
            "age": age,
            "birthday": birthday,
            "year": future_date,
        }

        # index() creates or replaces the document, so no exists() round trip is needed.
        Faces().insert_one(data_dict)
        return True
