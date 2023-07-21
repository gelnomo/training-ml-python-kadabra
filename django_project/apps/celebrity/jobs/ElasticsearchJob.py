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
        obj_elasticsearch = self.JOB_MODEL.objects.get(id=item_id)
        faces = Faces()
        face_encodings, image = self.get_encoding(obj_elasticsearch.actor_image)

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
            if birthday:
                future_date = (birthday + relativedelta(years=age)).year
        except Exception as ex:
            birthday = None
            print(ex)

        for face_encoding in face_encodings:
            data_dict = {
                "id": str(obj_elasticsearch.id),
                "name": obj_elasticsearch.actor_image.actor.name,
                "image_id": str(obj_elasticsearch.actor_image.id),
                "actor_id": str(obj_elasticsearch.actor_image.actor.id),
                "face_encoding": face_encoding.tolist(),
                "age": age,
                "birthday": birthday,
                "year": future_date
            }

            if faces.check_by_document_id(item_id):
                faces.update_one(data_dict)
            else:
                faces.insert_one(data_dict)

            return True
        return False
