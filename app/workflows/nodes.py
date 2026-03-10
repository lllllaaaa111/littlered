from __future__ import annotations

from app.database.engine import db_session
from app.database.repo import (
    add_comments,
    add_metric_snapshot,
    add_publish_event,
    attach_image,
    create_post,
    create_topic,
    get_strategy,
    upsert_strategy,
)
from app.services.comment_analyzer import CommentAnalyzer
from app.services.content_optimizer import ContentOptimizer
from app.services.image_generator import ImageGenerator
from app.services.metrics_collector import MetricsCollector
from app.services.publisher import XiaohongshuPublisher
from app.services.topic_post_generator import TopicPostGenerator
from app.workflows.state import AgentState


def load_strategy(state: AgentState) -> AgentState:
    with db_session() as s:
        state.strategy = get_strategy(s)
    return state


def generate_topics(state: AgentState) -> AgentState:
    gen = TopicPostGenerator(strategy=state.strategy)
    topics = gen.generate_topics(n=state.batch_size)
    with db_session() as s:
        for t in topics:
            row = create_topic(
                s,
                title=t["title"],
                angle=t.get("angle"),
                keywords=t.get("keywords", []),
                rationale=t.get("rationale"),
                score=float(t.get("score", 0.0)),
            )
            state.topic_ids.append(row.id)
    state.outputs["topics"] = topics
    return state


def generate_posts(state: AgentState) -> AgentState:
    gen = TopicPostGenerator(strategy=state.strategy)
    with db_session() as s:
        for topic_id in state.topic_ids:
            post = gen.generate_post(topic_id=topic_id, session=s)
            row = create_post(
                s,
                topic_id=topic_id,
                title=post["title"],
                body=post["body"],
                hashtags=post.get("hashtags", []),
                language=post.get("language", "zh"),
                style=post.get("style") or {},
            )
            state.post_ids.append(row.id)
    return state


def generate_images(state: AgentState) -> AgentState:
    img_gen = ImageGenerator()
    with db_session() as s:
        for post_id in state.post_ids:
            result = img_gen.generate_for_post(post_id=post_id, session=s)
            attach_image(
                s,
                post_id=post_id,
                prompt=result["prompt"],
                negative_prompt=result.get("negative_prompt"),
                model_id=result["model_id"],
                seed=result.get("seed"),
                width=result["width"],
                height=result["height"],
                steps=result["steps"],
                guidance_scale=result["guidance_scale"],
                file_path=result["file_path"],
            )
    return state


def publish_posts(state: AgentState) -> AgentState:
    pub = XiaohongshuPublisher()
    with db_session() as s:
        for post_id in state.post_ids:
            try:
                res = pub.publish(post_id=post_id, session=s)
                add_publish_event(
                    s,
                    post_id=post_id,
                    success=True,
                    external_post_id=res.get("external_post_id"),
                    external_url=res.get("external_url"),
                )
                state.published_post_ids.append(post_id)
            except Exception as e:
                add_publish_event(s, post_id=post_id, success=False, error=str(e))
                state.failures.append({"post_id": post_id, "error": str(e)})
    return state


def collect_metrics(state: AgentState) -> AgentState:
    collector = MetricsCollector()
    with db_session() as s:
        for post_id in state.published_post_ids:
            metrics = collector.collect(post_id=post_id, session=s)
            add_metric_snapshot(
                s,
                post_id=post_id,
                external_post_id=metrics.get("external_post_id"),
                metrics=metrics,
            )
    return state


def analyze_comments(state: AgentState) -> AgentState:
    collector = MetricsCollector()
    analyzer = CommentAnalyzer()
    with db_session() as s:
        for post_id in state.published_post_ids:
            comments = collector.fetch_comments(post_id=post_id, session=s)
            enriched = analyzer.enrich(comments)
            add_comments(s, post_id=post_id, external_post_id=None, comments=enriched)
    return state


def update_strategy(state: AgentState) -> AgentState:
    optimizer = ContentOptimizer()
    with db_session() as s:
        patch = optimizer.learn_patch(session=s)
        upsert_strategy(s, patch)
        state.strategy = get_strategy(s)
        state.outputs["strategy_patch"] = patch
    return state

