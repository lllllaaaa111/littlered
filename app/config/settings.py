from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/xhs_agent",
        alias="DATABASE_URL",
    )

    # Xiaohongshu automation
    xhs_base_url: str = Field(default="https://www.xiaohongshu.com", alias="XHS_BASE_URL")
    xhs_storage_state_path: str = Field(default="storage_state.json", alias="XHS_STORAGE_STATE_PATH")
    xhs_headless: bool = Field(default=False, alias="XHS_HEADLESS")

    # LLM (optional)
    llm_provider: Literal["none", "openai"] = Field(default="none", alias="LLM_PROVIDER")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # Stable Diffusion
    sd_model_id: str = Field(default="stabilityai/stable-diffusion-xl-base-1.0", alias="SD_MODEL_ID")
    sd_device: str = Field(default="cpu", alias="SD_DEVICE")  # "cuda" recommended
    sd_dtype: Literal["float16", "float32"] = Field(default="float16", alias="SD_DTYPE")
    sd_num_inference_steps: int = Field(default=30, alias="SD_NUM_INFERENCE_STEPS")
    sd_guidance_scale: float = Field(default=7.0, alias="SD_GUIDANCE_SCALE")
    sd_seed: int | None = Field(default=None, alias="SD_SEED")

    output_dir: str = Field(default="outputs", alias="OUTPUT_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    def output_path(self) -> Path:
        p = Path(self.output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def storage_state_path(self) -> Path:
        return Path(self.xhs_storage_state_path)


settings = Settings()

