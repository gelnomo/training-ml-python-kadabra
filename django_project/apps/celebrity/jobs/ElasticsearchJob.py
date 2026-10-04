import logging
import re

from dateutil.relativedelta import relativedelta
from overrides import override

from apps.celebrity.models import ElasticSearchActorImage
from apps.document.schema import Faces
from ms_data_mining.inteface import InterfaceJob

logger = logging.getLogger(__name__)


def estimate_age(image):
    """Apparent age of the face in ``image`` (RGB array) with DeepFace, or None."""
    try:
        import cv2
        from deepface import DeepFace

        detected_face = cv2.resize(image, (224, 224))
        objs = DeepFace.analyze(
            img_path=detected_face,
            actions=["age"],
            silent=True,
            enforce_detection=False,
        )
        return objs[0]["age"]
    except Exception as ex:
        logger.warning("Age estimation failed: %s", ex)
        return None


def photo_year(birthday, age):
    """
    Parse the scraped birthday and return ``(birthday, birthday + age years)``.
    Either value is None when it can't be computed.
    """
    import pandas as pd

    try:
        if birthday and len(birthday) <= 7:
            birthday = re.sub(r"[^\d]", "", birthday)
        birthday = pd.to_datetime(birthday)
        if birthday is pd.NaT:
            birthday = None
    except Exception as ex:
        logger.debug("Unparseable birthday %r: %s", birthday, ex)
        return None, None

    year = None
    if birthday is not None and age is not None:
        year = (birthday + relativedelta(years=int(age))).year
    return birthday, year


class ElasticsearchJob(InterfaceJob):
    JOB_MODEL = ElasticSearchActorImage

    @staticmethod
    def get_encoding(obj_actor_image):
        import face_recognition

        image = face_recognition.load_image_file(obj_actor_image.path)
        if obj_actor_image.face_encoding:
            # Computed and stored by ActorImageJob: skip the expensive face detection.
            return [obj_actor_image.face_encoding], image

        face_locations = face_recognition.face_locations(image)
        face_encodings = [e.tolist() for e in face_recognition.face_encodings(image, face_locations)]
        return face_encodings, image

    @override
    def internal_process(self, item_id: str) -> bool:
        obj_elasticsearch = self.JOB_MODEL.objects.select_related(
            "actor_image__actor"
        ).get(id=item_id)
        actor_image = obj_elasticsearch.actor_image
        face_encodings, image = self.get_encoding(actor_image)
        if not face_encodings:
            # Nothing to index: skip the (expensive) DeepFace age estimation.
            return False

        age = estimate_age(image)
        birthday, year = photo_year(actor_image.actor.birthday, age)

        # One document per actor image: ActorImageJob only keeps images with exactly one face.
        data_dict = {
            "id": str(obj_elasticsearch.id),
            "name": actor_image.actor.name,
            "image_id": str(actor_image.id),
            "actor_id": str(actor_image.actor.id),
            "face_encoding": face_encodings[0],
            "age": age,
            "birthday": birthday,
            "year": year,
        }

        # index() creates or replaces the document, so no exists() round trip is needed.
        Faces().insert_one(data_dict)
        return True
