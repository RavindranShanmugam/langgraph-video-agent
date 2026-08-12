"""Node 5 — render: the tool calls. One ffmpeg pass per clip.

Failures are isolated per clip: a cut that ffmpeg refuses is recorded and the
node moves on to the next one. Losing clip 2 shouldn't cost you clips 1 and 3.
"""

from pathlib import Path

from ..bus import bus
from ..captions import build_ass, clip_words
from ..ffmpeg_tools import render_short, safe_filename
from ..runtime import node


@node("render", retries=0, fatal=True)
def render(state: dict) -> dict:
    work_dir = state["work_dir"]
    output_dir = Path(state["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    segments = (state.get("transcript") or {}).get("segments") or []
    want_captions = state.get("captions", True)
    uppercase = state.get("uppercase", False)

    plan = state["plan"]
    rendered: list[dict] = []
    errors: list[dict] = []

    for index, clip in enumerate(plan, 1):
        number = clip["clip_number"]
        bus.progress(index - 1, len(plan))
        bus.log("render", f"cutting {index}/{len(plan)}: {clip['title']}")

        ass_name = ""
        if want_captions and segments:
            words = clip_words(segments, clip["start"], clip["end"])
            if words:
                ass_name = f"clip_{number}.ass"
                build_ass(words, str(Path(work_dir) / ass_name), uppercase=uppercase)

        out_path = output_dir / f"short_{number}_{safe_filename(clip['title'])}.mp4"
        try:
            ok, stderr = render_short(
                state["video_path"], clip["start"], clip["end"], str(out_path), ass_name, work_dir
            )
        except Exception as err:  # noqa: BLE001 - one clip failing must not end the node
            ok, stderr = False, str(err)

        if not ok:
            bus.log("render", f"clip {number} failed — keeping the rest")
            errors.append({"node": "render", "error": f"clip {number}: {stderr[-400:]}", "fatal": False})
            continue

        rendered.append(
            {
                "clip_number": number,
                "title": clip["title"],
                "reason": clip["reason"],
                "duration": round(clip["end"] - clip["start"], 1),
                "start": clip["start"],
                "end": clip["end"],
                "path": str(out_path),
                "filename": out_path.name,
                "captions": bool(ass_name),
            }
        )

    bus.progress(len(plan), len(plan))
    bus.log("render", f"{len(rendered)}/{len(plan)} clips rendered")
    return {"rendered": rendered, "errors": errors}
