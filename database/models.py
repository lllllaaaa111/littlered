"""
数据库模型定义模块

定义所有 SQLAlchemy ORM 模型，对应 PostgreSQL 数据库表结构：
- StyleCategory  : 装修风格分类表
- StyleTopic     : 风格主题表
- StyleExample   : 风格案例表
- PostRecord     : 帖子发布记录表
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class StyleCategory(Base):
    """
    装修风格分类表
    存储所有支持的装修风格，如：原木风、法式、新中式、北欧等
    """
    __tablename__ = "style_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    style_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="风格名称")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="风格描述")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="创建时间"
    )

    # 关联关系
    topics: Mapped[List["StyleTopic"]] = relationship("StyleTopic", back_populates="category", lazy="select")
    examples: Mapped[List["StyleExample"]] = relationship("StyleExample", back_populates="category", lazy="select")
    post_records: Mapped[List["PostRecord"]] = relationship("PostRecord", back_populates="category", lazy="select")

    def __repr__(self) -> str:
        return f"<StyleCategory(id={self.id}, style_name='{self.style_name}')>"


class StyleTopic(Base):
    """
    风格主题表
    存储各风格下的细分主题关键词，用于主题生成
    weight          : 权重（0.0~1.0），影响主题被选中概率
    performance_score: 历史表现评分，由数据分析模块更新
    """
    __tablename__ = "style_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    style_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("style_category.id", ondelete="CASCADE"), nullable=False, comment="关联风格ID"
    )
    topic_keyword: Mapped[str] = mapped_column(String(100), nullable=False, comment="主题关键词")
    weight: Mapped[float] = mapped_column(Float, default=1.0, comment="权重(0~1)")
    performance_score: Mapped[float] = mapped_column(Float, default=0.0, comment="历史表现评分")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="创建时间"
    )

    # 关联关系
    category: Mapped["StyleCategory"] = relationship("StyleCategory", back_populates="topics")

    def __repr__(self) -> str:
        return f"<StyleTopic(id={self.id}, keyword='{self.topic_keyword}', weight={self.weight})>"


class StyleExample(Base):
    """
    风格案例表
    存储优质内容案例，用于向量检索和内容参考
    tags            : JSON 数组，存储标签列表
    image_prompt    : Stable Diffusion 图片生成提示词
    performance_score: 案例表现评分
    post_records_id : 关联的发布记录 ID（可选）
    """
    __tablename__ = "style_examples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    style_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("style_category.id", ondelete="CASCADE"), nullable=False, comment="关联风格ID"
    )
    title: Mapped[str] = mapped_column(String(50), nullable=False, comment="标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="正文内容")
    image_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="图片生成提示词")
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="标签列表(JSON数组)")
    performance_score: Mapped[float] = mapped_column(Float, default=0.0, comment="内容表现评分")
    post_records_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("post_records.id", ondelete="SET NULL"), nullable=True, comment="关联发布记录ID"
    )

    # 关联关系
    category: Mapped["StyleCategory"] = relationship("StyleCategory", back_populates="examples")
    post_record: Mapped[Optional["PostRecord"]] = relationship("PostRecord", foreign_keys=[post_records_id])

    def __repr__(self) -> str:
        return f"<StyleExample(id={self.id}, title='{self.title}')>"


class PostRecord(Base):
    """
    帖子发布记录表
    记录每篇已发布帖子的元数据和数据指标
    images          : JSON 数组，存储本地图片路径列表
    views/likes/favorites/comments : 数据指标，由数据采集模块更新
    """
    __tablename__ = "post_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    style_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("style_category.id", ondelete="SET NULL"), nullable=True, comment="关联风格ID"
    )
    title: Mapped[str] = mapped_column(String(50), nullable=False, comment="帖子标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="帖子正文")
    images: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="图片路径列表(JSON数组)")
    views: Mapped[int] = mapped_column(Integer, default=0, comment="浏览量")
    likes: Mapped[int] = mapped_column(Integer, default=0, comment="点赞数")
    favorites: Mapped[int] = mapped_column(Integer, default=0, comment="收藏数")
    comments: Mapped[int] = mapped_column(Integer, default=0, comment="评论数")
    publish_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="发布时间"
    )
    # 小红书帖子 ID（发布后获取，用于数据采集）
    xhs_post_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="小红书帖子ID")
    # 性能评分缓存
    performance_score: Mapped[float] = mapped_column(Float, default=0.0, comment="帖子表现评分")

    # 关联关系
    category: Mapped[Optional["StyleCategory"]] = relationship("StyleCategory", back_populates="post_records")

    def __repr__(self) -> str:
        return f"<PostRecord(id={self.id}, title='{self.title}', score={self.performance_score})>"
