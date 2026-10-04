# Kadabra!
## Shazam for movies!
__collaborative repository__

This project builds on and improves [**Kadabra_public**](https://github.com/ijzepeda/Kadabra_public), a collaborative project I contributed to.
It continues the Django backend with:

- **FilmSleuth**: a Telegram bot that identifies a movie from a **photo** (face recognition + Elasticsearch vector search) or from a **text synopsis** (Universal Sentence Encoder + kNN search).
- A set of performance, reliability and security fixes on top of the original code.

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for how the Elasticsearch vector search works (HNSW kNN, actor filters, weighted face voting, hybrid ranking, passages, CLIP scene search, compression).

## Project layout

```
django_project/
├── apps/
│   ├── botAI/        # Telegram bot logic, SearchImage / SearchScene / SearchText
│   ├── celebrity/    # Actors, actor images, face indexing jobs, webhook views, Celery tasks
│   ├── movies/       # Movies, movie-actor relations, movie/passage/poster indexing jobs
│   └── document/     # Elasticsearch indices, encoders, ranking helpers, management commands
└── ms_data_mining/   # Django settings, Celery app + beat schedule, job base class
eval/                 # Search evaluation cases (see eval/README.md)
docs/                 # Architecture notes
docker-compose.yml    # PostgreSQL, Redis, Elasticsearch for local development
```

## Running it locally

```bash
docker compose up -d                       # PostgreSQL, Redis, Elasticsearch 8.8
cp .env.example .env && export SECRETS_PATH_FILE=$PWD/.env
pip install -r requirements.txt
cd django_project
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
celery -A ms_data_mining worker -l info    # runs the jobs and the bot replies
celery -A ms_data_mining beat -l info      # schedules the jobs
```

To register the Telegram webhook, log in to `/admin/` as a staff user and open `/bot/webhook/subscribe`.
The webhook only queues each update. A Celery **worker must be running** for the bot to reply.

## Search management commands

| Command | What it does |
|---|---|
| `rebuild_indices faces\|movies\|passages\|posters [--source INDEX] [--reembed]` | Builds a new index version and switches its alias with no downtime. Use `--source celebrity` / `--source movies_search` once, to migrate the old indices. |
| `build_eval_cases ../eval/cases.jsonl --count 80` | Writes a skeleton of evaluation cases from indexed movies, for you to fill in. |
| `evaluate_search --cases ../eval/cases.jsonl [--mode vector\|hybrid\|passages]` | Reports hit@1, hit@3 and MRR, and suggests `THRESHOLD_TEXT`. |
| `evaluate_search --faces 300` | Face recognition accuracy (leave-one-out, no labels needed) and a suggested `THRESHOLD_IMAGE`. |

## Tests

```bash
docker compose up -d db elasticsearch
cd django_project
ELASTICSEARCH_TEST_HOST=http://localhost:9200 python manage.py test --settings=ms_data_mining.settings_test
```

The tests use PostgreSQL (`TEST_DATABASE_URL`, which defaults to the docker-compose database), because the job queue relies on `SELECT … FOR UPDATE SKIP LOCKED`. Without `ELASTICSEARCH_TEST_HOST`, the Elasticsearch integration tests are skipped. TensorFlow, dlib, OpenCV and DeepFace are imported lazily, so the tests don't need them.

## Environment variables

All of them are listed with comments in [`.env.example`](.env.example). The bot-related ones:

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `BOT_URL` | Public HTTPS URL of `/bot/webhook/` |
| `BOT_SECRET_TOKEN` | *(recommended)* Secret Telegram sends back on every webhook call. Requests without it are rejected. |
| `TEXT_EMBEDDING_MODEL` | `use-large` (default), `minilm` or `minilm-multilingual` (also understands Spanish). Changing it requires `rebuild_indices movies --reembed`. |
| `PRELOAD_NLP_MODEL` | Load the text model when the process starts instead of on first use |
| `INDEX_MOVIE_PASSAGES` / `INDEX_MOVIE_POSTERS` | Also index synopsis passages / poster vectors (CLIP) |
| `ELASTICSEARCH_VECTOR_ELEMENT_TYPE` | `float` (default) or `byte` (int8 vectors, 4× smaller) |

## License

Released under the [MIT License](LICENSE).
