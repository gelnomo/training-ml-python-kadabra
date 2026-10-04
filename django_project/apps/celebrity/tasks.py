import logging

from celery import shared_task
from constance import config

from apps.celebrity.jobs.ActorImageJob import ActorImageJob
from apps.celebrity.jobs.ActorJob import ActorJob
from apps.celebrity.jobs.ElasticsearchJob import ElasticsearchJob

logger = logging.getLogger(__name__)


def _run(task, job_class, method, size, attempts, item_id):
    """Run one job method, logging memory usage around it at DEBUG level."""
    # Constance is read when the task runs, not when the module is imported.
    attempts = attempts if attempts is not None else config.CONFIG_ACTOR_ATTEMPTS
    debug = logger.isEnabledFor(logging.DEBUG)
    if debug:
        import memory_profiler as mem_profile

        logger.debug("%s Memory (Before) : %s Mb", task.name, mem_profile.memory_usage())

    getattr(job_class(size, attempts, item_id), method)()

    if debug:
        logger.debug("%s Memory (After) : %s Mb", task.name, mem_profile.memory_usage())


@shared_task(bind=True, name="actor_process")
def actor_process(self, size=100, attempts=None, actor_id=None):
    _run(self, ActorJob, "process", size, attempts, actor_id)


@shared_task(bind=True, name="actor_process_long_task")
def actor_process_long_task(self, size=100, attempts=None, actor_id=None):
    _run(self, ActorJob, "process_long_task", size, attempts, actor_id)


@shared_task(bind=True, name="actor_process_error")
def actor_process_error(self, size=10, attempts=None, actor_id=None):
    _run(self, ActorJob, "process_error", size, attempts, actor_id)


@shared_task(bind=True, name="actor_image_process")
def actor_image_process(self, size=100, attempts=None, actor_image_id=None):
    _run(self, ActorImageJob, "process", size, attempts, actor_image_id)


@shared_task(bind=True, name="actor_image_process_long_task")
def actor_image_process_long_task(self, size=100, attempts=None, actor_image_id=None):
    _run(self, ActorImageJob, "process_long_task", size, attempts, actor_image_id)


@shared_task(bind=True, name="actor_image_process_error")
def actor_image_process_error(self, size=100, attempts=None, actor_image_id=None):
    _run(self, ActorImageJob, "process_error", size, attempts, actor_image_id)


@shared_task(bind=True, name="elasticsearch_actor_images_process")
def elasticsearch_actor_images_process(self, size=100, attempts=None, document_id=None):
    _run(self, ElasticsearchJob, "process", size, attempts, document_id)


@shared_task(bind=True, name="elasticsearch_actor_images_process_long_task")
def elasticsearch_actor_images_process_long_task(self, size=100, attempts=None, document_id=None):
    _run(self, ElasticsearchJob, "process_long_task", size, attempts, document_id)


@shared_task(bind=True, name="elasticsearch_actor_images_process_error")
def elasticsearch_actor_images_process_error(self, size=100, attempts=None, document_id=None):
    _run(self, ElasticsearchJob, "process_error", size, attempts, document_id)


@shared_task(bind=True, name="telegram_process_update", ignore_result=True)
def telegram_process_update(self, content):
    """Handle one Telegram update (queued by the webhook view)."""
    import asyncio

    from apps.botAI.bot_core import TelegramBot

    asyncio.run(TelegramBot.handle_update(content))
