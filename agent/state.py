"""The typed graph state.

Every node receives the whole state and returns a partial update. Fields with an
`operator.add` reducer are appended to rather than replaced, so nodes can record
errors without clobbering each other (and so parallel branches stay safe if this
graph ever fans out).
"""

import operator
from typing import Annotated, TypedDict


class Clip(TypedDict, total=False):
    clip_number: int
    start: float
    end: float
    title: str
    reason: str


class RenderedClip(TypedDict, total=False):
    clip_number: int
    title: str
    reason: str
    duration: float
    path: str
    filename: str


class NodeError(TypedDict):
    node: str
    error: str
    fatal: bool


class EditorState(TypedDict, total=False):
    # ── inputs ────────────────────────────────────────────────────────────────
    video_path: str
    work_dir: str
    output_dir: str
    num_clips: int
    whisper_model: str
    captions: bool
    uppercase: bool

    # ── ingest ────────────────────────────────────────────────────────────────
    audio_path: str
    duration: float
    audio_silent: bool

    # ── transcribe ────────────────────────────────────────────────────────────
    transcript: dict  # {"segments": [...], "text": "..."}

    # ── select / fallback ─────────────────────────────────────────────────────
    raw_clips: list
    selection_source: str  # "claude" | "even-split"

    # ── plan ──────────────────────────────────────────────────────────────────
    plan: list

    # ── render / assemble ─────────────────────────────────────────────────────
    rendered: list
    report: str
    manifest_path: str

    # ── diagnostics (append-only) ─────────────────────────────────────────────
    errors: Annotated[list, operator.add]
