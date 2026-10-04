import logging

from celery import shared_task
from constance import config

from apps.movies.jobs.ElasticsearchJob import ElasticsearchJob
from apps.movies.jobs.MovieJob import MovieJob

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


@shared_task(bind=True, name="movie_process")
def movie_process(self, size=100, attempts=None, movie_id=None):
    _run(self, MovieJob, "process", size, attempts, movie_id)


@shared_task(bind=True, name="movie_process_long_task")
def movie_process_long_task(self, size=100, attempts=None, movie_id=None):
    _run(self, MovieJob, "process_long_task", size, attempts, movie_id)


@shared_task(bind=True, name="movie_process_error")
def movie_process_error(self, size=100, attempts=None, movie_id=None):
    _run(self, MovieJob, "process_error", size, attempts, movie_id)


@shared_task(bind=True, name="elasticsearch_movie_process")
def elasticsearch_movie_process(self, size=100, attempts=None, document_id=None):
    _run(self, ElasticsearchJob, "process", size, attempts, document_id)


@shared_task(bind=True, name="elasticsearch_movie_process_long_task")
def elasticsearch_movie_process_long_task(self, size=100, attempts=None, document_id=None):
    _run(self, ElasticsearchJob, "process_long_task", size, attempts, document_id)


@shared_task(bind=True, name="elasticsearch_movie_process_error")
def elasticsearch_movie_process_error(self, size=100, attempts=None, document_id=None):
    _run(self, ElasticsearchJob, "process_error", size, attempts, document_id)
