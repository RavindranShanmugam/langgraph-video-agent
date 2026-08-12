"""Node 3 — select: Claude reasons over the transcript and picks the moments.

This is the only node that calls a model. It's non-fatal by design: if the API
is down, rate-limited, or returns something unusable, the conditional edge routes
to the even-split fallback and the run still produces clips.
"""

import json
import re

import anthropic

from ..bus import bus
from ..config import ANTHROPIC_API_KEY, EFFORT, MAX_TOKENS, MODEL, SHORT_MAX_SECS, SHORT_MIN_SECS
from ..runtime import node

CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "title": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["start", "end", "title", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are an expert short-form video editor (YouTube Shorts, Reels, TikTok). "
    "You find the moments in a long video that would perform best as standalone shorts. "
    "A great short is self-contained, has a strong hook in the first 2 seconds, and delivers "
    "one clear payoff. Titles are punchy and honest — never clickbait, never invented claims."
)


def _client() -> anthropic.Anthropic:
    # Falls back to the SDK's own credential resolution when the env var is unset.
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else anthropic.Anthropic()


def _build_prompt(segments_summary: list, full_text: str, num_clips: int) -> str:
    return (
        f"Pick the {num_clips} best moments from this video for short-form clips "
        f"(each {SHORT_MIN_SECS:.0f}-{SHORT_MAX_SECS:.0f} seconds).\n\n"
        "For each: give exact start/end times in seconds (aligned to the transcript segments), "
        "a short punchy title (max 6 words), and a one-line reason it works as a hook.\n\n"
        "Rules: clips must not overlap; each must stand on its own; prefer moments with a clear "
        "hook, a surprising point, or an actionable tip.\n\n"
        f"Transcript segments (start, end, text):\n{json.dumps(segments_summary, indent=1)}\n\n"
        f"Full transcript:\n{full_text[:6000]}"
    )


def _call_structured(client, prompt: str) -> list:
    """Preferred path — structured outputs guarantee schema-valid JSON."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": CLIP_SCHEMA},
        },
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(text).get("clips", [])


def _call_plain(client, prompt: str) -> list:
    """Fallback path — older SDK / model without structured outputs."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": prompt
                + '\n\nReturn ONLY a JSON object: {"clips": [{"start","end","title","reason"}]}',
            }
        ],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in the model response")
    return json.loads(match.group(0)).get("clips", [])


@node("select", retries=1, fatal=False)
def select(state: dict) -> dict:
    transcript = state.get("transcript") or {}
    segments = transcript.get("segments") or []

    segments_summary = [
        {"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"].strip()}
        for s in segments
    ]
    prompt = _build_prompt(segments_summary, transcript.get("text", ""), state["num_clips"])
    client = _client()

    bus.log("select", f"asking {MODEL} (effort={EFFORT}) for the best moments")
    try:
        clips = _call_structured(client, prompt)
    except anthropic.BadRequestError as err:
        # Most likely: this SDK/model combo doesn't accept output_config. Retry plain.
        bus.log("select", f"structured output rejected ({err.message[:80]}) — retrying plain")
        clips = _call_plain(client, prompt)

    if not clips:
        raise ValueError("model returned zero clips")

    bus.log("select", f"{len(clips)} moments proposed")
    return {"raw_clips": clips, "selection_source": "claude"}
