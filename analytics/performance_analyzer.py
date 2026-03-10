"""
数据分析模块

对已采集的帖子数据进行统计分析：
- 计算帖子表现评分（score = views×0.2 + likes×0.4 + favorites×0.4）
- 识别高表现和低表现内容
- 分析差评内容特征，为策略优化提供依据
- 输出风格和主题的表现报告
"""

from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from database.repository import PostRecordRepository, StyleTopicRepository, StyleCategoryRepository
from database.models import PostRecord


# 帖子表现评分公式系数
SCORE_WEIGHTS = {
    "views": 0.2,
    "likes": 0.4,
    "favorites": 0.4,
}

# 高/低表现阈值（可根据实际数据调整）
HIGH_PERFORMANCE_THRESHOLD = 200.0   # 评分 ≥ 200 为高表现
LOW_PERFORMANCE_THRESHOLD = 50.0     # 评分 < 50 为低表现


def calculate_score(views: int, likes: int, favorites: int) -> float:
    """
    计算帖子表现评分

    公式：score = views × 0.2 + likes × 0.4 + favorites × 0.4

    Args:
        views    : 浏览量
        likes    : 点赞数
        favorites: 收藏数

    Returns:
        浮点评分
    """
    return (
        views * SCORE_WEIGHTS["views"]
        + likes * SCORE_WEIGHTS["likes"]
        + favorites * SCORE_WEIGHTS["favorites"]
    )


class PerformanceAnalyzer:
    """
    帖子表现分析器

    分析历史帖子的表现数据，提取风格/主题维度的洞察，
    为内容策略优化提供数据支撑。
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.post_repo = PostRecordRepository(db)
        self.topic_repo = StyleTopicRepository(db)
        self.category_repo = StyleCategoryRepository(db)

    async def analyze_all_posts(self) -> Dict:
        """
        全量分析所有已发布帖子

        Returns:
            分析报告字典，包含：
            - total_posts   : 总帖子数
            - avg_score     : 平均评分
            - high_count    : 高表现帖子数
            - low_count     : 低表现帖子数
            - top_posts     : 前5名帖子
            - worst_posts   : 后5名帖子
            - style_stats   : 各风格统计
        """
        posts = await self.post_repo.get_all_published()
        if not posts:
            logger.warning("无已发布帖子数据可分析")
            return {"total_posts": 0}

        # 更新每篇帖子的评分
        for post in posts:
            new_score = calculate_score(post.views, post.likes, post.favorites)
            if abs(new_score - post.performance_score) > 0.1:
                await self.post_repo.update_metrics(
                    record_id=post.id,
                    views=post.views,
                    likes=post.likes,
                    favorites=post.favorites,
                    comments=post.comments,
                )
        await self.db.commit()

        # 重新加载更新后的数据
        posts = await self.post_repo.get_all_published()
        scored_posts = sorted(posts, key=lambda p: p.performance_score, reverse=True)

        # 基础统计
        scores = [p.performance_score for p in posts]
        avg_score = sum(scores) / len(scores) if scores else 0
        high_count = sum(1 for s in scores if s >= HIGH_PERFORMANCE_THRESHOLD)
        low_count = sum(1 for s in scores if s < LOW_PERFORMANCE_THRESHOLD)

        # 按风格分组统计
        style_stats = await self._analyze_by_style(posts)

        # 差评内容特征分析
        low_posts = [p for p in posts if p.performance_score < LOW_PERFORMANCE_THRESHOLD]
        low_content_insights = self._analyze_low_performance_content(low_posts)

        report = {
            "total_posts": len(posts),
            "avg_score": round(avg_score, 2),
            "high_count": high_count,
            "low_count": low_count,
            "top_posts": [
                {"id": p.id, "title": p.title, "score": round(p.performance_score, 2)}
                for p in scored_posts[:5]
            ],
            "worst_posts": [
                {"id": p.id, "title": p.title, "score": round(p.performance_score, 2)}
                for p in scored_posts[-5:]
            ],
            "style_stats": style_stats,
            "low_content_insights": low_content_insights,
        }

        logger.info(
            f"分析完成: 共 {len(posts)} 篇，平均分 {avg_score:.1f}，"
            f"高表现 {high_count} 篇，低表现 {low_count} 篇"
        )
        return report

    async def _analyze_by_style(self, posts: List[PostRecord]) -> Dict:
        """按风格分组统计平均评分"""
        style_groups: Dict[int, List[float]] = defaultdict(list)
        for post in posts:
            if post.style_id:
                style_groups[post.style_id].append(post.performance_score)

        style_stats = {}
        for style_id, scores in style_groups.items():
            category = await self.category_repo.get_by_id(style_id)
            style_name = category.style_name if category else f"style_{style_id}"
            style_stats[style_name] = {
                "post_count": len(scores),
                "avg_score": round(sum(scores) / len(scores), 2),
                "max_score": round(max(scores), 2),
                "min_score": round(min(scores), 2),
            }

        return style_stats

    def _analyze_low_performance_content(
        self, low_posts: List[PostRecord]
    ) -> Dict:
        """
        分析低表现帖子的内容特征

        从标题和正文中提取共性问题，为内容模板更新提供依据。
        """
        if not low_posts:
            return {"count": 0, "patterns": []}

        # 统计标题长度分布
        title_lengths = [len(p.title) for p in low_posts]
        avg_title_len = sum(title_lengths) / len(title_lengths)

        # 统计正文长度分布
        body_lengths = [len(p.content) for p in low_posts]
        avg_body_len = sum(body_lengths) / len(body_lengths)

        # 识别问题模式
        patterns = []
        if avg_title_len < 8:
            patterns.append("标题过短（平均不足8字），建议增加描述性词汇")
        if avg_title_len > 18:
            patterns.append("标题接近上限，建议精炼标题")
        if avg_body_len < 100:
            patterns.append("正文内容过少（平均不足100字），建议增加实用信息")
        if avg_body_len > 450:
            patterns.append("正文过长（超过450字），建议精简内容")

        return {
            "count": len(low_posts),
            "avg_title_length": round(avg_title_len, 1),
            "avg_body_length": round(avg_body_len, 1),
            "patterns": patterns,
            "sample_titles": [p.title for p in low_posts[:5]],
        }

    async def get_topic_performance(self, style_id: int) -> List[Dict]:
        """
        获取某风格下各主题的表现数据

        通过匹配帖子标题与主题关键词来关联数据。

        Returns:
            主题表现列表（按评分降序）
        """
        topics = await self.topic_repo.get_by_style_id(style_id)
        posts = await self.post_repo.get_recent_posts(days=30, limit=200)
        style_posts = [p for p in posts if p.style_id == style_id]

        topic_performance = []
        for topic in topics:
            # 查找包含该主题关键词的帖子
            related_posts = [
                p for p in style_posts
                if topic.topic_keyword in p.title or topic.topic_keyword in p.content
            ]
            if related_posts:
                avg_score = sum(p.performance_score for p in related_posts) / len(related_posts)
            else:
                avg_score = topic.performance_score  # 使用历史评分

            topic_performance.append({
                "topic_id": topic.id,
                "keyword": topic.topic_keyword,
                "current_weight": topic.weight,
                "avg_score": round(avg_score, 2),
                "related_posts": len(related_posts),
            })

        return sorted(topic_performance, key=lambda x: x["avg_score"], reverse=True)
