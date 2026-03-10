"""
主题生成模块

根据用户输入的装修风格，从 style_topics 表中检索主题，
结合权重随机抽样，生成多样化的帖子主题列表。

示例：
    输入：原木风
    返回：['经典美式原木小户型客厅', '法式原木客厅收纳', '新中式原木卧室设计', ...]
"""

import random
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from database.repository import StyleCategoryRepository, StyleTopicRepository
from knowledge.style_repository import StyleRepository


# 主题组合修饰词（用于丰富主题变体）
STYLE_MODIFIERS = ["经典", "法式", "新中式", "日式", "现代", "复古", "简约", "极简", "轻奢"]
SPACE_TYPES = ["客厅", "卧室", "书房", "餐厅", "厨房", "玄关", "卫生间", "阳台"]
SIZE_MODIFIERS = ["小户型", "大户型", "50平", "90平", "120平", "loft", "复式"]
FEATURE_KEYWORDS = ["收纳", "改造", "设计", "装修分享", "布置技巧", "选材指南", "费用清单"]


class TopicGenerator:
    """
    主题生成器

    策略：
    1. 从数据库查询该风格下所有主题（按权重排序）
    2. 使用加权随机抽样选出核心主题
    3. 通过修饰词组合扩展主题变体
    4. 去重后返回指定数量的主题列表
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.category_repo = StyleCategoryRepository(db)
        self.topic_repo = StyleTopicRepository(db)
        self.style_repo = StyleRepository(db)

    async def generate_topics(
        self,
        style_name: str,
        count: int = 10,
    ) -> List[str]:
        """
        根据风格名称生成主题列表

        Args:
            style_name: 装修风格名称（如"原木风"）
            count     : 需要生成的主题数量

        Returns:
            主题字符串列表
        """
        # 1. 查询风格分类
        category = await self.category_repo.get_by_name(style_name)
        if not category:
            logger.warning(f"未找到风格 '{style_name}'，使用默认主题生成")
            return self._generate_default_topics(style_name, count)

        # 2. 查询该风格下所有主题
        all_topics = await self.topic_repo.get_by_style_id(category.id)
        if not all_topics:
            logger.warning(f"风格 '{style_name}' 下无主题数据，使用默认生成")
            return self._generate_default_topics(style_name, count)

        # 3. 加权随机抽样（weight 越高被选中概率越大）
        weights = [max(t.weight, 0.01) for t in all_topics]
        keywords = [t.topic_keyword for t in all_topics]

        # 抽取基础主题（数量为 count 的一半）
        base_count = min(len(keywords), max(count // 2, 3))
        selected_keywords = random.choices(keywords, weights=weights, k=base_count)

        # 4. 通过修饰词生成主题变体
        topics = list(set(selected_keywords))  # 去重基础主题
        topics += self._generate_variants(style_name, keywords, count - len(topics))

        # 5. 去重并截取所需数量
        unique_topics = list(dict.fromkeys(topics))[:count]

        logger.info(f"风格 '{style_name}' 生成主题 {len(unique_topics)} 个")
        return unique_topics

    def _generate_variants(
        self,
        style_name: str,
        base_keywords: List[str],
        count: int,
    ) -> List[str]:
        """
        通过修饰词组合生成主题变体

        Args:
            style_name   : 风格名称
            base_keywords: 基础关键词列表
            count        : 需要生成的变体数量

        Returns:
            变体主题列表
        """
        variants = []
        attempts = 0
        max_attempts = count * 5  # 防止无限循环

        while len(variants) < count and attempts < max_attempts:
            attempts += 1
            variant_type = random.randint(0, 3)

            if variant_type == 0:
                # 修饰词 + 风格 + 空间
                modifier = random.choice(STYLE_MODIFIERS)
                space = random.choice(SPACE_TYPES)
                topic = f"{modifier}{style_name}{space}设计"

            elif variant_type == 1:
                # 尺寸 + 风格 + 空间
                size = random.choice(SIZE_MODIFIERS)
                space = random.choice(SPACE_TYPES)
                topic = f"{size}{style_name}{space}"

            elif variant_type == 2:
                # 风格 + 空间 + 功能词
                space = random.choice(SPACE_TYPES)
                feature = random.choice(FEATURE_KEYWORDS)
                topic = f"{style_name}{space}{feature}"

            else:
                # 直接使用基础关键词（加少量变体）
                if base_keywords:
                    base = random.choice(base_keywords)
                    feature = random.choice(FEATURE_KEYWORDS)
                    topic = f"{base}{feature}" if len(base) < 10 else base

                else:
                    continue

            # 过滤过长的主题（> 20字会超出标题限制）
            if len(topic) <= 15:
                variants.append(topic)

        return variants

    def _generate_default_topics(self, style_name: str, count: int) -> List[str]:
        """当数据库无数据时的默认主题生成"""
        default_topics = []
        for space in SPACE_TYPES[:count]:
            default_topics.append(f"{style_name}{space}设计")
        return default_topics[:count]

    async def get_topics_for_batch(
        self,
        style_name: str,
        batch_size: int = 30,
    ) -> List[str]:
        """
        为每日批量发布生成主题列表

        Args:
            style_name : 装修风格
            batch_size : 每日发帖数量（默认 30）

        Returns:
            足够数量的主题列表
        """
        topics = await self.generate_topics(style_name, count=batch_size)
        # 如果主题不够，循环补充（稍作变体避免完全重复）
        while len(topics) < batch_size:
            extra = await self.generate_topics(style_name, count=batch_size - len(topics))
            topics.extend(extra)
            topics = list(dict.fromkeys(topics))  # 去重

        logger.info(f"批量主题生成完成: {style_name} × {len(topics)} 个主题")
        return topics[:batch_size]
