"""Node 4 — plan: validate and clamp whatever selection produced.

Model output and fallback output land in the same shape here, so the renderer
downstream only ever sees clips it can actually cut: inside the source duration,
within the length rules, non-overlapping, numbered.
"""

from ..bus import bus
from ..config import SHORT_MAX_SECS, SHORT_MIN_SECS
from ..runtime import node


@node("plan", retries=0, fatal=True)
def plan(state: dict) -> dict:
    duration = state["duration"]
    planned: list[dict] = []
    dropped = 0

    for clip in state.get("raw_clips") or []:
        try:
            start = max(0.0, float(clip["start"]))
            end = min(duration, float(clip["end"]))
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue

        if end - start < SHORT_MIN_SECS:
            end = min(duration, start + SHORT_MIN_SECS)
        if end - start > SHORT_MAX_SECS:
            end = start + SHORT_MAX_SECS
        if end - start < 2:
            dropped += 1
            continue

        # Drop anything that overlaps a clip we've already accepted.
        if any(start < kept["end"] and end > kept["start"] for kept in planned):
            dropped += 1
            continue

        planned.append(
            {
                "start": start,
                "end": end,
                "title": str(clip.get("title") or f"Clip {len(planned) + 1}"),
                "reason": str(clip.get("reason") or ""),
            }
        )

    planned.sort(key=lambda c: c["start"])
    for i, clip in enumerate(planned, 1):
        clip["clip_number"] = i

    if not planned:
        raise ValueError("no clip survived validation")

    bus.log("plan", f"{len(planned)} clips validated" + (f", {dropped} dropped" if dropped else ""))
    return {"plan": planned}
