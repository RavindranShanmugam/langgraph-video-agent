"""Alternate branch — even-split selection.

Reached when there's no usable transcript or the model didn't return clips.
Dumb on purpose: it exists so the run always produces something.
"""

from ..bus import bus
from ..runtime import node


@node("fallback", retries=0, fatal=True)
def fallback(state: dict) -> dict:
    duration = state["duration"]
    count = max(1, state["num_clips"])
    span = duration / count

    clips = [
        {
            "start": round(i * span, 2),
            "end": round(min((i + 1) * span, duration), 2),
            "title": f"Clip {i + 1}",
            "reason": "Evenly spaced (no smart selection available)",
        }
        for i in range(count)
    ]
    bus.log("fallback", f"{count} evenly spaced clips of ~{span:.0f}s")
    return {"raw_clips": clips, "selection_source": "even-split"}
