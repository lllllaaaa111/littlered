"""
图片获取模块

支持三种图片来源模式，通过配置 image.source 切换：

  stable_diffusion  调用 SD WebUI API 生成（生产默认）
  local             从本地 sample_images 目录随机抽取（测试用）
  auto              优先调用 SD API；若 API 不可达则自动回退到 local

典型用法（测试其他环节时）：
  config.yaml → image.source: "local"
  在 storage/sample_images/ 放入任意 PNG/JPG 图片即可跳过 SD API
"""

import os
import uuid
import shutil
import random
import asyncio
import base64
import io
from pathlib import Path
from typing import List

import yaml
import aiohttp
from PIL import Image
from loguru import logger

from generators.prompt_templates import build_sd_prompt


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "../config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# 支持的本地图片扩展名
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class ImageGenerator:
    """
    图片获取器

    根据 config.yaml 中 image.source 的值，选择不同的图片获取策略：
    - stable_diffusion : 调用 SD WebUI API 生成（生产模式）
    - local            : 从 image.local_image_dir 随机取图（测试模式）
    - auto             : 先尝试 SD API，不可用时自动回退 local
    """

    SOURCE_SD    = "stable_diffusion"
    SOURCE_LOCAL = "local"
    SOURCE_AUTO  = "auto"

    def __init__(self):
        config = _load_config()
        sd_cfg      = config["stable_diffusion"]
        storage_cfg = config["storage"]
        img_cfg     = config.get("image", {})

        # ── 图片来源模式 ──────────────────────────────────────
        self.source = img_cfg.get("source", self.SOURCE_SD)

        # 本地样例图片目录（local / auto 模式使用）
        self.local_image_dir = Path(
            img_cfg.get("local_image_dir", "./storage/sample_images")
        )
        self.local_image_dir.mkdir(parents=True, exist_ok=True)

        # ── SD API 参数 ────────────────────────────────────────
        self.api_url     = sd_cfg.get("api_url", "http://127.0.0.1:7860")
        self.steps       = sd_cfg.get("steps", 30)
        self.cfg_scale   = sd_cfg.get("cfg_scale", 7)
        self.width       = sd_cfg.get("width", 1024)
        self.height      = sd_cfg.get("height", 1024)
        self.sampler_name = sd_cfg.get("sampler_name", "DPM++ 2M Karras")

        # ── 输出目录 ──────────────────────────────────────────
        self.image_dir = Path(storage_cfg.get("image_dir", "./storage/images"))
        self.image_dir.mkdir(parents=True, exist_ok=True)

        self.images_per_post = config["content_rules"].get("images_per_post", 4)

        logger.info(f"ImageGenerator 初始化完成，图片来源模式: [{self.source}]")

    # ================================================================
    # 公共入口
    # ================================================================

    async def generate_post_images(
        self,
        style_name: str,
        topic: str,
        post_id: str = None,
    ) -> List[str]:
        """
        为单篇帖子获取 N 张图片（由 images_per_post 决定，默认4张）

        根据 self.source 路由到对应策略：
          - local            → _load_local_images()
          - stable_diffusion → _generate_via_sd()
          - auto             → 先尝试 SD，失败则 local

        Args:
            style_name: 装修风格名称
            topic     : 帖子主题（SD 模式用于构建 Prompt）
            post_id   : 帖子 ID，用于图片文件命名

        Returns:
            图片本地路径列表
        """
        if not post_id:
            post_id = str(uuid.uuid4())[:8]

        if self.source == self.SOURCE_LOCAL:
            return self._load_local_images(post_id)

        if self.source == self.SOURCE_SD:
            return await self._generate_via_sd(style_name, topic, post_id)

        # ── auto 模式：优先 SD，不可用时回退 local ─────────────
        if await self.check_api_health():
            result = await self._generate_via_sd(style_name, topic, post_id)
            if result:
                return result
            logger.warning("SD API 可达但生成失败，回退到本地图片")
        else:
            logger.warning("SD API 不可达，回退到本地图片")

        return self._load_local_images(post_id)

    # ================================================================
    # 策略一：本地图片（local / auto fallback）
    # ================================================================

    def _load_local_images(self, post_id: str) -> List[str]:
        """
        从 local_image_dir 目录随机抽取图片并复制到输出目录

        抽取规则：
        - 扫描目录下所有支持格式的图片文件
        - 随机抽取 images_per_post 张（不足时允许重复抽取）
        - 复制到 image_dir 并重命名为 {post_id}_img_{n}.png

        Args:
            post_id: 帖子 ID（用于文件命名）

        Returns:
            复制后的图片路径列表；目录为空时返回 []
        """
        candidates = [
            f for f in self.local_image_dir.iterdir()
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTS
        ]

        if not candidates:
            logger.error(
                f"本地图片目录为空: {self.local_image_dir}\n"
                "请向该目录放入 PNG/JPG 图片后重试，或切换为 stable_diffusion 模式"
            )
            return []

        # 不足 N 张时允许重复（有放回抽样）
        allow_repeat = len(candidates) < self.images_per_post
        selected = random.choices(candidates, k=self.images_per_post) \
            if allow_repeat \
            else random.sample(candidates, self.images_per_post)

        if allow_repeat:
            logger.warning(
                f"本地图片数量({len(candidates)})不足 {self.images_per_post} 张，"
                "已启用重复抽样"
            )

        image_paths = []
        for i, src_path in enumerate(selected):
            dst_name = f"{post_id}_img_{i+1}.png"
            dst_path = self.image_dir / dst_name
            self._copy_and_normalize(src_path, dst_path)
            image_paths.append(str(dst_path))
            logger.debug(f"本地图片 [{i+1}]: {src_path.name} → {dst_name}")

        logger.info(
            f"本地图片加载完成: {len(image_paths)} 张 "
            f"(来源: {self.local_image_dir})"
        )
        return image_paths

    def _copy_and_normalize(self, src: Path, dst: Path) -> None:
        """
        复制图片到目标路径，同时确保分辨率 ≥ 1024

        若原图分辨率不足，等比放大后再保存为 PNG。
        """
        img = Image.open(src)
        min_res = 1024
        if img.width < min_res or img.height < min_res:
            scale = max(min_res / img.width, min_res / img.height)
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            logger.debug(
                f"图片分辨率 {img.width}×{img.height} 不足，放大至 {new_w}×{new_h}"
            )
            img = img.resize((new_w, new_h), Image.LANCZOS)
        img.save(str(dst), format="PNG", optimize=True)

    # ================================================================
    # 策略二：Stable Diffusion API 生成
    # ================================================================

    async def _generate_via_sd(
        self,
        style_name: str,
        topic: str,
        post_id: str,
    ) -> List[str]:
        """
        调用 SD WebUI API 并发生成 N 张图片

        Args:
            style_name: 装修风格
            topic     : 帖子主题
            post_id   : 帖子 ID

        Returns:
            图片本地路径列表
        """
        logger.info(f"SD 生成图片: 风格={style_name}, 主题={topic}")

        tasks = [
            self._sd_generate_single(*build_sd_prompt(style_name, topic, index=i))
            for i in range(self.images_per_post)
        ]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error(f"SD 并发生成异常: {e}")
            return []

        image_paths = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"第 {i+1} 张 SD 图片生成失败: {result}")
                continue
            filename = f"{post_id}_img_{i+1}.png"
            path = self._save_sd_image(result, filename)
            image_paths.append(path)

        logger.info(f"SD 图片生成完成: {len(image_paths)}/{self.images_per_post} 张")
        return image_paths

    async def _sd_generate_single(
        self,
        positive_prompt: str,
        negative_prompt: str,
        seed: int = -1,
    ) -> bytes:
        """调用 SD /sdapi/v1/txt2img 生成单张图片，返回原始字节"""
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

        return base64.b64decode(data["images"][0])

    def _save_sd_image(self, img_bytes: bytes, filename: str) -> str:
        """保存 SD 生成的图片字节，校验并补足分辨率"""
        img = Image.open(io.BytesIO(img_bytes))
        min_res = 1024
        if img.width < min_res or img.height < min_res:
            logger.warning(f"SD 图片分辨率 {img.width}×{img.height} 不足，自动放大")
            img = img.resize(
                (max(img.width, min_res), max(img.height, min_res)),
                Image.LANCZOS,
            )
        save_path = self.image_dir / filename
        img.save(str(save_path), format="PNG", optimize=True)
        logger.debug(f"SD 图片已保存: {save_path} ({img.width}×{img.height})")
        return str(save_path)

    # ================================================================
    # 工具方法
    # ================================================================

    async def check_api_health(self) -> bool:
        """检查 SD API 是否可达（超时 5 秒）"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/sdapi/v1/sd-models",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    def get_local_image_count(self) -> int:
        """返回本地样例目录中的可用图片数量"""
        if not self.local_image_dir.exists():
            return 0
        return sum(
            1 for f in self.local_image_dir.iterdir()
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTS
        )
