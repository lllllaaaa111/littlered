from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.database.models import Post, Topic


def _dtype() -> torch.dtype:
    return torch.float16 if settings.sd_dtype == "float16" else torch.float32


class ImageGenerator:
    _pipe: StableDiffusionXLPipeline | None = None

    def _get_pipe(self) -> StableDiffusionXLPipeline:
        if self._pipe is not None:
            return self._pipe

        pipe = StableDiffusionXLPipeline.from_pretrained(
            settings.sd_model_id,
            torch_dtype=_dtype(),
            use_safetensors=True,
        )
        pipe.to(settings.sd_device)
        pipe.set_progress_bar_config(disable=True)
        self._pipe = pipe
        return pipe

    def build_prompt(self, *, post: Post, topic: Topic, strategy: dict[str, Any] | None = None) -> dict[str, str]:
        strategy = strategy or {}
        aesthetic = strategy.get("image_aesthetic", "clean, bright, lifestyle photo, high quality")
        brand = strategy.get("image_brand", "xiaohongshu style, trendy, minimal")
        base = f"{topic.title}. {topic.angle or ''}".strip()
        prompt = f"{base}, {aesthetic}, {brand}"
        negative = "low quality, blurry, watermark, text, logo, deformed, bad anatomy"
        return {"prompt": prompt, "negative_prompt": negative}

    def generate_for_post(self, *, post_id: int, session: Session) -> dict[str, Any]:
        post = session.get(Post, post_id)
        if post is None:
            raise ValueError(f"post {post_id} not found")
        topic = session.get(Topic, post.topic_id)
        if topic is None:
            raise ValueError(f"topic {post.topic_id} not found")

        prompts = self.build_prompt(post=post, topic=topic, strategy=post.style or {})
        prompt = prompts["prompt"]
        negative_prompt = prompts.get("negative_prompt")

        seed = settings.sd_seed
        if seed is None:
            seed = int(time.time()) % 2_147_483_647
        generator = torch.Generator(device=settings.sd_device).manual_seed(seed)

        pipe = self._get_pipe()
        out = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=settings.sd_num_inference_steps,
            guidance_scale=settings.sd_guidance_scale,
            generator=generator,
        )
        img: Image.Image = out.images[0]

        out_dir: Path = settings.output_path() / "images"
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = out_dir / f"post_{post_id}_{seed}.png"
        img.save(file_path)

        return {
            "post_id": post_id,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "model_id": settings.sd_model_id,
            "seed": seed,
            "width": img.size[0],
            "height": img.size[1],
            "steps": settings.sd_num_inference_steps,
            "guidance_scale": settings.sd_guidance_scale,
            "file_path": str(file_path),
        }

