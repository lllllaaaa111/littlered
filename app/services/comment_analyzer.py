from __future__ import annotations

from typing import Any


class CommentAnalyzer:
    """
    Lightweight rule-based enrichment.

    Replace with an LLM classifier if desired, but keep this interface.
    """

    POS = ["好用", "有用", "收藏了", "太棒了", "学到了", "谢谢"]
    NEG = ["不行", "没用", "踩雷", "骗人的", "失望", "不好用"]
    INTENTS = {
        "question": ["吗", "怎么", "如何", "求", "请问"],
        "buying": ["链接", "在哪里买", "同款", "价格", "店铺"],
        "experience": ["我也", "亲测", "用过", "试过"],
    }

    def enrich(self, comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in comments:
            content = (c.get("content") or "").strip()
            if not content:
                continue

            sentiment = "neutral"
            if any(k in content for k in self.POS):
                sentiment = "positive"
            if any(k in content for k in self.NEG):
                sentiment = "negative"

            intent = None
            for k, toks in self.INTENTS.items():
                if any(t in content for t in toks):
                    intent = k
                    break

            enriched = dict(c)
            enriched["sentiment"] = sentiment
            enriched["intent"] = intent
            out.append(enriched)
        return out

