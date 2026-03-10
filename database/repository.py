"""
数据库仓储层模块

封装所有数据库 CRUD 操作，提供统一的数据访问接口。
每个仓储类对应一张数据库表，隔离业务逻辑与数据访问逻辑。
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from database.models import StyleCategory, StyleTopic, StyleExample, PostRecord


# ===================== StyleCategory 仓储 =====================

class StyleCategoryRepository:
    """装修风格分类数据访问层"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_name(self, style_name: str) -> Optional[StyleCategory]:
        """根据风格名称查询"""
        result = await self.db.execute(
            select(StyleCategory).where(StyleCategory.style_name == style_name)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, style_id: int) -> Optional[StyleCategory]:
        """根据 ID 查询"""
        result = await self.db.execute(
            select(StyleCategory).where(StyleCategory.id == style_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> List[StyleCategory]:
        """查询所有风格"""
        result = await self.db.execute(select(StyleCategory))
        return list(result.scalars().all())

    async def create(self, style_name: str, description: str = "") -> StyleCategory:
        """创建新风格"""
        category = StyleCategory(style_name=style_name, description=description)
        self.db.add(category)
        await self.db.flush()
        logger.info(f"创建风格分类: {style_name}")
        return category

    async def get_or_create(self, style_name: str, description: str = "") -> StyleCategory:
        """查询或创建风格"""
        existing = await self.get_by_name(style_name)
        if existing:
            return existing
        return await self.create(style_name, description)


# ===================== StyleTopic 仓储 =====================

class StyleTopicRepository:
    """风格主题数据访问层"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_style_id(self, style_id: int) -> List[StyleTopic]:
        """查询某风格下所有主题"""
        result = await self.db.execute(
            select(StyleTopic)
            .where(StyleTopic.style_id == style_id)
            .order_by(StyleTopic.weight.desc())
        )
        return list(result.scalars().all())

    async def get_top_topics(self, style_id: int, limit: int = 10) -> List[StyleTopic]:
        """获取权重最高的主题"""
        result = await self.db.execute(
            select(StyleTopic)
            .where(StyleTopic.style_id == style_id)
            .order_by(StyleTopic.weight.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, style_id: int, topic_keyword: str, weight: float = 1.0) -> StyleTopic:
        """创建新主题"""
        topic = StyleTopic(style_id=style_id, topic_keyword=topic_keyword, weight=weight)
        self.db.add(topic)
        await self.db.flush()
        return topic

    async def update_weight(self, topic_id: int, weight: float) -> None:
        """更新主题权重"""
        await self.db.execute(
            update(StyleTopic)
            .where(StyleTopic.id == topic_id)
            .values(weight=weight)
        )
        logger.debug(f"更新主题权重: id={topic_id}, weight={weight:.3f}")

    async def update_performance_score(self, topic_id: int, score: float) -> None:
        """更新主题表现评分"""
        await self.db.execute(
            update(StyleTopic)
            .where(StyleTopic.id == topic_id)
            .values(performance_score=score)
        )

    async def bulk_create(self, style_id: int, keywords: List[str]) -> List[StyleTopic]:
        """批量创建主题"""
        topics = []
        for kw in keywords:
            topic = StyleTopic(style_id=style_id, topic_keyword=kw, weight=1.0)
            self.db.add(topic)
            topics.append(topic)
        await self.db.flush()
        logger.info(f"批量创建主题 {len(topics)} 条，style_id={style_id}")
        return topics


# ===================== StyleExample 仓储 =====================

class StyleExampleRepository:
    """风格案例数据访问层"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_style_id(self, style_id: int, limit: int = 20) -> List[StyleExample]:
        """查询某风格下的案例"""
        result = await self.db.execute(
            select(StyleExample)
            .where(StyleExample.style_id == style_id)
            .order_by(StyleExample.performance_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_top_examples(self, style_id: int, limit: int = 5) -> List[StyleExample]:
        """获取表现最好的案例"""
        result = await self.db.execute(
            select(StyleExample)
            .where(StyleExample.style_id == style_id)
            .order_by(StyleExample.performance_score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(
        self,
        style_id: int,
        title: str,
        content: str,
        image_prompt: str = "",
        tags: List[str] = None,
    ) -> StyleExample:
        """创建新案例"""
        example = StyleExample(
            style_id=style_id,
            title=title,
            content=content,
            image_prompt=image_prompt,
            tags=tags or [],
        )
        self.db.add(example)
        await self.db.flush()
        return example

    async def update_score(self, example_id: int, score: float) -> None:
        """更新案例评分"""
        await self.db.execute(
            update(StyleExample)
            .where(StyleExample.id == example_id)
            .values(performance_score=score)
        )


# ===================== PostRecord 仓储 =====================

class PostRecordRepository:
    """帖子发布记录数据访问层"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        style_id: int,
        title: str,
        content: str,
        images: List[str] = None,
    ) -> PostRecord:
        """创建发布记录"""
        record = PostRecord(
            style_id=style_id,
            title=title,
            content=content,
            images=images or [],
        )
        self.db.add(record)
        await self.db.flush()
        logger.info(f"创建发布记录: {title}")
        return record

    async def update_publish_info(self, record_id: int, xhs_post_id: str) -> None:
        """发布成功后更新小红书帖子 ID 和发布时间"""
        await self.db.execute(
            update(PostRecord)
            .where(PostRecord.id == record_id)
            .values(xhs_post_id=xhs_post_id, publish_time=datetime.now())
        )

    async def update_metrics(
        self,
        record_id: int,
        views: int,
        likes: int,
        favorites: int,
        comments: int,
    ) -> None:
        """更新帖子数据指标"""
        score = views * 0.2 + likes * 0.4 + favorites * 0.4
        await self.db.execute(
            update(PostRecord)
            .where(PostRecord.id == record_id)
            .values(
                views=views,
                likes=likes,
                favorites=favorites,
                comments=comments,
                performance_score=score,
            )
        )
        logger.debug(f"更新帖子指标: id={record_id}, score={score:.1f}")

    async def get_by_xhs_id(self, xhs_post_id: str) -> Optional[PostRecord]:
        """根据小红书帖子 ID 查询"""
        result = await self.db.execute(
            select(PostRecord).where(PostRecord.xhs_post_id == xhs_post_id)
        )
        return result.scalar_one_or_none()

    async def get_published_without_metrics(self, limit: int = 50) -> List[PostRecord]:
        """查询已发布但未采集数据的帖子"""
        result = await self.db.execute(
            select(PostRecord)
            .where(
                PostRecord.xhs_post_id.isnot(None),
                PostRecord.views == 0,
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent_posts(self, days: int = 7, limit: int = 100) -> List[PostRecord]:
        """查询最近 N 天的发布记录"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        result = await self.db.execute(
            select(PostRecord)
            .where(PostRecord.publish_time >= cutoff)
            .order_by(PostRecord.publish_time.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_low_performance_posts(self, threshold: float = 50.0, limit: int = 20) -> List[PostRecord]:
        """查询低表现帖子（评分低于阈值）"""
        result = await self.db.execute(
            select(PostRecord)
            .where(
                PostRecord.performance_score < threshold,
                PostRecord.publish_time.isnot(None),
            )
            .order_by(PostRecord.performance_score.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_all_published(self) -> List[PostRecord]:
        """查询所有已发布帖子"""
        result = await self.db.execute(
            select(PostRecord).where(PostRecord.publish_time.isnot(None))
        )
        return list(result.scalars().all())

    async def get_style_avg_score(self, style_id: int) -> float:
        """查询某风格帖子的平均评分"""
        result = await self.db.execute(
            select(func.avg(PostRecord.performance_score))
            .where(PostRecord.style_id == style_id)
        )
        avg = result.scalar_one_or_none()
        return float(avg) if avg else 0.0
