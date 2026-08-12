#!/usr/bin/env python3
"""Streamlit UI for the LangGraph video-editing agent.

Upload a long video, watch the graph light up node by node, get vertical shorts.

Run with:
    streamlit run app.py
"""

import html
import shutil
import tempfile
import threading
import time
from pathlib import Path

import streamlit as st

from agent import bus, build_graph
from agent.bus import DONE, FAILED, NODES, PENDING, RETRY, RUNNING, SKIPPED
from agent.config import (
    ANTHROPIC_API_KEY,
    DEFAULT_NUM_CLIPS,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_WHISPER_MODEL,
    EFFORT,
    MODEL,
)
from agent.ffmpeg_tools import ffmpeg_available

st.set_page_config(page_title="LangGraph Video Agent", page_icon="🎬", layout="wide")

# ── Live graph rendering ──────────────────────────────────────────────────────

STATUS_STYLE = {
    PENDING: ("#8b8b8b", "transparent", "○"),
    RUNNING: ("#f5a623", "rgba(245,166,35,.16)", "◉"),
    RETRY: ("#f5a623", "rgba(245,166,35,.16)", "↻"),
    DONE: ("#2ea043", "rgba(46,160,67,.16)", "✔"),
    FAILED: ("#d1242f", "rgba(209,36,47,.16)", "✖"),
    SKIPPED: ("#8b8b8b", "transparent", "–"),
}

MAIN_PATH = ["ingest", "transcribe", "select", "plan", "render", "assemble"]
LABELS = dict(NODES)


def _chip(key: str, status: str) -> str:
    color, background, glyph = STATUS_STYLE.get(status, STATUS_STYLE[PENDING])
    weight = "600" if status in (RUNNING, RETRY) else "500"
    return (
        f'<span style="display:inline-block;padding:7px 13px;margin:3px;border-radius:9px;'
        f'border:1.5px solid {color};background:{background};color:{color};'
        f'font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;'
        f'font-weight:{weight};white-space:nowrap;">{glyph}&nbsp;{LABELS[key]}</span>'
    )


def render_graph_html(snapshot: dict) -> str:
    status = snapshot["status"]
    arrow = '<span style="color:#8b8b8b;margin:0 2px;">→</span>'
    main = arrow.join(_chip(key, status[key]) for key in MAIN_PATH)

    branch = (
        '<div style="margin-left:190px;margin-top:2px;">'
        '<span style="color:#8b8b8b;font-family:monospace;">└─ alt&nbsp;</span>'
        f'{_chip("fallback", status["fallback"])}'
        '<span style="color:#8b8b8b;font-family:monospace;">&nbsp;→ Plan</span>'
        "</div>"
    )

    progress = ""
    if snapshot["progress"] and status["render"] in (RUNNING, RETRY):
        current, total = snapshot["progress"]
        progress = (
            f'<div style="margin-top:6px;color:#8b8b8b;font-family:monospace;font-size:12px;">'
            f"rendering {current}/{total}</div>"
        )

    route = ""
    if snapshot["route"]:
        route = (
            f'<div style="margin-top:6px;color:#8b8b8b;font-family:monospace;font-size:12px;">'
            f"last route → {html.escape(snapshot['route'])}</div>"
        )

    return f'<div style="line-height:2.1;">{main}{branch}{progress}{route}</div>'


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Settings")
    num_clips = st.slider("Number of shorts", 1, 6, DEFAULT_NUM_CLIPS)
    whisper_model = st.selectbox(
        "Transcription quality",
        ["base", "small", "medium"],
        index=["base", "small", "medium"].index(DEFAULT_WHISPER_MODEL)
        if DEFAULT_WHISPER_MODEL in ("base", "small", "medium")
        else 1,
        help="'small' is a good default. 'medium' is the most accurate (best captions) but slowest.",
    )
    do_captions = st.checkbox("Animated captions", value=True)
    uppercase = st.checkbox("UPPERCASE captions", value=False)
    output_dir = st.text_input("Output folder", value=str(DEFAULT_OUTPUT_DIR))

    st.divider()
    st.subheader("System check")
    if ffmpeg_available():
        st.success("ffmpeg on PATH")
    else:
        st.error("ffmpeg not found on PATH")
    if ANTHROPIC_API_KEY:
        st.success(f"Claude ready — `{MODEL}` (effort: {EFFORT})")
    else:
        st.warning("No ANTHROPIC_API_KEY — the graph will route to the even-split fallback.")
        st.caption("Set it in `.env` next to app.py, or as an environment variable.")

# ── Main ──────────────────────────────────────────────────────────────────────

st.title("🎬 LangGraph Video Agent")
st.caption(
    "Long video → vertical shorts. Transcription, selection, reasoning, tool calls and "
    "assembly each run as their own graph node with their own retry and error handling."
)

PREVIEW_LIMIT_MB = 200  # above this, previewing in-browser is slower than it's worth

