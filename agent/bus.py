"""Thread-safe status bus.

The graph runs on a worker thread; the UI polls this from the main thread.
Nothing in here imports Streamlit, so the same bus drives the CLI runner.
"""

import threading
import time

# Display order of the graph. `fallback` sits on the alternate branch.
NODES = [
    ("ingest", "Ingest"),
    ("transcribe", "Transcribe"),
    ("select", "Select"),
    ("fallback", "Fallback"),
    ("plan", "Plan"),
    ("render", "Render"),
    ("assemble", "Assemble"),
]

PENDING = "pending"
RUNNING = "running"
RETRY = "retry"
DONE = "done"
FAILED = "failed"
SKIPPED = "skipped"


class Bus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._status = {key: PENDING for key, _ in NODES}
            self._log: list[dict] = []
            self._route: str | None = None
            self._progress: tuple[int, int] | None = None
            self._finished = False
            self._fatal: str | None = None

    # ── writes (worker thread) ────────────────────────────────────────────────
    def start(self, node: str, message: str | None = None) -> None:
        with self._lock:
            self._status[node] = RUNNING
        if message:
            self.log(node, message)

    def retry(self, node: str, attempt: int, err: Exception) -> None:
        with self._lock:
            self._status[node] = RETRY
        self.log(node, f"attempt {attempt} failed ({type(err).__name__}: {err}) — retrying")

    def done(self, node: str, message: str | None = None) -> None:
        with self._lock:
            self._status[node] = DONE
        if message:
            self.log(node, message)

    def fail(self, node: str, err: BaseException, fatal: bool) -> None:
        with self._lock:
            self._status[node] = FAILED
            if fatal:
                self._fatal = f"{node}: {err}"
        self.log(node, f"{'FATAL' if fatal else 'failed'} — {err}")

    def skip(self, node: str) -> None:
        with self._lock:
            if self._status[node] == PENDING:
                self._status[node] = SKIPPED

    def route(self, choice: str, message: str) -> None:
        with self._lock:
            self._route = choice
        self.log("route", message)

    def progress(self, current: int, total: int) -> None:
        with self._lock:
            self._progress = (current, total)

    def log(self, node: str, message: str) -> None:
        with self._lock:
            self._log.append({"t": time.strftime("%H:%M:%S"), "node": node, "m": message})

    def finish(self) -> None:
        with self._lock:
            self._finished = True

    # ── reads (UI thread) ─────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": dict(self._status),
                "log": list(self._log),
                "route": self._route,
                "progress": self._progress,
                "finished": self._finished,
                "fatal": self._fatal,
            }


bus = Bus()
