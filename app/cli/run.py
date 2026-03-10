from __future__ import annotations

import argparse

from rich.console import Console

from app.database.init_db import init_db
from app.workflows.graph import build_graph
from app.workflows.state import AgentState


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Xiaohongshu AI agent batch.")
    parser.add_argument("--batch-size", type=int, default=1)
    args = parser.parse_args()

    init_db()

    graph = build_graph()
    state = AgentState(batch_size=args.batch_size)
    out = graph.invoke(state)

    console = Console()
    console.print({"published_post_ids": out.published_post_ids, "failures": out.failures, "strategy_patch": out.outputs.get("strategy_patch")})


if __name__ == "__main__":
    main()

