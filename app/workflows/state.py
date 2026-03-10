from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    batch_size: int = 1
    strategy: dict[str, Any] = field(default_factory=dict)

    topic_ids: list[int] = field(default_factory=list)
    post_ids: list[int] = field(default_factory=list)

    published_post_ids: list[int] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

    outputs: dict[str, Any] = field(default_factory=dict)

