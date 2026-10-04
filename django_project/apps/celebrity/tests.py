import json
import sys
import types
from datetime import timedelta
from unittest import mock

import numpy as np
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone

from apps.celebrity.enums import StatusEnum
from apps.celebrity.jobs.ActorImageJob import ActorImageJob
from apps.celebrity.jobs.ElasticsearchJob import ElasticsearchJob, photo_year
from apps.celebrity.models import Actor, ActorImage, ElasticSearchActorImage
from ms_data_mining.inteface import InterfaceJob

WEBHOOK = "/bot/webhook/"


@override_settings(BOT_SECRET_TOKEN="s3cret")
class WebhookTests(TestCase):
    def post(self, body, token="s3cret"):
        headers = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": token} if token else {}
        return self.client.post(WEBHOOK, data=json.dumps(body), content_type="application/json", **headers)

    def test_rejects_a_wrong_secret(self):
        with mock.patch("apps.celebrity.views.telegram_process_update") as task:
            self.assertEqual(self.post({"update_id": 1}, token="nope").status_code, 403)
            self.assertEqual(self.post({"update_id": 1}, token=None).status_code, 403)
        task.delay.assert_not_called()

    def test_queues_the_update_and_answers_immediately(self):
        with mock.patch("apps.celebrity.views.is_new_update", return_value=True), \
                mock.patch("apps.celebrity.views.telegram_process_update") as task:
            response = self.post({"update_id": 5, "message": {"text": "hi"}})
        self.assertEqual(response.status_code, 200)
        task.delay.assert_called_once_with({"update_id": 5, "message": {"text": "hi"}})

    def test_ignores_duplicates(self):
        with mock.patch("apps.celebrity.views.is_new_update", return_value=False), \
                mock.patch("apps.celebrity.views.telegram_process_update") as task:
            self.assertEqual(self.post({"update_id": 5}).status_code, 200)
        task.delay.assert_not_called()

    def test_broker_failure_lets_telegram_retry(self):
        with mock.patch("apps.celebrity.views.is_new_update", return_value=True), \
                mock.patch("apps.celebrity.views.forget_update") as forget, \
                mock.patch("apps.celebrity.views.telegram_process_update") as task:
            task.delay.side_effect = ConnectionError("broker down")
            self.assertEqual(self.post({"update_id": 6}).status_code, 503)
        forget.assert_called_once_with(6)

    def test_bad_json(self):
        response = self.client.post(WEBHOOK, data="{", content_type="application/json",
                                    HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="s3cret")
        self.assertEqual(response.status_code, 400)


class SubscribeTests(TestCase):
    def test_requires_staff(self):
        with mock.patch("apps.celebrity.views.TelegramBot") as bot:
            # Anonymous: 401 (JWT is the first authentication class), never 200.
            self.assertIn(self.client.get("/bot/webhook/subscribe").status_code, (401, 403))
            user = get_user_model().objects.create_user("plain", password="x")
            self.client.force_login(user)
            self.assertEqual(self.client.get("/bot/webhook/unsubscribe").status_code, 403)
            bot.subscribe.assert_not_called()
            bot.unsubscribe.assert_not_called()

    def test_staff_session_can_subscribe(self):
        from django.http import HttpResponse

        staff = get_user_model().objects.create_user("staff", password="x", is_staff=True)
        self.client.force_login(staff)
        with mock.patch("apps.celebrity.views.TelegramBot") as bot:
            bot.subscribe.return_value = HttpResponse("ok")
            self.assertEqual(self.client.get("/bot/webhook/subscribe").status_code, 200)
        bot.subscribe.assert_called_once()


class FakeJob(InterfaceJob):
    JOB_MODEL = ActorImage
    fail_ids = ()

    def internal_process(self, item_id):
        if item_id in self.fail_ids:
            raise RuntimeError("boom")
        return True


class InterfaceJobTests(TestCase):
    def setUp(self):
        actor = Actor.objects.create(name="Alice", slug="alice")
        self.images = [
            ActorImage.objects.create(actor=actor, keyword="IMDB", url=f"http://x/{i}.jpg")
            for i in range(5)
        ]

    def statuses(self):
        return sorted(ActorImage.objects.values_list("status", flat=True))

    def test_process_claims_up_to_size_and_completes(self):
        FakeJob(size=3, attempt=3).process()
        self.assertEqual(self.statuses().count(StatusEnum.COMPLETED), 3)
        self.assertEqual(self.statuses().count(StatusEnum.READY), 2)

    def test_failures_are_marked_and_retried_until_expired(self):
        failing = str(self.images[0].id)
        job = FakeJob(size=0, attempt=1)
        job.fail_ids = (failing,)
        job.process()
        image = ActorImage.objects.get(id=failing)
        self.assertEqual(image.status, StatusEnum.ERROR)

        FakeJob(size=0, attempt=1).process_error()  # attempt 0 < 1 -> READY, attempt 1
        image.refresh_from_db()
        self.assertEqual((image.status, image.attempt), (StatusEnum.READY, 1))

        ActorImage.objects.filter(id=failing).update(status=StatusEnum.ERROR)
        FakeJob(size=0, attempt=1).process_error()  # attempt 1 >= 1 -> EXPIRED
        image.refresh_from_db()
        self.assertEqual(image.status, StatusEnum.EXPIRED)

    def test_long_task_resets_stuck_rows(self):
        stuck = self.images[0]
        ActorImage.objects.filter(id=stuck.id).update(
            status=StatusEnum.RUNNING, attempt=2, updated=timezone.now() - timedelta(days=2)
        )
        # `updated` is auto_now, so set it with update() above and check it moved.
        FakeJob(size=0, attempt=3).process_long_task()
        stuck.refresh_from_db()
        self.assertEqual((stuck.status, stuck.attempt), (StatusEnum.READY, 0))

    def test_claim_uses_skip_locked(self):
        with mock.patch.object(ActorImage.objects, "select_for_update", wraps=ActorImage.objects.select_for_update) as sfu:
            FakeJob(size=2, attempt=3).process()
        sfu.assert_called_with(skip_locked=True)


