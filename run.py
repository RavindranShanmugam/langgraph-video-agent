#!/usr/bin/env python3
"""Headless runner — same graph, no UI.

    python run.py path/to/video.mp4 --clips 3 --whisper small
"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from agent import bus, build_graph
from agent.config import DEFAULT_NUM_CLIPS, DEFAULT_OUTPUT_DIR, DEFAULT_WHISPER_MODEL, setup_logging

log = setup_logging()


def main() -> int:
    # Windows consoles default to cp1252 and choke on the report's arrows/em-dashes.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Turn a long video into vertical shorts.")
    parser.add_argument("video", help="path to the source video")
    parser.add_argument("--clips", type=int, default=DEFAULT_NUM_CLIPS, help="how many shorts")
    parser.add_argument("--whisper", default=DEFAULT_WHISPER_MODEL, choices=["base", "small", "medium"])
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR), help="output folder")
    parser.add_argument("--no-captions", action="store_true")
    parser.add_argument("--uppercase", action="store_true")
    args = parser.parse_args()

    if not Path(args.video).exists():
        log.error("no such file: %s", args.video)
        return 1

    bus.reset()
    work_dir = tempfile.mkdtemp(prefix="lgva_")
    try:
        final = build_graph().invoke(
            {
                "video_path": str(Path(args.video).resolve()),
                "work_dir": work_dir,
                "output_dir": args.out,
                "num_clips": args.clips,
                "whisper_model": args.whisper,
                "captions": not args.no_captions,
                "uppercase": args.uppercase,
                "errors": [],
            }
        )
    except Exception as err:  # noqa: BLE001 - top-level runner
        log.error("run stopped: %s", err)
        return 1
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    rendered = final.get("rendered") or []
    print("\n" + (final.get("report") or ""))
    for err in final.get("errors") or []:
        log.warning("non-fatal [%s]: %s", err["node"], err["error"][:300])

    return 0 if rendered else 1


if __name__ == "__main__":
    raise SystemExit(main())
