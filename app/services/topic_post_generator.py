from __future__ import annotations

import random
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import Topic


class TopicPostGenerator:
    """
    Minimal generator (no external LLM required).

    You can later swap this to an LLM-backed implementation while keeping the same interface.
    """

    def __init__(self, strategy: dict[str, Any] | None = None):
        self.strategy = strategy or {}
        self.random = random.Random(self.strategy.get("seed", 42))

    def generate_topics(self, n: int = 5) -> list[dict[str, Any]]:
        niche = self.strategy.get("niche", "生活方式")
        audience = self.strategy.get("audience", "上班族")
        formats = self.strategy.get("formats", ["清单", "避坑", "对比", "教程", "经验复盘"])
        hooks = self.strategy.get("hooks", ["我踩过的坑", "亲测有效", "3分钟搞定", "别再这样做了", "省钱又好用"])

        topics: list[dict[str, Any]] = []
        for _ in range(n):
            fmt = self.random.choice(formats)
            hook = self.random.choice(hooks)
            title = f"{audience}{niche}{fmt}：{hook}"
            angle = self.random.choice(
                [
                    "高性价比、可复制",
                    "新手友好、步骤清晰",
                    "真实体验、优缺点都讲",
                    "效率提升、可立刻执行",
                ]
            )
            keywords = [niche, audience, fmt]
            topics.append(
                {
                    "title": title[:300],
                    "angle": angle,
                    "keywords": keywords,
                    "rationale": f"用{fmt}结构+{hook}钩子，贴合{audience}在{niche}的高频需求。",
                    "score": float(self.random.randint(1, 5)),
                }
            )
        return topics

    def generate_post(self, *, topic_id: int, session: Session) -> dict[str, Any]:
        topic = session.get(Topic, topic_id)
        if topic is None:
            raise ValueError(f"topic {topic_id} not found")

        tone = self.strategy.get("tone", "真诚、可执行、偏口语")
        cta = self.strategy.get("cta", "如果你也在用/踩过坑，评论区聊聊～")
        hashtag_pool = self.strategy.get(
            "hashtag_pool",
            ["#日常分享", "#干货", "#避坑", "#清单", "#提升效率", "#生活方式"],
        )
        hashtags = self.random.sample(hashtag_pool, k=min(4, len(hashtag_pool)))

        title = (topic.title or "分享")[:200]
        body = "\n".join(
            [
                f"先说结论：{topic.angle or '这套方法我最近一直在用，真的省时间。'}",
                "",
                "1）准备/前提",
                " - 你需要：纸笔/备忘录 + 10分钟空档",
                "",
                "2）步骤（照做即可）",
                " - 第一步：列出你现在最困扰的3件事（越具体越好）",
                " - 第二步：给每件事设一个“最低完成标准”（5分钟能做完）",
                " - 第三步：只做最小闭环，先把反馈跑出来",
                "",
                "3）避坑点",
                " - 别一次性做太多，越多越容易放弃",
                " - 先让自己“容易开始”，再优化",
                "",
                f"风格：{tone}",
                "",
                cta,
            ]
        )

        return {
            "title": title,
            "body": body,
            "hashtags": hashtags,
            "language": "zh",
            "style": dict(self.strategy),
        }

