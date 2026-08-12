"""The tool layer — every shell-out to ffmpeg/ffprobe lives here.

Nodes call these; nothing else in the package touches subprocess.
"""

import re
import subprocess
from pathlib import Path

from .config import OUT_H, OUT_W


class FFmpegError(RuntimeError):
    pass


def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def ffmpeg_available() -> bool:
    try:
        _run(["ffmpeg", "-version"])
        _run(["ffprobe", "-version"])
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def probe_duration(video_path: str) -> float:
    result = _run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
    )
    try:
        duration = float(result.stdout.strip())
    except (TypeError, ValueError):
        raise FFmpegError(f"ffprobe could not read a duration from {video_path}: {result.stderr[-400:]}")
    if duration <= 0:
        raise FFmpegError(f"{video_path} reports a duration of {duration}s")
    return duration


def extract_audio(video_path: str, output_path: str) -> str:
    result = _run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            output_path,
        ]
    )
    if result.returncode != 0 or not Path(output_path).exists():
        raise FFmpegError(f"audio extraction failed: {result.stderr[-600:]}")
    return output_path


def mean_volume_db(audio_path: str) -> float | None:
    """Mean volume of a track in dBFS, or None if ffmpeg didn't report one.

    Digital silence reads around -91 dB. Used to tell "this audio has no speech"
    apart from "the model didn't like the transcript" — without it, a silent
    track surfaces as a confusing selection failure several minutes later.
    """
    result = _run(["ffmpeg", "-i", audio_path, "-af", "volumedetect", "-f", "null", "-"])
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", result.stderr or "")
    return float(match.group(1)) if match else None


def render_short(
    src: str,
    start: float,
    end: float,
    out_path: str,
    ass_name: str,
    work_dir: str,
) -> tuple[bool, str]:
    """Cut + blur-fill to vertical + burn captions in one pass.

    Returns (ok, stderr) instead of raising — the render node isolates failures
    per clip so one bad cut doesn't lose the others.
    """
    duration = end - start
    graph = (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W}:{OUT_H},boxblur=40:1,eq=brightness=-0.18[bgb];"
        f"[fg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2[base]"
    )
    if ass_name:
        graph += f";[base]subtitles={ass_name}[v]"
        video_out = "[v]"
    else:
        video_out = "[base]"

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}", "-i", src, "-t", f"{duration:.3f}",
        "-filter_complex", graph,
        "-map", video_out, "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-r", "30",
        out_path,
    ]
    # cwd=work_dir so the subtitles filter can reference the .ass by bare filename
    # (dodges Windows drive-letter ':' escaping headaches).
    result = _run(cmd, cwd=work_dir)
    return result.returncode == 0, result.stderr


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "", name)
    cleaned = cleaned.replace(" ", "_").strip("._")
    return cleaned[:40] or "clip"