source_mode = st.radio(
    "Where's the video?",
    ["On this computer", "Upload a file"],
    horizontal=True,
    help="Long-form sources are often over a gigabyte — pointing at the file on disk "
    "skips the upload entirely and starts instantly.",
)

source_path: str | None = None
uploaded = None

if source_mode == "On this computer":
    typed = st.text_input(
        "Full path to the video",
        placeholder=r"C:\Users\ravin\Videos\RavsDigital\...\my_video.mp4",
    )
    typed = (typed or "").strip().strip('"')
    if typed:
        candidate = Path(typed)
        if not candidate.exists():
            st.error(f"No file at that path: {candidate}")
        elif candidate.is_dir():
            st.error("That's a folder — point at the video file itself.")
        else:
            source_path = str(candidate)
            size_mb = candidate.stat().st_size / 1_000_000
            st.caption(f"{candidate.name} — {size_mb:,.0f} MB")
else:
    uploaded = st.file_uploader(
        "Upload your video",
        type=["mp4", "mov", "avi", "mkv", "webm"],
        help="Fine for short clips. For anything large, use 'On this computer' instead.",
    )

graph_slot = st.empty()
log_slot = st.empty()

if not source_path and not uploaded:
    graph_slot.markdown(render_graph_html(bus.snapshot()), unsafe_allow_html=True)
    st.info("Point at a video to get started.")
else:
    if uploaded is not None:
        st.video(uploaded)
    elif source_path and Path(source_path).stat().st_size <= PREVIEW_LIMIT_MB * 1_000_000:
        st.video(source_path)
    else:
        st.caption("Preview skipped — file is large. It'll still process normally.")

    if st.button("Run the graph", type="primary", use_container_width=True):
        bus.reset()
        work_dir = tempfile.mkdtemp(prefix="lgva_")
        if source_path:
            # Already on disk — read it in place rather than copying a gigabyte around.
            video_path = source_path
        else:
            video_path = str(Path(work_dir) / uploaded.name)
            with open(video_path, "wb") as handle:
                handle.write(uploaded.getbuffer())

        initial_state = {
            "video_path": video_path,
            "work_dir": work_dir,
            "output_dir": output_dir,
            "num_clips": num_clips,
            "whisper_model": whisper_model,
            "captions": do_captions,
            "uppercase": uppercase,
            "errors": [],
        }

        result: dict = {}

        def run_graph():
            """Runs on a worker thread so the main thread can repaint the graph."""
            try:
                result["state"] = build_graph().invoke(initial_state)
            except Exception as err:  # noqa: BLE001 - surfaced in the UI below
                result["error"] = err
            finally:
                bus.finish()

        worker = threading.Thread(target=run_graph, daemon=True)
        worker.start()

        while True:
            snapshot = bus.snapshot()
            graph_slot.markdown(render_graph_html(snapshot), unsafe_allow_html=True)
            recent = snapshot["log"][-14:]
            log_slot.code(
                "\n".join(f"{e['t']}  {e['node']:<10} {e['m']}" for e in recent) or "waiting…",
                language=None,
            )
            if snapshot["finished"] and not worker.is_alive():
                break
            time.sleep(0.4)

        worker.join()
        shutil.rmtree(work_dir, ignore_errors=True)

        st.session_state["result"] = result
        st.rerun()

# ── Results ───────────────────────────────────────────────────────────────────

stored = st.session_state.get("result")
if stored:
    graph_slot.markdown(render_graph_html(bus.snapshot()), unsafe_allow_html=True)

    if stored.get("error"):
        st.error(f"The run stopped: {stored['error']}")
        st.caption("A fatal node failed. Check the log above and `agent.log` for the full trace.")
    else:
        state = stored["state"]
        clips = state.get("rendered") or []
        source = state.get("selection_source")

        if clips:
            st.success(f"{len(clips)} vertical shorts — selection by **{source}**")
        else:
            st.error("The graph completed but no clip rendered. See the errors below.")

        for clip in clips:
            st.divider()
            st.subheader(f"{clip['clip_number']}. {clip['title']}")
            st.caption(f"{clip['duration']}s — {clip['reason'] or 'no reason given'}")
            path = Path(clip["path"])
            if path.exists():
                data = path.read_bytes()
                st.video(data)
                st.download_button(
                    f"Download {clip['filename']}",
                    data=data,
                    file_name=clip["filename"],
                    mime="video/mp4",
                    use_container_width=True,
                    key=f"dl-{clip['clip_number']}",
                )
            else:
                st.warning(f"File missing on disk: {path}")

        errors = state.get("errors") or []
        if errors:
            with st.expander(f"Non-fatal errors ({len(errors)}) — the run continued"):
                for err in errors:
                    st.markdown(f"**{err['node']}** — {err['error'][:600]}")

        if state.get("report"):
            with st.expander("Run report"):
                st.markdown(state["report"])
