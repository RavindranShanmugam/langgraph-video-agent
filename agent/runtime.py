"""Node wrapper: retry, error capture, status reporting.

This is the piece that makes "a failure in one stage doesn't collapse the run"
true rather than aspirational. Each node declares its own retry count and whether
its failure is fatal:

  * fatal=True   -> the exception propagates and the graph stops (no video, no run)
  * fatal=False  -> the error is recorded in state["errors"] and the graph routes on

LangGraph also ships a RetryPolicy you can pass to `add_node`, but its keyword
name has moved between releases; a plain decorator keeps this version-proof and
lets us push status to the bus on every attempt.
"""

import functools
import time

from .bus import bus
from .config import RETRIES, RETRY_BACKOFF, setup_logging

log = setup_logging()


def node(name: str, retries: int = RETRIES, fatal: bool = True, backoff: float = RETRY_BACKOFF):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(state):
            bus.start(name)
            log.info("node %s: start", name)
            last_err: BaseException | None = None

            for attempt in range(1, retries + 2):
                try:
                    update = fn(state) or {}
                    log.info("node %s: done", name)
                    bus.done(name)
                    return update
                except Exception as err:  # noqa: BLE001 - deliberately broad; we classify below
                    last_err = err
                    log.warning("node %s: attempt %s/%s failed: %s", name, attempt, retries + 1, err)
                    if attempt <= retries:
                        bus.retry(name, attempt, err)
                        time.sleep(backoff * attempt)

            bus.fail(name, last_err, fatal)
            log.error("node %s: giving up (fatal=%s)", name, fatal)
            if fatal:
                raise last_err
            return {"errors": [{"node": name, "error": str(last_err), "fatal": False}]}

        return wrapper

    return decorator
