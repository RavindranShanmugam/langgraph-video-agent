"""The graph.

    START → ingest → transcribe ─┬─(has speech)──→ select ─┬─(clips)──→ plan → render → assemble → END
                                 │                          │
                                 └─(no speech)───→ fallback ←┘ (no clips)

Two conditional edges carry the real decisions. Everything else is a straight
line, which is the point: the branching lives in the graph rather than buried in
an `if` inside a 400-line script.
"""

from langgraph.graph import END, START, StateGraph

from .bus import bus
from .nodes import assemble, fallback, ingest, plan, render, select, transcribe
from .state import EditorState


def route_after_transcribe(state: EditorState) -> str:
    """No usable transcript → skip the model entirely, go straight to even-split."""
    segments = (state.get("transcript") or {}).get("segments") or []
    if segments:
        bus.route("select", f"transcript has {len(segments)} segments → Select")
        return "select"
    bus.skip("select")
    bus.route("fallback", "no transcript → Fallback (even split)")
    return "fallback"


def route_after_select(state: EditorState) -> str:
    """Model gave us nothing usable → fall back rather than fail the run."""
    if state.get("raw_clips"):
        bus.skip("fallback")
        bus.route("plan", f"{len(state['raw_clips'])} clips from the model → Plan")
        return "plan"
    bus.route("fallback", "model returned no clips → Fallback (even split)")
    return "fallback"


def build_graph():
    graph = StateGraph(EditorState)

    graph.add_node("ingest", ingest)
    graph.add_node("transcribe", transcribe)
    graph.add_node("select", select)
    graph.add_node("fallback", fallback)
    graph.add_node("plan", plan)
    graph.add_node("render", render)
    graph.add_node("assemble", assemble)

    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "transcribe")
    graph.add_conditional_edges(
        "transcribe", route_after_transcribe, {"select": "select", "fallback": "fallback"}
    )
    graph.add_conditional_edges(
        "select", route_after_select, {"plan": "plan", "fallback": "fallback"}
    )
    graph.add_edge("fallback", "plan")
    graph.add_edge("plan", "render")
    graph.add_edge("render", "assemble")
    graph.add_edge("assemble", END)

    return graph.compile()
