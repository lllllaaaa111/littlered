from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database.models import (
    Comment,
    ImageAsset,
    MetricSnapshot,
    Post,
    PostStatus,
    PublishEvent,
    StrategyState,
    Topic,
)


def upsert_strategy(session: Session, patch: dict) -> StrategyState:
    row = session.scalar(select(StrategyState).order_by(desc(StrategyState.id)).limit(1))
    if row is None:
        row = StrategyState(state={})
        session.add(row)
        session.flush()
    merged = dict(row.state or {})
    merged.update(patch or {})
    row.state = merged
    return row


def get_strategy(session: Session) -> dict:
    row = session.scalar(select(StrategyState).order_by(desc(StrategyState.id)).limit(1))
    return dict(row.state) if row and row.state else {}


def create_topic(session: Session, *, title: str, angle: str | None, keywords: list[str], rationale: str | None, score: float) -> Topic:
    t = Topic(title=title, angle=angle, keywords=keywords, rationale=rationale, score=score)
    session.add(t)
    session.flush()
    return t


def create_post(
    session: Session,
    *,
    topic_id: int,
    title: str,
    body: str,
    hashtags: list[str],
    language: str = "zh",
    style: dict | None = None,
    version: int = 1,
) -> Post:
    p = Post(
        topic_id=topic_id,
        version=version,
        status=PostStatus.drafted,
        title=title,
        body=body,
        hashtags=hashtags,
        language=language,
        style=style or {},
    )
    session.add(p)
    session.flush()
    return p


def attach_image(
    session: Session,
    *,
    post_id: int,
    prompt: str,
    negative_prompt: str | None,
    model_id: str,
    seed: int | None,
    width: int,
    height: int,
    steps: int,
    guidance_scale: float,
    file_path: str,
) -> ImageAsset:
    img = ImageAsset(
        post_id=post_id,
        prompt=prompt,
        negative_prompt=negative_prompt,
        model_id=model_id,
        seed=seed,
        width=width,
        height=height,
        steps=steps,
        guidance_scale=guidance_scale,
        file_path=file_path,
    )
    session.add(img)
    post = session.get(Post, post_id)
    if post:
        post.status = PostStatus.image_generated
    session.flush()
    return img


def add_publish_event(
    session: Session,
    *,
    post_id: int,
    success: bool,
    external_post_id: str | None = None,
    external_url: str | None = None,
    error: str | None = None,
) -> PublishEvent:
    ev = PublishEvent(
        post_id=post_id,
        success=success,
        external_post_id=external_post_id,
        external_url=external_url,
        error=error,
    )
    session.add(ev)
    post = session.get(Post, post_id)
    if post:
        post.status = PostStatus.published if success else PostStatus.failed
    session.flush()
    return ev


def add_metric_snapshot(session: Session, *, post_id: int, external_post_id: str | None, metrics: dict) -> MetricSnapshot:
    snap = MetricSnapshot(
        post_id=post_id,
        external_post_id=external_post_id,
        views=int(metrics.get("views", 0)),
        likes=int(metrics.get("likes", 0)),
        collects=int(metrics.get("collects", 0)),
        comments=int(metrics.get("comments", 0)),
        shares=int(metrics.get("shares", 0)),
    )
    session.add(snap)
    session.flush()
    return snap


def add_comments(session: Session, *, post_id: int, external_post_id: str | None, comments: list[dict]) -> list[Comment]:
    out: list[Comment] = []
    for c in comments:
        ext_id = str(c.get("external_comment_id") or c.get("id") or "")
        if not ext_id:
            continue
        row = Comment(
            post_id=post_id,
            external_post_id=external_post_id,
            external_comment_id=ext_id,
            author=c.get("author"),
            content=c.get("content", ""),
            sentiment=c.get("sentiment"),
            intent=c.get("intent"),
        )
        session.add(row)
        out.append(row)
    session.flush()
    return out

