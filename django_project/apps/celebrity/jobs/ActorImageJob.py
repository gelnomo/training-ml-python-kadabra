import os
from overrides import override
import urllib.request

from apps.celebrity.enums import StatusEnum
from ms_data_mining.inteface import InterfaceJob
from apps.celebrity.models import ActorImage, ElasticSearchActorImage
from django.conf import settings
import face_recognition
from fake_useragent import UserAgent


class ActorImageJob(InterfaceJob):
    JOB_MODEL = ActorImage

    @override
    def internal_process(self, item_id: str) -> bool:
        is_completed = True
        obj_actor_image = self.JOB_MODEL.objects.get(id=item_id)
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
    def __is_valid_face(obj_actor_image):
        image = face_recognition.load_image_file(obj_actor_image.path)
        face_locations = face_recognition.face_locations(image)
        face_encodings = face_recognition.face_encodings(image, face_locations)
        obj_actor_image.is_valid = True

        if not face_encodings or len(face_encodings) > 1:
            if os.path.exists(obj_actor_image.path):
                os.remove(obj_actor_image.path)
            obj_actor_image.is_valid = False
        else:
            ElasticSearchActorImage.objects.update_or_create(
                actor_image=obj_actor_image,
                defaults={"status": StatusEnum.READY, "attempt": 0},
            )
        obj_actor_image.save()
