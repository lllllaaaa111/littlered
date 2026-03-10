"""
图片生成模块

调用 Stable Diffusion WebUI API（A1111 兼容接口）
为每篇帖子生成 4 张高质量装修效果图。

支持：
- txt2img 文本生成图片
- 批量生成（4 张/帖）
- 自动保存到本地存储目录
"""

import os
import base64
import uuid
import asyncio
from typing import List, Tuple
from pathlib import Path

import yaml
import aiohttp
from PIL import Image
import io
from loguru import logger

from generators.prompt_templates import build_sd_prompt


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "../config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class ImageGenerator:
    """
    Stable Diffusion 图片生成器

    对接 A1111 WebUI /sdapi/v1/txt2img API。
    每次调用为一篇帖子生成 4 张不同角度的装修效果图。
    """

    def __init__(self):
        config = _load_config()
        sd_cfg = config["stable_diffusion"]
        storage_cfg = config["storage"]

        self.api_url = sd_cfg.get("api_url", "http://127.0.0.1:7860")
        self.steps = sd_cfg.get("steps", 30)
        self.cfg_scale = sd_cfg.get("cfg_scale", 7)
        self.width = sd_cfg.get("width", 1024)
        self.height = sd_cfg.get("height", 1024)
        self.sampler_name = sd_cfg.get("sampler_name", "DPM++ 2M Karras")

        # 图片存储目录
        self.image_dir = Path(storage_cfg.get("image_dir", "./storage/images"))
        self.image_dir.mkdir(parents=True, exist_ok=True)

        self.images_per_post = config["content_rules"].get("images_per_post", 4)

    async def _generate_single(
        self,
        positive_prompt: str,
        negative_prompt: str,
        seed: int = -1,
    ) -> bytes:
        """
        调用 SD API 生成单张图片

        Args:
            positive_prompt: 正面提示词
            negative_prompt: 负面提示词
            seed           : 随机种子（-1 为随机）

        Returns:
            图片二进制数据
        """
        payload = {
            "prompt": positive_prompt,
            "negative_prompt": negative_prompt,
            "steps": self.steps,
            "cfg_scale": self.cfg_scale,
            "width": self.width,
            "height": self.height,
            "sampler_name": self.sampler_name,
            "seed": seed,
            "batch_size": 1,
            "n_iter": 1,
            "save_images": False,
            "send_images": True,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/sdapi/v1/txt2img",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

        # 解码 Base64 图片
        img_b64 = data["images"][0]
        img_bytes = base64.b64decode(img_b64)
        return img_bytes

    def _save_image(self, img_bytes: bytes, filename: str) -> str:
        """
        保存图片到本地，并验证分辨率

        Args:
            img_bytes: 图片二进制数据
            filename : 文件名（不含路径）

        Returns:
            图片绝对路径
        """
        img = Image.open(io.BytesIO(img_bytes))

        # 校验分辨率（≥ 1024）
        min_res = 1024
        if img.width < min_res or img.height < min_res:
            logger.warning(f"图片分辨率 {img.width}×{img.height} 低于要求，尝试放大")
            img = img.resize((max(img.width, min_res), max(img.height, min_res)), Image.LANCZOS)

        save_path = self.image_dir / filename
        img.save(str(save_path), format="PNG", optimize=True)
        logger.debug(f"图片已保存: {save_path} ({img.width}×{img.height})")
        return str(save_path)

    async def generate_post_images(
        self,
        style_name: str,
        topic: str,
        post_id: str = None,
    ) -> List[str]:
        """
        为单篇帖子生成 4 张图片

        Args:
            style_name: 装修风格名称
            topic     : 帖子主题
            post_id   : 帖子 ID（用于文件命名，不传则自动生成）

        Returns:
            4 张图片的本地路径列表
        """
        if not post_id:
            post_id = str(uuid.uuid4())[:8]

        logger.info(f"开始生成图片: 风格={style_name}, 主题={topic}")
        image_paths = []

        # 并发生成 4 张图（不同角度/光线）
        tasks = []
        for i in range(self.images_per_post):
            pos_prompt, neg_prompt = build_sd_prompt(style_name, topic, index=i)
            tasks.append(self._generate_single(pos_prompt, neg_prompt))

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"图片生成失败: {e}")
            return []

        # 保存成功生成的图片
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"第 {i+1} 张图片生成失败: {result}")
                continue
            filename = f"{post_id}_img_{i+1}.png"
            path = self._save_image(result, filename)
            image_paths.append(path)

        logger.info(f"图片生成完成: {len(image_paths)}/{self.images_per_post} 张")
        return image_paths

    async def check_api_health(self) -> bool:
        """检查 SD API 是否可用"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/sdapi/v1/sd-models",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
