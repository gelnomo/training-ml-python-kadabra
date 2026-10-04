# `django_project`: this repo vs. Kadabra_public

This repository continues the work on the Django backend of
[ijzepeda/Kadabra_public](https://github.com/ijzepeda/Kadabra_public), a collaborative project I contributed to.
This page lists how `django_project/` here differs from `django_project/` in that repository.
It covers only the Django project. The notebooks in Kadabra_public (`nlp/`, `Save Model techniques/`) are not part of this repo.

The comparison was made against the latest commit of Kadabra_public's default branch (`ba70894`, "Update README.md").

## 1. Features added here (not in Kadabra_public)

| Area | What was added |
|---|---|
| **Telegram bot ("FilmSleuth")** | `apps/botAI/bot_core.py`: a webhook-based bot (`python-telegram-bot` 20) with the commands `/start`, `/list` and `/cancel`. You send it a **photo** or a **text synopsis** and it replies with the most likely movie. |
| **Search by image** | `apps/botAI/search_image.py`: computes `face_recognition` encodings from the photo and runs a cosine-similarity search against the `celebrity` Elasticsearch index. |
| **Search by text** | `apps/botAI/search_text.py`: NLTK preprocessing (tokenize, POS tag, lemmatize, remove stop words), then a kNN search on the `movies_search` index using Universal Sentence Encoder (512-d) embeddings. Results can be filtered by the actors recognised in the photo and by their estimated year. |
| **Movie vector index** | New `ElasticSearchMovie` model + migration `0010`, `apps/movies/jobs/ElasticsearchJob.py`, the Celery tasks `elasticsearch_movie_process*`, an admin page and a delete signal. |
| **Shared ES schema module** | `apps/celebrity/document/schema.py` moved to `apps/document/schema.py` and extended with a `Movies` index (dense_vector, nested celebrities) and an `age` / `birthday` / `year` mapping on `Faces`. |
| **Age estimation** | `apps/celebrity/jobs/ElasticsearchJob.py` estimates the actor's age with DeepFace and stores the estimated **year** the photo was taken (birthday + age). |
| **Birthday scraping** | `ActorJob` gets the actor's birth date from IMDb (ignoring death dates) before it downloads images. |
| **Bot URLs** | `apps/celebrity/urls.py` → `/bot/webhook/`, `/bot/webhook/subscribe`, `/bot/webhook/unsubscribe`. |
| **Settings** | `django_celery_results`, `django_celery_beat`, `adrf` (async DRF views), `MEDIA_*`, `CSRF_TRUSTED_ORIGINS`, Redis-backed Constance, the new Constance keys (`K_TEXT`, `THRESHOLD_TEXT`, `THRESHOLD_IMAGE`, `THRESHOLD_YEAR`, `SIZE_MOVIE_LISTING`, `MOVIE_LIST_TIME_*`), ES shard/replica settings, `BOT_*`, and a `.env` path read from `SECRETS_PATH_FILE`. |
| **Admin** | `raw_id_fields` and more `search_fields` on the actor-image admin pages, and `imdb_id` searchable on `Actor`. |

## 2. Behaviour changed compared with Kadabra_public

- **Celery beat:** only the `elasticsearch_*_process` tasks are enabled by default. The scraping tasks (`actor_*`, `movie_*`) are disabled.
- **Task names:** `elasticsearch_process*` was renamed to `elasticsearch_actor_images_process*`.
- **Batch sizes:** the default batch `size` of the tasks went from `0` (unlimited) to `100`.
- **`download_page()`:** returns `None` on failure instead of an empty `BeautifulSoup`.
- **Google Images fallback:** the fallback in `ActorJob` is commented out, so only IMDb images are used.
- **`ActorImageJob`:** creates the target folder if it is missing.
- **`MovieJob`:** fixes the decoding of special characters, appends the IMDb synopsis to the description and queues the movie for Elasticsearch indexing.
- **Dependencies:** `requirements.txt` adds the ML/NLP stack (TensorFlow 2.13, TF-Hub, PyTorch, sentence-transformers, spaCy, NLTK, TextBlob) plus `python-telegram-bot`, `adrf`, and `django-celery-beat` / `django-celery-results`. Celery goes from 5.2.7 to 5.3.1.
- **Model file:** `django_project/age_detect_cnn_model.h5` (about 5 MB) was added. No Python code in the project references it.

## 3. Optimisations and fixes in this repo

These are code-quality, performance and security improvements on top of section 1.

### Performance
- **Lazy model loading.** `settings.py` used to load the Universal Sentence Encoder at import time, so every `manage.py` command and every Celery beat/worker start loaded TensorFlow. The model now loads on first use, behind a thread-safe singleton. To warm it up when the app starts, set `PRELOAD_NLP_MODEL=True`.
- **Batched embeddings.** `Movies.insert_many()` now encodes descriptions in batches of 64 instead of making one model call per movie.
- **Fewer Elasticsearch round trips.** Both indexing jobs called `exists()` before `update()` / `index()`. They now call `index()` directly, which creates or replaces the document.
- **Fewer database reads.**
  - `InterfaceJob` loads only primary keys (`values_list("id")`) instead of full rows. Movie rows include a large JSON payload.
  - The indexing jobs use `select_related` to avoid N+1 queries.
- **Shared `/list` cache.** The `/list` reply was cached once per Telegram user. It is now cached once for everyone, because the content is identical.
- **Cheaper image indexing.** DeepFace age estimation is skipped when the image has no face.
- **Faster stop-word lookups.** Stop words are loaded once per process into a `frozenset` instead of a list built on every request.

### Bugs fixed
- **`movies/signals.py`:** deleting an `ElasticSearchMovie` raised `AttributeError` because the code read `instance.actor_image`, a field that model doesn't have. This broke deletes in the admin.
- **`MovieJob.__create_actors`:** an off-by-one (`key <= len(...)`) raised `IndexError` outside the `try`, and the job also crashed when `starts_id` or `starts_name` was `None`.
- **`MovieJob.__download_movie_info`:**
  - Years were only detected between 1900 and 2013. The range now goes up to next year.
  - A movie without `imdb_id` crashed the job.
- **`MovieJob.__get_synopsis`:** when the page download failed (`None`), the movie was never queued for Elasticsearch indexing.
- **`MovieJob.__change_chars`:** ~130 hard-coded `\xNN` replacements were replaced by a generic UTF-8 decoder. It gives identical output for all Latin-1 characters, and it also decodes characters the table missed, such as `’`, which used to stay as `\xe2\x80\x99`.
- **Constance values read at import time:** `THRESHOLD_TEXT`, `THRESHOLD_IMAGE` and `SIZE_MOVIE_LISTING` were evaluated once, when the module was imported, so changes in the admin were ignored until a restart. They are now read on every call.
- **`SearchText`:**
  - It always returned some text, so the bot's "not enough information" reply never appeared. Instead, users got `Best Result: None`.
  - Duplicate words were removed with `set()`, which shuffled the word order.
- **Unescaped HTML:** movie titles and actor names were sent to Telegram in HTML mode without escaping. A title containing `&` or `<` made the message fail.
- **`SearchImage`:** PNG/RGBA photos are converted to RGB before face encoding.
- **Webhook updates without a message:** an edited message, for example, caused a second exception inside the error handler.
- **Settings:**
  - `CSRF_TRUSTED_ORIGINS` crashed at startup if the variable was missing.
  - `ELASTICSEARCH_NUM_*` were read as strings.
- **Timeouts:** network calls (`download_page`, OMDb API) had no timeout, so a stalled request could block a Celery worker forever. The `ActorImageJob` file and HTTP handles are now closed with `with` blocks.

### Security
- **Webhook secret.** Set `BOT_SECRET_TOKEN` and the webhook is registered with Telegram's `secret_token`. Calls to `/bot/webhook/` without the matching `X-Telegram-Bot-Api-Secret-Token` header are then rejected.
- **Staff-only webhook management.** `/bot/webhook/subscribe` and `/bot/webhook/unsubscribe` were public, so anyone could disconnect the bot. They now require a staff user: log in to `/admin/` first, or send a staff JWT.

### Not changed (worth a follow-up)
- **Pin `deepface` and `pandas`.** Both are imported but were missing from `requirements.txt`. They were added unpinned and still need versions that are compatible with TensorFlow 2.13.
- **Unused model file.** `age_detect_cnn_model.h5` is not used by the code. Consider removing it or moving it to Git LFS.
- **Byte-string scraping.** `download_page()` still turns responses into `str(bytes)`, and the IMDb scrapers depend on that format (for example, `image[r"\nsrc"]`). Decoding the HTML properly means updating the CSS selectors too.
