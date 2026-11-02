import sys
sys.path.append("REDACTED — production application root")

import os
import time

from engine.parts.core.logger import log_detail, log_error


def ensure_file(path: str, description: str, timeout: int = 300, interval: float = 1.0):
    """
    Wait for a required file to exist.
    This allows watcher/merger to finish producing the final video
    before uploader runs.
    """
    start = time.time()
    log_detail(f"Waiting for {description}.", component="wiring")

    while time.time() - start < timeout:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            log_detail(f"{description} ready.", component="wiring")
            return path
        time.sleep(interval)

    msg = f"{description} not found after waiting {timeout} seconds."
    log_error(msg, component="wiring")
    raise FileNotFoundError(msg)


def join(*paths):
    """
    Simple, safe join wrapper for consistency.
    """
    return os.path.join(*paths)


# IMPORTANT: leave a blank line at the end of file so Python parses correctly.
