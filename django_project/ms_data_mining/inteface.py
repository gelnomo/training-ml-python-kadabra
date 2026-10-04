import logging
import uuid
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from apps.celebrity.enums import StatusEnum

logger = logging.getLogger(__name__)


class InterfaceJob:
    JOB_MODEL = None

    def __init__(self, size: int, attempt: int, job_id: uuid = None):
        self.size = size
        self.attempt = attempt
        self.job_id = str(job_id) if job_id else None
        self.lst_items = []
        if not self.JOB_MODEL:
            raise Exception("JOB_MODEL is missing")

    def process(self):
        if self.job_id is not None:
            query = Q(id=self.job_id)
        else:
            query = Q(status=StatusEnum.READY) & Q(attempt__lte=self.attempt)

        self.__claim(query, ("attempt", "created"), status=StatusEnum.RUNNING)

        self.__process_item()

    def __process_item(self):
        for item in self.lst_items:
            try:
                is_completed = self.internal_process(item["id"])

                if is_completed:
                    self.JOB_MODEL.objects.filter(id=item["id"]).update(
                        status=StatusEnum.COMPLETED,
                        updated=timezone.now(),
                    )
            except Exception:
                logger.exception("%s %s failed", self.JOB_MODEL.__name__, item["id"])
                self.JOB_MODEL.objects.filter(id=item["id"]).update(
                    status=StatusEnum.ERROR,
                    updated=timezone.now(),
                )

            self.update_task(item["id"])

    def __claim(self, query, order_by, limit=True, **changes):
        """
        Select the matching rows and apply ``changes`` to them in one transaction.

        ``select_for_update(skip_locked=True)`` locks the selected rows, and rows
        already locked by another worker are skipped, so two overlapping Celery runs
        never pick the same items. Only the primary keys are fetched: the job models
        can hold large JSON payloads.
        """
        with transaction.atomic():
            queryset = (
                self.JOB_MODEL.objects.select_for_update(skip_locked=True)
                .filter(query)
                .order_by(*order_by)
            )
            if limit and self.size:
                queryset = queryset[: self.size]
            ids = [str(item_id) for item_id in queryset.values_list("id", flat=True)]
            if ids:
                self.JOB_MODEL.objects.filter(id__in=ids).update(
                    updated=timezone.now(), **changes
                )
        self.lst_items.extend({"id": item_id} for item_id in ids)

    def internal_process(self, item_id: str) -> bool:
        pass

    def update_task(self, item_id: str):
        pass

    def __updated_item(self) -> None:
        for item in self.lst_items:
            self.update_task(item["id"])

    def process_expired(self):
        self.lst_items = []
        query = Q(status=StatusEnum.ERROR) & Q(attempt__gte=self.attempt)

        self.__claim(query, ("created",), limit=False, status=StatusEnum.EXPIRED)

    def process_error(self):
        if self.job_id is not None:
            query = Q(id=self.job_id)
        else:
            query = Q(status=StatusEnum.ERROR) & Q(attempt__lt=self.attempt)

        self.__claim(
            query, ("created",), status=StatusEnum.READY, attempt=F("attempt") + 1
        )

        self.process_expired()
        self.__updated_item()

    def process_long_task(self):
        if self.job_id is not None:
            query = Q(id=self.job_id)
        else:
            query = Q(status=StatusEnum.RUNNING) & Q(
                updated__lte=(timezone.now() + timezone.timedelta(days=-1))
            )

        self.__claim(query, ("created",), status=StatusEnum.READY, attempt=0)
        self.__updated_item()
