import logging
import os
import urllib.request

from django.conf import settings
from fake_useragent import UserAgent
from overrides import override

from apps.celebrity.enums import StatusEnum
from apps.celebrity.models import ActorImage, ElasticSearchActorImage
from ms_data_mining.inteface import InterfaceJob

logger = logging.getLogger(__name__)


class ActorImageJob(InterfaceJob):
    JOB_MODEL = ActorImage

    @override
    def internal_process(self, item_id: str) -> bool:
        is_completed = True
        obj_actor_image = self.JOB_MODEL.objects.select_related("actor").get(id=item_id)
        self.__download_images(obj_actor_image)
        return is_completed

    def __download_images(self, obj_actor_image):
        ua = UserAgent(browsers=["edge", "chrome"])
        req = urllib.request.Request(
            obj_actor_image.url,
            headers={"User-Agent": ua.random},
        )
        with urllib.request.urlopen(req, None, 15) as response:
            if response.status != 200:
                return
            data = response.read()

        path = f"{settings.STATIC_ROOT}/images/celebrities/{obj_actor_image.actor.name.strip()}/{obj_actor_image.keyword.strip().replace(' ', '')}"
        os.makedirs(path, exist_ok=True)

        path = f"{path}/{str(obj_actor_image.id)}.jpg"

        with open(path, "wb") as output_file:
            output_file.write(data)
        obj_actor_image.path = path
        obj_actor_image.save()
        self.__is_valid_face(obj_actor_image)

    @staticmethod
    def face_encodings(path):
        import face_recognition

        image = face_recognition.load_image_file(path)
        face_locations = face_recognition.face_locations(image)
        return face_recognition.face_encodings(image, face_locations)

    @classmethod
    def __is_valid_face(cls, obj_actor_image):
        face_encodings = cls.face_encodings(obj_actor_image.path)
        obj_actor_image.is_valid = True

        if not face_encodings or len(face_encodings) > 1:
            if os.path.exists(obj_actor_image.path):
                os.remove(obj_actor_image.path)
            obj_actor_image.is_valid = False
            obj_actor_image.face_encoding = None
        else:
            # Keep the encoding so the Elasticsearch job doesn't compute it again.
            obj_actor_image.face_encoding = face_encodings[0].tolist()
        obj_actor_image.save()

        if obj_actor_image.is_valid:
            ElasticSearchActorImage.objects.update_or_create(
                actor_image=obj_actor_image,
                defaults={"status": StatusEnum.READY, "attempt": 0},
            )
