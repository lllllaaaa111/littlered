from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.workflows.nodes import (
    analyze_comments,
    collect_metrics,
    generate_images,
    generate_posts,
    generate_topics,
    load_strategy,
    publish_posts,
    update_strategy,
)
from app.workflows.state import AgentState


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("load_strategy", load_strategy)
    g.add_node("generate_topics", generate_topics)
    g.add_node("generate_posts", generate_posts)
    g.add_node("generate_images", generate_images)
    g.add_node("publish_posts", publish_posts)
    g.add_node("collect_metrics", collect_metrics)
    g.add_node("analyze_comments", analyze_comments)
    g.add_node("update_strategy", update_strategy)

    g.set_entry_point("load_strategy")
    g.add_edge("load_strategy", "generate_topics")
    g.add_edge("generate_topics", "generate_posts")
    g.add_edge("generate_posts", "generate_images")
    g.add_edge("generate_images", "publish_posts")
    g.add_edge("publish_posts", "collect_metrics")
    g.add_edge("collect_metrics", "analyze_comments")
    g.add_edge("analyze_comments", "update_strategy")
    g.add_edge("update_strategy", END)

    return g.compile()

