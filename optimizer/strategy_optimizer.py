"""
策略优化模块

根据历史帖子表现数据，动态调整风格主题的权重。
核心策略：
- 高表现主题（评分高）→ 增加权重，增加被选中概率
- 低表现主题（评分低）→ 降低权重，减少被选中概率
- 定期重置权重防止两极分化

同时更新风格案例库的评分，维护知识库质量。
"""

from typing import List, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from database.repository import StyleTopicRepository, StyleCategoryRepository, PostRecordRepository
from analytics.performance_analyzer import PerformanceAnalyzer, HIGH_PERFORMANCE_THRESHOLD, LOW_PERFORMANCE_THRESHOLD


# 权重调整参数
WEIGHT_INCREASE_FACTOR = 1.15   # 高表现主题权重增加系数（+15%）
WEIGHT_DECREASE_FACTOR = 0.88   # 低表现主题权重降低系数（-12%）
WEIGHT_MIN = 0.1                # 最小权重（防止完全消失）
WEIGHT_MAX = 5.0                # 最大权重（防止过度集中）
WEIGHT_DEFAULT = 1.0            # 默认权重


class StrategyOptimizer:
    """
    内容策略优化器

    每日定时分析帖子数据，动态调整主题权重，
    确保系统持续优化内容方向，提升整体表现。
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.topic_repo = StyleTopicRepository(db)
        self.category_repo = StyleCategoryRepository(db)
        self.post_repo = PostRecordRepository(db)
        self.analyzer = PerformanceAnalyzer(db)

    async def optimize(self) -> Dict:
        """
        执行完整的策略优化流程

        Returns:
            优化报告字典
        """
        logger.info("开始执行策略优化...")

        # 1. 获取全量分析报告
        report = await self.analyzer.analyze_all_posts()
        if report.get("total_posts", 0) == 0:
            logger.info("暂无数据，跳过策略优化")
            return {"status": "skipped", "reason": "no data"}

        # 2. 逐风格优化主题权重
        categories = await self.category_repo.get_all()
        optimization_summary = []

        for category in categories:
            result = await self._optimize_style_topics(category.id, category.style_name)
            if result:
                optimization_summary.append(result)

        await self.db.commit()

        summary = {
            "status": "completed",
            "analyzed_posts": report.get("total_posts", 0),
            "avg_score": report.get("avg_score", 0),
            "styles_optimized": len(optimization_summary),
            "details": optimization_summary,
            "low_content_insights": report.get("low_content_insights", {}),
        }

        logger.info(
            f"策略优化完成: 分析 {summary['analyzed_posts']} 篇帖子，"
            f"优化 {summary['styles_optimized']} 个风格"
        )
        return summary

    async def _optimize_style_topics(self, style_id: int, style_name: str) -> Dict:
        """
        优化单个风格下的主题权重

        Args:
            style_id  : 风格 ID
            style_name: 风格名称

        Returns:
            优化结果字典
        """
        topic_performances = await self.analyzer.get_topic_performance(style_id)
        if not topic_performances:
            return {}

        increased = 0
        decreased = 0
        unchanged = 0

        for tp in topic_performances:
            topic_id = tp["topic_id"]
            avg_score = tp["avg_score"]
            current_weight = tp["current_weight"]

            if avg_score >= HIGH_PERFORMANCE_THRESHOLD:
                # 高表现：增加权重
                new_weight = min(current_weight * WEIGHT_INCREASE_FACTOR, WEIGHT_MAX)
                await self.topic_repo.update_weight(topic_id, new_weight)
                await self.topic_repo.update_performance_score(topic_id, avg_score)
                increased += 1
                logger.debug(
                    f"[{style_name}] 主题'{tp['keyword']}' 权重上调: "
                    f"{current_weight:.3f} → {new_weight:.3f} (评分:{avg_score:.1f})"
                )

            elif avg_score < LOW_PERFORMANCE_THRESHOLD and tp["related_posts"] >= 3:
                # 低表现（且有足够样本）：降低权重
                new_weight = max(current_weight * WEIGHT_DECREASE_FACTOR, WEIGHT_MIN)
                await self.topic_repo.update_weight(topic_id, new_weight)
                await self.topic_repo.update_performance_score(topic_id, avg_score)
                decreased += 1
                logger.debug(
                    f"[{style_name}] 主题'{tp['keyword']}' 权重下调: "
                    f"{current_weight:.3f} → {new_weight:.3f} (评分:{avg_score:.1f})"
                )

            else:
                # 中等表现或样本不足：保持权重，仅更新评分
                await self.topic_repo.update_performance_score(topic_id, avg_score)
                unchanged += 1

        return {
            "style": style_name,
            "topics_total": len(topic_performances),
            "weight_increased": increased,
            "weight_decreased": decreased,
            "unchanged": unchanged,
        }

    async def reset_weights(self, style_id: int = None) -> int:
        """
        重置主题权重到默认值（防止权重过度集中）

        Args:
            style_id: 指定风格 ID（None 表示重置所有风格）

        Returns:
            重置的主题数量
        """
        if style_id:
            topics = await self.topic_repo.get_by_style_id(style_id)
        else:
            categories = await self.category_repo.get_all()
            topics = []
            for cat in categories:
                topics.extend(await self.topic_repo.get_by_style_id(cat.id))

        for topic in topics:
            await self.topic_repo.update_weight(topic.id, WEIGHT_DEFAULT)

        await self.db.commit()
        logger.info(f"已重置 {len(topics)} 个主题的权重为默认值 {WEIGHT_DEFAULT}")
        return len(topics)

    async def get_optimization_report(self) -> Dict:
        """
        获取当前策略状态报告

        Returns:
            包含各风格主题权重分布的报告
        """
        categories = await self.category_repo.get_all()
        report = {}

        for cat in categories:
            topics = await self.topic_repo.get_by_style_id(cat.id)
            if not topics:
                continue

            weights = [t.weight for t in topics]
            scores = [t.performance_score for t in topics]

            report[cat.style_name] = {
                "total_topics": len(topics),
                "avg_weight": round(sum(weights) / len(weights), 3),
                "max_weight_topic": max(topics, key=lambda t: t.weight).topic_keyword,
                "min_weight_topic": min(topics, key=lambda t: t.weight).topic_keyword,
                "top_topics": [
                    {"keyword": t.topic_keyword, "weight": round(t.weight, 3), "score": round(t.performance_score, 1)}
                    for t in sorted(topics, key=lambda t: t.weight, reverse=True)[:5]
                ],
            }

        return report
