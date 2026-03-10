from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.models import Comment, MetricSnapshot, Post


class ContentOptimizer:
    """
    Simple strategy optimizer:
    - Find which hashtags correlate with higher likes/comments
    - Track common positive comment intents
    - Update strategy knobs (hashtag_pool, tone hints)
    """

    def learn_patch(self, *, session: Session) -> dict[str, Any]:
        posts = session.scalars(select(Post).order_by(desc(Post.created_at)).limit(50)).all()
        if not posts:
            return {}

        # Latest metrics per post
        metrics_by_post: dict[int, MetricSnapshot] = {}
        for p in posts:
            snap = session.scalar(
                select(MetricSnapshot)
                .where(MetricSnapshot.post_id == p.id)
                .order_by(desc(MetricSnapshot.created_at))
                .limit(1)
            )
            if snap:
                metrics_by_post[p.id] = snap

        hashtag_scores: defaultdict[str, list[float]] = defaultdict(list)
        for p in posts:
            snap = metrics_by_post.get(p.id)
            if not snap:
                continue
            score = float(snap.likes + 2 * snap.comments + snap.collects)
            for h in (p.hashtags or []):
                hashtag_scores[h].append(score)

        ranked = sorted(
            ((h, sum(vals) / max(1, len(vals))) for h, vals in hashtag_scores.items()),
            key=lambda x: x[1],
            reverse=True,
        )
        top_hashtags = [h for h, _ in ranked[:10]]

        # Comment intent stats
        recent_comments = session.scalars(select(Comment).order_by(desc(Comment.created_at)).limit(200)).all()
        intent_counts = Counter([c.intent for c in recent_comments if c.intent])
        sentiment_counts = Counter([c.sentiment for c in recent_comments if c.sentiment])

        patch: dict[str, Any] = {}
        if top_hashtags:
            patch["hashtag_pool"] = top_hashtags
        if intent_counts:
            patch["top_comment_intents"] = dict(intent_counts.most_common(5))
        if sentiment_counts:
            patch["sentiment_mix"] = dict(sentiment_counts)

        # A tiny nudge: if lots of questions, encourage clearer steps
        if intent_counts.get("question", 0) >= 10:
            patch["tone"] = "更清晰、步骤更细、先给结论再展开"
        return patch

