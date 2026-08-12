"""Word-level animated captions as a styled ASS file.

Whole phrase on screen, active word highlighted (karaoke `\\k` timing). Word
timings come straight from Whisper, offset to the clip start — which is why the
captions never drift out of sync with the cut.
"""

from pathlib import Path

from .config import (
    CAPTION_FG_COLOR,
    CAPTION_FONT,
    CAPTION_GAP_BREAK,
    CAPTION_HL_COLOR,
    CAPTION_MARGIN_V,
    CAPTION_OUTLINE,
    CAPTION_SIZE,
    OUT_H,
    OUT_W,
    WORDS_PER_CAPTION,
)


def _segment_words(segment: dict) -> list:
    """Word timings for a segment, synthesised if Whisper didn't provide them.

    When word-level alignment fails we still have segment text and boundaries —
    spreading the words evenly across the segment gives captions that are close
    enough to read along with, instead of no captions at all.
    """
    words = segment.get("words") or []
    if words:
        return words

    tokens = (segment.get("text") or "").split()
    if not tokens:
        return []

    start, end = float(segment["start"]), float(segment["end"])
    step = (end - start) / len(tokens)
    return [
        {"word": token, "start": start + i * step, "end": start + (i + 1) * step}
        for i, token in enumerate(tokens)
    ]


def clip_words(segments: list, clip_start: float, clip_end: float) -> list:
    """Words inside the clip, timestamped relative to the clip start."""
    words = []
    for segment in segments:
        for word in _segment_words(segment):
            w_start, w_end = word.get("start"), word.get("end")
            if w_start is None or w_end is None or w_end <= clip_start or w_start >= clip_end:
                continue
            words.append(
                {
                    "text": word["word"].strip(),
                    "start": max(0.0, w_start - clip_start),
                    "end": max(0.0, min(w_end, clip_end) - clip_start),
                }
            )
    return words


def _group_words(words: list) -> list:
    chunks, current = [], []
    for word in words:
        too_long = len(current) >= WORDS_PER_CAPTION
        big_pause = current and (word["start"] - current[-1]["end"]) > CAPTION_GAP_BREAK
        if current and (too_long or big_pause):
            chunks.append(current)
            current = []
        current.append(word)
    if current:
        chunks.append(current)
    return chunks


def _ass_time(seconds: float) -> str:
    centis = int(round(max(0.0, seconds) * 100))
    hours, centis = divmod(centis, 360000)
    minutes, centis = divmod(centis, 6000)
    secs, centis = divmod(centis, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def build_ass(words: list, path: str, uppercase: bool = False) -> int:
    style = (
        f"Style: Default,{CAPTION_FONT},{CAPTION_SIZE},"
        f"{CAPTION_HL_COLOR},{CAPTION_FG_COLOR},{CAPTION_OUTLINE},&H64000000,"
        f"-1,0,0,0,100,100,0,0,1,6,3,2,60,60,{CAPTION_MARGIN_V},1"
    )
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {OUT_W}\nPlayResY: {OUT_H}\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    lines = []
    for chunk in _group_words(words):
        parts = []
        for i, word in enumerate(chunk):
            next_start = chunk[i + 1]["start"] if i + 1 < len(chunk) else word["end"]
            karaoke = max(1, int(round((next_start - word["start"]) * 100)))
            text = word["text"].replace("{", "").replace("}", "")
            if uppercase:
                text = text.upper()
            parts.append("{\\k%d}%s " % (karaoke, text))
        body = "".join(parts).strip()
        start, end = _ass_time(chunk[0]["start"]), _ass_time(chunk[-1]["end"])
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{body}")

    Path(path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)
