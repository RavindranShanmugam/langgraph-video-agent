"""Configuration + environment loading.

Everything tunable lives here so the nodes stay boring.
"""

import logging
import os
from pathlib import Path

# Windows TLS: make Python's HTTPS (used by the anthropic SDK) trust the OS cert store.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover - optional dependency
    pass

PROJECT_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    """Minimal .env loader (no dependency on python-dotenv)."""
    try:
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


_load_env_file(PROJECT_DIR / ".env")
_load_env_file(Path.home() / ".env")


# ── Model ─────────────────────────────────────────────────────────────────────
# Defaults to Sonnet 5 (Ravi's primary LLM). Set MODEL=claude-opus-5 in .env for
# noticeably better clip picks on long / rambling source footage.
MODEL = os.environ.get("MODEL", "claude-sonnet-5").strip()
EFFORT = os.environ.get("EFFORT", "medium").strip()  # low | medium | high | xhigh | max
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "8000"))

ANTHROPIC_API_KEY = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()

# ── Clip rules ────────────────────────────────────────────────────────────────
SHORT_MIN_SECS = float(os.environ.get("SHORT_MIN_SECS", "15"))
SHORT_MAX_SECS = float(os.environ.get("SHORT_MAX_SECS", "60"))
DEFAULT_NUM_CLIPS = int(os.environ.get("NUM_CLIPS", "3"))
DEFAULT_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")

# ── Vertical canvas ───────────────────────────────────────────────────────────
OUT_W, OUT_H = 1080, 1920

# ── Caption look (ASS styling) ────────────────────────────────────────────────
CAPTION_FONT = "Arial Black"
CAPTION_SIZE = 92
CAPTION_HL_COLOR = "&H0000FFFF"  # active word  -> yellow  (ASS is &HAABBGGRR)
CAPTION_FG_COLOR = "&H00FFFFFF"  # upcoming     -> white
CAPTION_OUTLINE = "&H00000000"  # outline      -> black
CAPTION_MARGIN_V = 520
WORDS_PER_CAPTION = 4
CAPTION_GAP_BREAK = 0.6

# ── Node retry policy ─────────────────────────────────────────────────────────
RETRIES = int(os.environ.get("NODE_RETRIES", "2"))
RETRY_BACKOFF = float(os.environ.get("NODE_RETRY_BACKOFF", "1.5"))

# ── Output ────────────────────────────────────────────────────────────────────
DEFAULT_OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", str(PROJECT_DIR / "shorts")))

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_FILE = PROJECT_DIR / "agent.log"


def setup_logging(level: str = "INFO") -> logging.Logger:
    log = logging.getLogger("video_agent")
    if log.handlers:
        return log
    log.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    log.addHandler(stream)

    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(fmt)
        log.addHandler(file_handler)
    except Exception:
        pass  # read-only dir etc. — console logging is enough

    log.propagate = False
    return log
