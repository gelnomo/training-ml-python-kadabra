"""
Measure search quality so thresholds and models are chosen with numbers.

Labelled cases (see eval/README.md):
    python manage.py evaluate_search --cases ../eval/cases.jsonl
    python manage.py evaluate_search --cases ../eval/cases.jsonl --mode hybrid
    python manage.py evaluate_search --cases ../eval/cases.jsonl --no-preprocess

Faces, without labelling anything (leave-one-out over the indexed images):
    python manage.py evaluate_search --faces 300

Add ``--output report.json`` to save every number.
"""
import json
import random
from pathlib import Path

from constance import config
from django.core.management.base import BaseCommand, CommandError

from apps.document.ranking import pick_threshold, vote_actor
from apps.document.schema import Faces


def summarize(ranks, k):
    """``ranks``: 1-based rank of the expected answer per query, or None if missing."""
    n = len(ranks)
    if not n:
        return {"queries": 0}
    return {
        "queries": n,
        "hit@1": sum(1 for r in ranks if r == 1) / n,
        f"hit@{k}": sum(1 for r in ranks if r is not None and r <= k) / n,
        "mrr": sum(1.0 / r for r in ranks if r) / n,
    }


class Command(BaseCommand):
    help = "Evaluate image/text search quality and suggest score thresholds."

    def add_arguments(self, parser):
        parser.add_argument("--cases", help="JSONL file with labelled queries")
        parser.add_argument("--k", type=int, default=3, help="Report hit@k (default 3)")
        parser.add_argument("--mode", choices=["vector", "hybrid", "passages"], help="Override TEXT_SEARCH_MODE")
        parser.add_argument("--no-preprocess", action="store_true", help="Encode the raw text (no NLTK cleaning)")
        parser.add_argument("--faces", type=int, default=0, help="Leave-one-out test on N indexed faces")
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--output", help="Write the full report as JSON")

    def handle(self, *args, **options):
        if not options["cases"] and not options["faces"]:
            raise CommandError("Pass --cases FILE and/or --faces N")

        report = {}
        if options["cases"]:
            report["cases"] = self.evaluate_cases(options)
        if options["faces"]:
            report["faces"] = self.evaluate_faces(options)

        if options["output"]:
            Path(options["output"]).write_text(json.dumps(report, indent=2, default=str))
            self.stdout.write(f"Report written to {options['output']}")

    # ---- labelled cases ------------------------------------------------------------
    @staticmethod
    def load_cases(path):
        path = Path(path)
        if not path.exists():
            raise CommandError(f"{path} not found")
        cases = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            case = json.loads(line)
            if not (case.get("text") or case.get("image")):
                continue  # skeleton rows not filled in yet
            if "expected_imdb_id" not in case:
                raise CommandError(f"{path}:{number}: missing expected_imdb_id (use null for a negative case)")
            if case.get("image"):
                case["image"] = str((path.parent / case["image"]).resolve())
            case.setdefault("id", f"line-{number}")
            cases.append(case)
        return cases

    def run_case(self, case, options, depth):
        from PIL import Image

        from apps.botAI.search_image import SearchImage, SearchScene
        from apps.botAI.search_text import SearchText

        actors, results, used = [], [], None
        image = Image.open(case["image"]) if case.get("image") else None
        if image is not None:
            actors = SearchImage(image).process()

        text = case.get("text")
        if text or actors:
            # threshold=0: keep every candidate, the sweep below picks the cutoff.
            search = SearchText(
                text,
                actors,
                threshold=0,
                mode=options["mode"],
                k=depth,
                preprocess=False if options["no_preprocess"] else None,
            )
            results = search.search()
            used = "text" if text else "actors"
        elif image is not None and config.SCENE_SEARCH_ENABLED:
            results = SearchScene(image, threshold=0, k=depth).search()
            used = "scene"

        # A null expected_imdb_id is a negative case: the movie is not in the
        # collection, so the right behaviour is to answer nothing.
        expected = (case["expected_imdb_id"] or "").strip().lower() or None
        ids = [str(r["imdb_id"]).strip().lower() for r in results]
        rank = ids.index(expected) + 1 if expected in ids else None
        return {
            "negative": expected is None,
            "id": case["id"],
            "kind": ("image+text" if text else "image") if image is not None else "text",
            "scored_by": used,
            "actors": [a["name"] for a in actors],
            "rank": rank,
            "top": results[0] if results else None,
        }

    def evaluate_cases(self, options):
        cases = self.load_cases(options["cases"])
        if not cases:
            raise CommandError("No filled-in cases (need expected_imdb_id and text and/or image)")
        k = options["k"]
        depth = max(k, 10)

        rows = []
        for case in cases:
            try:
                rows.append(self.run_case(case, options, depth))
            except Exception as ex:  # one broken case shouldn't stop the run
                self.stderr.write(f"{case['id']}: {ex}")

        report = {"settings": {"mode": options["mode"] or config.TEXT_SEARCH_MODE, "k": k}}
        self.stdout.write(self.style.MIGRATE_HEADING(f"Labelled cases ({len(rows)})"))
        positives = [r for r in rows if not r["negative"]]
        for kind in ("text", "image", "image+text"):
            subset = [r for r in positives if r["kind"] == kind]
            if not subset:
                continue
            metrics = summarize([r["rank"] for r in subset], k)
            report[kind] = metrics
            self.stdout.write(
                f"  {kind:<11} n={metrics['queries']:<4} hit@1={metrics['hit@1']:.2f} "
                f"hit@{k}={metrics[f'hit@{k}']:.2f} mrr={metrics['mrr']:.2f}"
            )

        # Thresholds only make sense for vector scores (text or scene search).
        # The top answer of a negative case is always wrong, so negatives teach the
        # sweep which scores to reject.
        for scored_by, setting in (("text", "THRESHOLD_TEXT"), ("scene", "THRESHOLD_SCENE")):
            subset = [r for r in rows if r["scored_by"] == scored_by and r["top"]]
            scored = [(r["top"]["score"], r["rank"] == 1) for r in subset]
            if len(scored) < 5:
                continue
            threshold, table = pick_threshold(scored)
            current = getattr(config, setting)
            negatives = [r for r in subset if r["negative"]]
            report[f"suggested_{setting}"] = threshold
            report[f"{setting}_table"] = table
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Suggested {setting} = {threshold} (current {current}, based on {len(scored)} queries, "
                    f"{len(negatives)} negative)"
                )
            )
            if negatives:
                for label, value in (("current", current), ("suggested", threshold)):
                    rejected = sum(1 for r in negatives if r["top"]["score"] < value)
                    self.stdout.write(f"  Negative cases rejected at the {label} {setting}: {rejected}/{len(negatives)}")
            else:
                self.stdout.write(
                    "  No negative cases: add some (expected_imdb_id null) so the threshold also learns what to reject."
                )

        misses = [r for r in positives if r["rank"] != 1]
        if misses:
            self.stdout.write("  Misses (rank of the expected movie, top answer):")
            for r in misses[:20]:
                top = r["top"]["title"] if r["top"] else "-"
                self.stdout.write(f"    {r['id']}: rank={r['rank']} top={top!r} actors={r['actors']}")
        report["rows"] = rows
        return report

    # ---- faces (no labelling needed) ---------------------------------------------------
    def evaluate_faces(self, options):
        """
        Leave-one-out: take an indexed face, search with its own vector while
        excluding that document, and check the vote returns the same actor.
        Only actors with at least 2 indexed images can be found this way.
        """
        faces = Faces()
        faces.ensure()
        response = faces.es.search(
            index=faces.ALIAS,
            query={"function_score": {"query": {"match_all": {}}, "random_score": {"seed": options["seed"], "field": "_seq_no"}}},
            size=options["faces"],
            _source=["actor_id", "face_encoding"],
        )
        samples = response["hits"]["hits"]
        if not samples:
            raise CommandError(f"No documents in {faces.ALIAS}")

        actor_ids = list({hit["_source"]["actor_id"] for hit in samples})
        counts = faces.es.search(
            index=faces.ALIAS,
            size=0,
            query={"terms": {"actor_id": actor_ids}},
            aggs={"per_actor": {"terms": {"field": "actor_id", "size": len(actor_ids)}}},
        )["aggregations"]["per_actor"]["buckets"]
        images_per_actor = {b["key"]: b["doc_count"] for b in counts}
        samples = [h for h in samples if images_per_actor.get(h["_source"]["actor_id"], 0) >= 2]
        random.Random(options["seed"]).shuffle(samples)

        threshold = config.THRESHOLD_IMAGE
        scored, correct_at_threshold = [], 0
        for hit in samples:
            hits = faces.query_face([hit["_source"]["face_encoding"]], exclude_ids=[hit["_id"]])[0]
            winner = vote_actor(hits, threshold=0.0)
            if winner is None:
                continue
            ok = winner["actor_id"] == hit["_source"]["actor_id"]
            scored.append((winner["score"], ok))
            winner_at_threshold = vote_actor(hits, threshold, config.FACE_MIN_VOTES)
            if winner_at_threshold and winner_at_threshold["actor_id"] == hit["_source"]["actor_id"]:
                correct_at_threshold += 1

        n = len(samples)
        report = {
            "queries": n,
            "accuracy_no_threshold": sum(1 for _, ok in scored if ok) / n if n else 0.0,
            "recognised_correctly_at_current_threshold": correct_at_threshold / n if n else 0.0,
            "current_threshold": threshold,
        }
        self.stdout.write(self.style.MIGRATE_HEADING(f"Faces leave-one-out ({n} images)"))
        self.stdout.write(
            f"  correct actor (no threshold) = {report['accuracy_no_threshold']:.2f}\n"
            f"  correct and above THRESHOLD_IMAGE={threshold} = {report['recognised_correctly_at_current_threshold']:.2f}"
        )
        if len(scored) >= 5:
            suggested, table = pick_threshold(scored)
            report["suggested_THRESHOLD_IMAGE"] = suggested
            report["THRESHOLD_IMAGE_table"] = table
            self.stdout.write(self.style.SUCCESS(f"  Suggested THRESHOLD_IMAGE = {suggested}"))
        return report
