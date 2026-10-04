"""
Pure ranking helpers used by the search code and the evaluation command.

Nothing here talks to Elasticsearch or loads a model, so it is easy to unit test.
"""
from collections import OrderedDict

# face_recognition's default "same person" tolerance (Euclidean distance).
FACE_DISTANCE_TOLERANCE = 0.6


def l2_score(distance):
    """Elasticsearch kNN score for `similarity: l2_norm`."""
    return 1.0 / (1.0 + distance**2)


def l2_distance(score):
    """Inverse of l2_score."""
    return ((1.0 / score) - 1.0) ** 0.5


def cosine_score(cos):
    """Elasticsearch kNN score for `similarity: cosine`."""
    return (1.0 + cos) / 2.0


def score_to_cosine(score):
    """Inverse of cosine_score."""
    return 2.0 * score - 1.0


# score > ~0.735  <=>  Euclidean distance < 0.6
DEFAULT_FACE_THRESHOLD = round(l2_score(FACE_DISTANCE_TOLERANCE), 3)


def vote_actor(hits, threshold, min_votes=1):
    """
    Pick the actor for one query face from its k nearest stored faces.

    Each actor has many indexed images, so instead of trusting only the single
    nearest image, the hits above ``threshold`` vote for their ``actor_id``.
    Votes are weighted by score (weighted kNN): the actor with the highest summed
    score wins, ties go to the actor with more votes. A plain vote count would let
    several distant faces outvote one near-identical face.

    Returns the winning hit's ``_source`` enriched with ``votes`` and ``score``
    (best score for that actor), or ``None`` when nobody reaches ``min_votes``.
    """
    tally = OrderedDict()
    for hit in hits:
        score = float(hit["_score"])
        if score <= threshold:
            continue
        source = hit["_source"]
        entry = tally.setdefault(
            source["actor_id"],
            {"source": source, "votes": 0, "total": 0.0, "best": 0.0},
        )
        entry["votes"] += 1
        entry["total"] += score
        if score > entry["best"]:
            entry["best"] = score
            entry["source"] = source

    candidates = [e for e in tally.values() if e["votes"] >= min_votes]
    if not candidates:
        return None

    winner = max(candidates, key=lambda e: (e["total"], e["votes"]))
    return {**winner["source"], "votes": winner["votes"], "score": winner["best"]}


def rrf_fuse(ranked_lists, k=60):
    """
    Reciprocal Rank Fusion: ``score(d) = sum(1 / (k + rank_i(d)))``.

    ``ranked_lists`` is a list of lists of document ids (best first). Returns the
    ids ordered by fused score. Ties keep the order of first appearance.
    """
    scores = OrderedDict()
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda doc_id: scores[doc_id], reverse=True)


def chunk_text(text, max_words=120, overlap=30):
    """
    Split a long synopsis into overlapping word windows (passages).

    One vector for a whole long plot averages away the details; several passage
    vectors let a short user description match the part of the plot it describes.
    """
    if overlap >= max_words:
        raise ValueError("overlap must be smaller than max_words")

    words = (text or "").split()
    if len(words) <= max_words:
        return [" ".join(words)] if words else []

    step = max_words - overlap
    passages = []
    for start in range(0, len(words), step):
        passages.append(" ".join(words[start : start + max_words]))
        if start + max_words >= len(words):
            break
    return passages


def best_hit_per_key(hits, key, limit):
    """
    Keep the best-scoring hit per ``_source[key]`` (hits must be sorted best first)
    and return at most ``limit`` of them.
    """
    seen, result = set(), []
    for hit in hits:
        value = hit["_source"].get(key)
        if value in seen:
            continue
        seen.add(value)
        result.append(hit)
        if len(result) >= limit:
            break
    return result


def pick_threshold(scored):
    """
    Choose a score cutoff from labelled results.

    ``scored`` is a list of ``(score, is_correct)`` pairs, one per query, for the
    top answer. A query is "answered" when ``score >= cutoff``. We maximise F1 where
    precision = correct answered / answered and recall = correct answered / all
    correct top answers. Returns ``(threshold, table)`` where ``table`` lists every
    candidate cutoff with its metrics.
    """
    total_correct = sum(1 for _, ok in scored if ok)
    table = []
    best = (None, -1.0)
    for cutoff in sorted({round(s, 4) for s, _ in scored}):
        answered = [(s, ok) for s, ok in scored if s >= cutoff]
        correct = sum(1 for _, ok in answered if ok)
        precision = correct / len(answered) if answered else 0.0
        recall = correct / total_correct if total_correct else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        table.append(
            {
                "threshold": cutoff,
                "answered": len(answered),
                "correct": correct,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )
        if f1 > best[1]:
            best = (cutoff, f1)
    return best[0], table
