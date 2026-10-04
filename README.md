# Kadabra!
## Shazam for movies!
__collaborative repository__

This project builds on and improves [**Kadabra_public**](https://github.com/ijzepeda/Kadabra_public), a collaborative project I contributed to.
It continues the Django backend with:

- **FilmSleuth**: a Telegram bot that identifies a movie from a **photo** (face recognition + Elasticsearch vector search) or from a **text synopsis** (Universal Sentence Encoder + kNN search).
- A set of performance, reliability and security fixes on top of the original code.

See **[COMPARISON.md](COMPARISON.md)** for a detailed list of the differences from Kadabra_public and the optimisations made here.
See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for how the Elasticsearch vector search works and the improvement roadmap.

## Project layout

```
django_project/
├── apps/
│   ├── botAI/        # Telegram bot, search by image / text, model loader
│   ├── celebrity/    # Actors, actor images, face indexing jobs, bot URLs
│   ├── movies/       # Movies, movie-actor relations, movie indexing jobs
│   └── document/     # Elasticsearch index definitions (Faces, Movies)
└── ms_data_mining/   # Django settings, Celery app + beat schedule, helpers
```

## Environment variables (bot related)

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `BOT_URL` | Public HTTPS URL of `/bot/webhook/` |
| `BOT_SECRET_TOKEN` | *(optional, recommended)* Secret Telegram sends back on every webhook call. Requests without it are rejected. |
| `PRELOAD_NLP_MODEL` | *(optional, default `False`)* Set to `True` on the web process to load the sentence encoder at startup instead of on the first request |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated list of trusted origins |

To register the webhook, log in to `/admin/` as a staff user and open `/bot/webhook/subscribe`.
