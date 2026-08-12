"""Node 2 — transcribe: Whisper with word-level timestamps.

Non-fatal. A failed transcription costs us smart clip picking and captions, but
the graph can still route to the even-split fallback and produce cuts.
"""

from ..bus import bus
from ..runtime import node

_MODEL_CACHE: dict = {}


def _load(name: str):
    """Module-level cache — a Whisper model load is slow and Streamlit's own
    cache decorators don't work from the graph's worker thread."""
    if name not in _MODEL_CACHE:
        import whisper

        bus.log("transcribe", f"loading whisper '{name}' (first run downloads weights)")
        _MODEL_CACHE[name] = whisper.load_model(name)
    return _MODEL_CACHE[name]


@node("transcribe", retries=1, fatal=False)
def transcribe(state: dict) -> dict:
    if state.get("audio_silent"):
        # No point burning a Whisper pass on silence — it returns hallucinated
        # filler ("you you you"), which then reads downstream as a model failure.
        bus.log("transcribe", "skipped — no audio to transcribe")
        return {"transcript": {"segments": [], "text": ""}}

    model_name = state.get("whisper_model", "small")
    model = _load(model_name)
    audio_path = state["audio_path"]

    bus.log("transcribe", f"transcribing with '{model_name}' — this is the slow part")
    try:
        result = model.transcribe(audio_path, verbose=False, word_timestamps=True)
    except Exception as err:  # noqa: BLE001 - degrade rather than lose the transcript
        # Whisper's word-timestamp alignment crashes on an empty segment
        # ("cannot reshape tensor of 0 elements"). It's intermittent because
        # temperature fallback makes decoding nondeterministic — the same file
        # can succeed one run and crash the next. Losing word timings costs us
        # karaoke captions; losing the transcript would cost us the whole point
        # of the tool, so drop the timings and keep going.
        bus.log(
            "transcribe",
            f"word timings failed ({type(err).__name__}) — retrying without them; "
            "captions will be line-level",
        )
        result = model.transcribe(audio_path, verbose=False, word_timestamps=False)

    segments = result.get("segments", []) or []
    text = result.get("text", "") or ""
    words = sum(len(s.get("words", []) or []) for s in segments)
    bus.log("transcribe", f"{len(segments)} segments, {words} word timings")

    return {"transcript": {"segments": segments, "text": text}}
