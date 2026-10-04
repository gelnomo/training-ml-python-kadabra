"""
Write a skeleton of evaluation cases for movies that are actually indexed.

    python manage.py build_eval_cases ../eval/cases.jsonl --count 80

Each line gets the movie's imdb id and title; you fill in ``text`` (a synopsis in
your own words, the way a user would describe it) and/or ``image`` (a path to a
screenshot of the movie, relative to the JSONL file). Rows left empty are
ignored by ``evaluate_search``.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.document.schema import Movies


class Command(BaseCommand):
    help = "Create an evaluation-cases skeleton from random indexed movies."

    def add_arguments(self, parser):
        parser.add_argument("output", help="JSONL file to create")
        parser.add_argument("--count", type=int, default=80)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--force", action="store_true", help="Overwrite an existing file")

    def handle(self, *args, **options):
        output = Path(options["output"])
        if output.exists() and not options["force"]:
            raise CommandError(f"{output} exists; use --force to overwrite it")

        movies = Movies()
        movies.ensure()
        hits = movies.es.search(
            index=movies.ALIAS,
            query={
                "function_score": {
                    "query": {"match_all": {}},
                    "random_score": {"seed": options["seed"], "field": "_seq_no"},
                }
            },
            size=options["count"],
            _source=["title", "year", "imdb_id"],
        )["hits"]["hits"]
        if not hits:
            raise CommandError(f"No movies indexed in {movies.ALIAS}")

        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for number, hit in enumerate(hits, start=1):
                source = hit["_source"]
                case = {
                    "id": f"case-{number:03d}",
                    "expected_imdb_id": source["imdb_id"],
                    "title": source["title"],
                    "year": source["year"],
                    "text": "",
                    "image": "",
                }
                handle.write(json.dumps(case, ensure_ascii=False) + "\n")

        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {len(hits)} cases to {output}. Fill in `text` and/or `image`, then run "
                f"`manage.py evaluate_search --cases {output}`."
            )
        )
