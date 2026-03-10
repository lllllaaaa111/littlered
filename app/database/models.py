from __future__ import annotations

import datetime as dt
import enum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class PostStatus(str, enum.Enum):
    drafted = "drafted"
    image_generated = "image_generated"
    published = "published"
    failed = "failed"


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))

    title: Mapped[str] = mapped_column(String(300))
    angle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)  # coarse priority

    posts: Mapped[list["Post"]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("topic_id", "version", name="uq_post_topic_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
    )

    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[PostStatus] = mapped_column(Enum(PostStatus), default=PostStatus.drafted)

    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    language: Mapped[str] = mapped_column(String(16), default="zh")
    style: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    image: Mapped["ImageAsset | None"] = relationship(back_populates="post", uselist=False, cascade="all, delete-orphan")
    publish_events: Mapped[list["PublishEvent"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    metrics: Mapped[list["MetricSnapshot"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    topic: Mapped["Topic"] = relationship(back_populates="posts")


class ImageAsset(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), unique=True)
    prompt: Mapped[str] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str] = mapped_column(String(200))
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=1024)
    height: Mapped[int] = mapped_column(Integer, default=1024)
    steps: Mapped[int] = mapped_column(Integer, default=30)
    guidance_scale: Mapped[float] = mapped_column(Float, default=7.0)
    file_path: Mapped[str] = mapped_column(String(500))

    post: Mapped["Post"] = relationship(back_populates="image")


class PublishEvent(Base):
    __tablename__ = "publish_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    platform: Mapped[str] = mapped_column(String(64), default="xiaohongshu")
    external_post_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    post: Mapped["Post"] = relationship(back_populates="publish_events")


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    external_post_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    collects: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)

    post: Mapped["Post"] = relationship(back_populates="metrics")


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (UniqueConstraint("post_id", "external_comment_id", name="uq_comment_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"))
    external_post_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_comment_id: Mapped[str] = mapped_column(String(200))

    author: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)

    post: Mapped["Post"] = relationship(back_populates="comments")


class StrategyState(Base):
    __tablename__ = "strategy_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
    )
    # Free-form knobs learned over time (style weights, best hashtags, posting time hints, etc.)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