@skipUnlessDBFeature("has_select_for_update_skip_locked")
class ConcurrentClaimTests(TransactionTestCase):
    """Two workers at the same time: rows locked by one are skipped by the other."""

    def test_rows_locked_by_another_worker_are_skipped(self):
        import psycopg2

        actor = Actor.objects.create(name="Alice", slug="alice")
        images = [ActorImage.objects.create(actor=actor, keyword="IMDB", url=f"http://x/{i}") for i in range(5)]
        locked = [str(images[0].id), str(images[1].id)]

        # Without SKIP LOCKED the job would wait on worker 1's lock: fail fast instead of hanging.
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '3s'")

        settings_dict = connection.settings_dict
        other = psycopg2.connect(
            dbname=settings_dict["NAME"], user=settings_dict["USER"], password=settings_dict["PASSWORD"],
            host=settings_dict["HOST"] or "localhost", port=settings_dict["PORT"] or 5432,
        )
        try:
            with other.cursor() as cursor:  # "worker 1" holds a lock on two rows
                cursor.execute(
                    f"SELECT id FROM {ActorImage._meta.db_table} WHERE id::text = ANY(%s) FOR UPDATE", (locked,)
                )
                job = FakeJob(size=0, attempt=3)
                job.process()  # "worker 2"
            claimed = {item["id"] for item in job.lst_items}
        finally:
            other.rollback()
            other.close()

        self.assertEqual(len(claimed), 3)
        self.assertFalse(claimed & set(locked))
        self.assertEqual(
            set(ActorImage.objects.filter(id__in=locked).values_list("status", flat=True)), {StatusEnum.READY}
        )


class FaceEncodingReuseTests(TestCase):
    def setUp(self):
        actor = Actor.objects.create(name="Alice", slug="alice", birthday="March 3, 1980")
        self.image = ActorImage.objects.create(actor=actor, keyword="IMDB", url="http://x/1.jpg", path="/tmp/none.jpg")

    def test_valid_image_stores_its_encoding(self):
        encoding = np.linspace(-0.1, 0.1, 128)
        with mock.patch.object(ActorImageJob, "face_encodings", return_value=[encoding]):
            ActorImageJob._ActorImageJob__is_valid_face(self.image)
        self.image.refresh_from_db()
        self.assertTrue(self.image.is_valid)
        self.assertEqual(len(self.image.face_encoding), 128)
        self.assertTrue(ElasticSearchActorImage.objects.filter(actor_image=self.image).exists())

    def test_image_with_two_faces_is_rejected(self):
        with mock.patch.object(ActorImageJob, "face_encodings", return_value=[np.zeros(128), np.ones(128)]):
            ActorImageJob._ActorImageJob__is_valid_face(self.image)
        self.image.refresh_from_db()
        self.assertFalse(self.image.is_valid)
        self.assertIsNone(self.image.face_encoding)
        self.assertFalse(ElasticSearchActorImage.objects.exists())

    def test_elasticsearch_job_reuses_the_stored_encoding(self):
        self.image.face_encoding = [0.5] * 128
        self.image.save()
        document = ElasticSearchActorImage.objects.create(actor_image=self.image)

        fake_fr = types.SimpleNamespace(
            load_image_file=mock.Mock(return_value=np.zeros((4, 4, 3), dtype=np.uint8)),
            face_locations=mock.Mock(side_effect=AssertionError("must not detect again")),
            face_encodings=mock.Mock(side_effect=AssertionError("must not encode again")),
        )
        with mock.patch.dict(sys.modules, {"face_recognition": fake_fr}), \
                mock.patch("apps.celebrity.jobs.ElasticsearchJob.estimate_age", return_value=30), \
                mock.patch("apps.celebrity.jobs.ElasticsearchJob.Faces") as faces:
            self.assertTrue(ElasticsearchJob(1, 3).internal_process(str(document.id)))

        row = faces.return_value.insert_one.call_args.args[0]
        self.assertEqual(row["face_encoding"], [0.5] * 128)
        self.assertEqual(row["actor_id"], str(self.image.actor.id))
        self.assertEqual((row["age"], row["year"]), (30, 2010))

    def test_photo_year(self):
        self.assertEqual(photo_year("March 3, 1980", 30)[1], 2010)
        self.assertEqual(photo_year("1980", None)[1], None)
        self.assertEqual(photo_year(None, 30), (None, None))
        self.assertEqual(photo_year("not a date", 30), (None, None))
