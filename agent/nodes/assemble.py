"""Node 6 — assemble: write the manifest + a human-readable run report.

The manifest is the machine-readable output of the run (what got cut, from
where, and why), so a downstream step — an uploader, a review UI — doesn't have
to re-derive any of it.
"""

import json
from pathlib import Path

from ..bus import bus
from ..config import MODEL
from ..runtime import node


@node("assemble", retries=0, fatal=True)
def assemble(state: dict) -> dict:
    output_dir = Path(state["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    rendered = state.get("rendered") or []
    errors = state.get("errors") or []
    source = state.get("selection_source", "unknown")

    manifest = {
        "source_video": state["video_path"],
        "source_duration": round(state.get("duration", 0.0), 2),
        "selection": source,
        "model": MODEL if source == "claude" else None,
        "whisper_model": state.get("whisper_model"),
        "clips": rendered,
        "errors": errors,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    lines = [
        "# Run report",
        "",
        f"- Source: `{Path(state['video_path']).name}` ({state.get('duration', 0):.1f}s)",
        f"- Selection: **{source}**" + (f" (`{MODEL}`)" if source == "claude" else ""),
        f"- Clips rendered: **{len(rendered)}/{len(state.get('plan') or [])}**",
        "",
    ]
    for clip in rendered:
        lines.append(
            f"### {clip['clip_number']}. {clip['title']} ({clip['duration']}s)\n"
            f"- `{clip['filename']}`\n"
            f"- {clip['start']:.1f}s → {clip['end']:.1f}s\n"
            f"- Why: {clip['reason'] or '—'}\n"
        )
    if errors:
        lines.append("## Non-fatal errors\n")
        lines += [f"- **{e['node']}**: {e['error'][:300]}" for e in errors]

    report = "\n".join(lines)
    (output_dir / "report.md").write_text(report, encoding="utf-8")

    bus.log("assemble", f"manifest + report written to {output_dir}")
    return {"report": report, "manifest_path": str(manifest_path)}
