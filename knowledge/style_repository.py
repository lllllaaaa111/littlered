"""
风格知识库模块

整合数据库和向量库，提供风格案例的统一管理接口。
负责：
- 初始化内置风格数据（首次运行时种子数据）
- 同步数据库案例到向量库
- 根据风格和主题检索相关案例
"""

from typing import List, Dict, Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from database.repository import StyleCategoryRepository, StyleExampleRepository, StyleTopicRepository
from knowledge.vector_store import VectorStore


# ===== 内置种子数据：风格 & 主题 =====
SEED_STYLES: List[Dict[str, Any]] = [
    {
        "style_name": "原木风",
        "description": "以天然木材为主要元素，色调温暖自然，强调木纹纹理，营造治愈温馨的居住氛围",
        "topics": [
            "小户型原木客厅改造",
            "原木风卧室收纳技巧",
            "原木餐厅设计",
            "原木风书房打造",
            "原木儿童房设计",
            "原木风玄关设计",
            "原木浴室改造",
            "原木风阳台花园",
            "法式原木客厅收纳",
            "新中式原木卧室设计",
            "经典美式原木小户型客厅",
            "日式原木极简客厅",
        ],
    },
    {
        "style_name": "法式风",
        "description": "优雅浪漫，以奶油白、灰粉等柔和色调为主，搭配精致线条和复古元素，充满艺术气息",
        "topics": [
            "法式奶油风客厅设计",
            "法式卧室布置技巧",
            "法式厨房改造",
            "法式餐厅设计",
            "法式玄关设计",
            "法式浪漫婚房布置",
            "法式复古书房",
            "法式阳台设计",
        ],
    },
    {
        "style_name": "新中式",
        "description": "融合传统中式元素与现代设计理念，以深色木材、山水画、竹帘等为特色，平衡传统与现代",
        "topics": [
            "新中式客厅设计",
            "新中式茶室打造",
            "新中式卧室布置",
            "新中式书房设计",
            "新中式玄关设计",
            "新中式餐厅设计",
            "禅意新中式阳台",
        ],
    },
    {
        "style_name": "北欧风",
        "description": "简约实用，以白色为基调，搭配原木色和黑色线条，注重自然光线和功能性",
        "topics": [
            "北欧极简客厅",
            "北欧风卧室收纳",
            "北欧厨房改造",
            "北欧儿童房设计",
            "北欧书房设计",
            "北欧玄关收纳",
        ],
    },
    {
        "style_name": "现代简约",
        "description": "去繁从简，以直线条和中性色调为主，强调功能性和空间感，适合都市快节奏生活",
        "topics": [
            "现代简约客厅设计",
            "极简主义卧室布置",
            "现代简约厨房改造",
            "简约卫生间设计",
            "现代简约书房",
            "小户型极简设计",
        ],
    },
]


class StyleRepository:
    """
    风格知识库管理类

    统一管理风格数据、主题数据和向量库，
    提供面向业务的检索和管理接口。
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.category_repo = StyleCategoryRepository(db)
        self.topic_repo = StyleTopicRepository(db)
        self.example_repo = StyleExampleRepository(db)
        self.vector_store = VectorStore()

    async def initialize_seed_data(self) -> None:
        """
        初始化种子数据（首次运行时调用）
        向数据库写入内置风格和主题数据
        """
        logger.info("开始初始化风格知识库种子数据...")
        for style_data in SEED_STYLES:
            # 创建或获取风格分类
            category = await self.category_repo.get_or_create(
                style_name=style_data["style_name"],
                description=style_data["description"],
            )
            # 批量创建主题
            existing_topics = await self.topic_repo.get_by_style_id(category.id)
            existing_keywords = {t.topic_keyword for t in existing_topics}
            new_keywords = [
                kw for kw in style_data["topics"]
                if kw not in existing_keywords
            ]
            if new_keywords:
                await self.topic_repo.bulk_create(category.id, new_keywords)
                logger.info(f"风格 [{style_data['style_name']}] 添加 {len(new_keywords)} 个新主题")

        await self.db.commit()
        logger.info("种子数据初始化完成")

    async def get_style_id(self, style_name: str) -> Optional[int]:
        """根据风格名称获取 ID"""
        category = await self.category_repo.get_by_name(style_name)
        return category.id if category else None

    async def get_topics_by_style(self, style_name: str, limit: int = 10) -> List[str]:
        """获取某风格下的主题关键词列表（按权重排序）"""
        category = await self.category_repo.get_by_name(style_name)
        if not category:
            logger.warning(f"未找到风格: {style_name}")
            return []
        topics = await self.topic_repo.get_top_topics(category.id, limit=limit)
        return [t.topic_keyword for t in topics]

    async def search_examples(
        self,
        style_name: str,
        query: str,
        n_results: int = 5,
    ) -> List[Dict]:
        """
        通过向量检索获取相关案例

        Args:
            style_name: 装修风格名称
            query     : 查询文本（主题关键词）
            n_results : 返回数量

        Returns:
            相关案例列表
        """
        results = self.vector_store.search_by_style(
            style_name=style_name,
            query_text=query,
            n_results=n_results,
        )
        return results

    async def add_example_to_vector_store(
        self,
        example_id: int,
        style_name: str,
        title: str,
        content: str,
        tags: List[str] = None,
    ) -> None:
        """将新案例添加到向量库"""
        text = f"{title}\n{content}"
        metadata = {
            "style_name": style_name,
            "title": title,
            "tags": ",".join(tags or []),
        }
        self.vector_store.add_example(
            doc_id=str(example_id),
            text=text,
            metadata=metadata,
        )

    async def sync_examples_to_vector_store(self) -> int:
        """
        将数据库中所有案例同步到向量库
        用于初始化或重建向量索引
        """
        categories = await self.category_repo.get_all()
        total = 0
        for category in categories:
            examples = await self.example_repo.get_by_style_id(category.id, limit=1000)
            if not examples:
                continue
            doc_ids = [str(e.id) for e in examples]
            texts = [f"{e.title}\n{e.content}" for e in examples]
            metas = [
                {
                    "style_name": category.style_name,
                    "title": e.title,
                    "tags": ",".join(e.tags or []),
                }
                for e in examples
            ]
            self.vector_store.add_examples_batch(doc_ids, texts, metas)
            total += len(examples)

        logger.info(f"同步 {total} 条案例到向量库")
        return total
