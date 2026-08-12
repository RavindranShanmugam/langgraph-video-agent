"""Node 1 — ingest: verify the toolchain, probe the video, pull the audio.

Fatal on failure. If there's no readable video there is nothing downstream can
do, so this is the one node where stopping the run is the correct behaviour.
"""

from pathlib import Path

from ..bus import bus
from ..ffmpeg_tools import (
    FFmpegError,
    extract_audio,
    ffmpeg_available,
    mean_volume_db,
    probe_duration,
)
from ..runtime import node

# Digital silence sits around -91 dBFS; real speech, even quiet, sits well above -60.
SILENCE_DB = -60.0


@node("ingest", retries=1, fatal=True)
def ingest(state: dict) -> dict:
    video_path = state["video_path"]
    if not Path(video_path).exists():
        raise FileNotFoundError(f"video not found: {video_path}")
    if not ffmpeg_available():
        raise FFmpegError("ffmpeg/ffprobe not found on PATH — install ffmpeg first")

    duration = probe_duration(video_path)
    bus.log("ingest", f"source is {duration:.1f}s")

    audio_path = str(Path(state["work_dir"]) / "audio.wav")
    extract_audio(video_path, audio_path)

    # Catch a silent track here rather than letting it masquerade as a model
    # failure ten minutes later: Whisper hallucinates filler on silence, and the
    # selection node then correctly reports "no good moments" for the wrong reason.
    volume = mean_volume_db(audio_path)
    silent = volume is not None and volume <= SILENCE_DB
    if silent:
        bus.log(
            "ingest",
            f"audio is silent ({volume:.0f} dB) — skipping transcription, "
            "clips will be evenly spaced",
        )
    else:
        level = f"{volume:.0f} dB" if volume is not None else "level unknown"
        bus.log("ingest", f"audio extracted (16 kHz mono, {level})")

    return {"duration": duration, "audio_path": audio_path, "audio_silent": silent}
