"""
文案生成模块

使用 LLM API（OpenAI 兼容接口）根据装修主题生成小红书文案。
支持：
- 单篇内容生成
- 批量内容生成
- 校验失败时自动重试
"""

import os
import re
from typing import Optional, Dict, Any

import yaml
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

from generators.prompt_templates import (
    CONTENT_SYSTEM_PROMPT,
    CONTENT_USER_PROMPT_TEMPLATE,
    CONTENT_RETRY_PROMPT_TEMPLATE,
)


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "../config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class GeneratedContent:
    """存储生成内容的数据结构"""

    def __init__(self, title: str, body: str, tags: list):
        self.title = title          # 帖子标题
        self.body = body            # 帖子正文
        self.tags = tags            # 话题标签列表
        self.raw_text = ""          # LLM 原始输出

    def __repr__(self) -> str:
        return f"<GeneratedContent title='{self.title}' tags={self.tags}>"


class ContentGenerator:
    """
    小红书文案生成器

    调用 OpenAI 兼容的 LLM API 生成文案，
    内置解析逻辑将 LLM 输出拆分为 title、body、tags。
    """

    def __init__(self):
        config = _load_config()
        llm_cfg = config["llm"]

        self.client = AsyncOpenAI(
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg.get("base_url", "https://api.openai.com/v1"),
        )
        self.model = llm_cfg.get("model", "gpt-4o")
        self.max_tokens = llm_cfg.get("max_tokens", 1024)
        self.temperature = llm_cfg.get("temperature", 0.8)
        self.max_retries = llm_cfg.get("max_retries", 3)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _call_llm(self, messages: list) -> str:
        """
        调用 LLM API，内置重试机制

        Args:
            messages: OpenAI 格式的消息列表

        Returns:
            LLM 返回的文本内容
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()

    def _parse_response(self, raw_text: str) -> Optional[GeneratedContent]:
        """
        解析 LLM 输出，提取标题、正文、标签

        Args:
            raw_text: LLM 原始输出文本

        Returns:
            GeneratedContent 对象，解析失败返回 None
        """
        try:
            # 提取标题
            title_match = re.search(r"标题[：:]\s*\n?(.+)", raw_text)
            if not title_match:
                logger.warning("无法从 LLM 输出中提取标题")
                return None
            title = title_match.group(1).strip()

            # 提取正文（标题之后到标签之前的内容）
            body_match = re.search(
                r"正文[：:]\s*\n([\s\S]+?)(?=\n\s*#|\Z)",
                raw_text,
            )
            if not body_match:
                logger.warning("无法从 LLM 输出中提取正文")
                return None
            body = body_match.group(1).strip()

            # 提取标签（#标签名 格式）
            tags = re.findall(r"#([^#\s]+)", raw_text)
            tags = [t.strip() for t in tags if t.strip()]

            content = GeneratedContent(title=title, body=body, tags=tags)
            content.raw_text = raw_text
            return content

        except Exception as e:
            logger.error(f"解析 LLM 输出失败: {e}\n原始内容: {raw_text[:200]}")
            return None

    async def generate(
        self,
        topic: str,
        reference_examples: str = "",
    ) -> Optional[GeneratedContent]:
        """
        根据主题生成小红书文案

        Args:
            topic              : 装修主题（如"法式原木客厅收纳"）
            reference_examples : 参考案例文本（来自向量库检索）

        Returns:
            GeneratedContent 对象，失败返回 None
        """
        # 构建用户 Prompt
        user_prompt = CONTENT_USER_PROMPT_TEMPLATE.substitute(
            topic=topic,
            reference_examples=reference_examples or "（无参考案例）",
        )

        messages = [
            {"role": "system", "content": CONTENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(f"开始生成文案，主题: {topic}")
        raw_text = await self._call_llm(messages)
        content = self._parse_response(raw_text)

        if content:
            logger.info(f"文案生成成功: 标题='{content.title}'，正文={len(content.body)}字")
        else:
            logger.error(f"文案解析失败，主题: {topic}")

        return content

    async def regenerate(
        self,
        topic: str,
        issues: str,
        previous_content: Optional[GeneratedContent] = None,
    ) -> Optional[GeneratedContent]:
        """
        内容校验失败后重新生成

        Args:
            topic           : 原始主题
            issues          : 校验失败的具体问题描述
            previous_content: 上一次生成的内容（用于上下文）

        Returns:
            重新生成的 GeneratedContent 对象
        """
        retry_prompt = CONTENT_RETRY_PROMPT_TEMPLATE.substitute(
            issues=issues,
            topic=topic,
        )

        messages = [
            {"role": "system", "content": CONTENT_SYSTEM_PROMPT},
        ]

        # 如果有上一次的内容，加入对话上下文
        if previous_content:
            messages.append({"role": "assistant", "content": previous_content.raw_text})

        messages.append({"role": "user", "content": retry_prompt})

        logger.info(f"重新生成文案，原因: {issues}")
        raw_text = await self._call_llm(messages)
        return self._parse_response(raw_text)
