"""
Octron Launcher
Starts the FastAPI core (octron_api.py) and the Streamlit mobile UI
(octron_mobile_ui.py) together, in one terminal, and shuts both down
cleanly on Ctrl+C.

Run this FROM THE PROJECT FOLDER (same place as octron_api.py):

    python launch_octron.py

What it does:
- Launches octron_api.py with the current Python interpreter (sys.executable),
  so it uses whatever venv/environment you're already running this from.
- Waits for the API's health check to respond before starting the UI, so the
  UI doesn't show "DISCONNECTED" just because it started half a second early.
- Launches `streamlit run octron_mobile_ui.py` and opens your browser to it.
- Streams both processes' output into this one terminal, prefixed so you can
  tell them apart ([API] / [UI]).
- On Ctrl+C (or if one process dies), stops the other and exits cleanly.

What it does NOT do:
- Doesn't check Ollama is running or that models are pulled — if the API
  process itself fails on startup, its [API] output will show that traceback
  right here.
- Doesn't manage ports beyond the defaults (API: 8000, UI: 8501). If those
  are already taken, you'll see the underlying error in the relevant stream.
"""

import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
API_SCRIPT = PROJECT_DIR / "octron_api.py"
UI_SCRIPT = PROJECT_DIR / "octron_mobile_ui.py"

API_HEALTH_URL = "http://localhost:8000/docs"  # FastAPI auto-serves this; cheap liveness check
API_STARTUP_TIMEOUT = 30  # seconds to wait for the API before starting the UI anyway

processes = []
stop_event = threading.Event()


def stream_output(proc: subprocess.Popen, label: str):
    """Pipe a subprocess's stdout/stderr into this terminal with a [LABEL] prefix."""
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            print(f"[{label}] {line.rstrip()}")
    except Exception:
        pass


def wait_for_api(timeout: int) -> bool:
    """Poll the API until it responds or we give up."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if stop_event.is_set():
            return False
        try:
            urllib.request.urlopen(API_HEALTH_URL, timeout=1)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


def launch(cmd: list, label: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        cmd,
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    processes.append(proc)
    t = threading.Thread(target=stream_output, args=(proc, label), daemon=True)
    t.start()
    return proc


def shutdown():
    print("\n[LAUNCHER] Shutting down...")
    for proc in processes:
        if proc.poll() is None:
            proc.terminate()
    # give them a moment to exit gracefully before forcing it
    deadline = time.time() + 5
    for proc in processes:
        remaining = max(0, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("[LAUNCHER] All processes stopped.")


def main():
    if not API_SCRIPT.exists():
        print(f"[LAUNCHER] ERROR: {API_SCRIPT.name} not found in {PROJECT_DIR}")
        sys.exit(1)
    if not UI_SCRIPT.exists():
        print(f"[LAUNCHER] ERROR: {UI_SCRIPT.name} not found in {PROJECT_DIR}")
        sys.exit(1)

    print("=" * 50)
    print("  OCTRON LAUNCHER")
    print("=" * 50)

    print("[LAUNCHER] Starting API core...")
    launch([sys.executable, str(API_SCRIPT)], "API")

    print("[LAUNCHER] Waiting for API to come online...")
    if wait_for_api(API_STARTUP_TIMEOUT):
        print("[LAUNCHER] API is up.")
    else:
        print(
            "[LAUNCHER] WARNING: API didn't respond within "
            f"{API_STARTUP_TIMEOUT}s — starting the UI anyway. "
            "Check the [API] lines above for a crash/traceback."
        )

    print("[LAUNCHER] Starting UI...")
    launch(
        [sys.executable, "-m", "streamlit", "run", str(UI_SCRIPT), "--server.headless=false"],
        "UI",
    )

    print("[LAUNCHER] Both processes launched. Press Ctrl+C to stop everything.\n")

    try:
        while not stop_event.is_set():
            # if either process dies on its own, shut the other down too
            for proc in processes:
                if proc.poll() is not None:
                    print(f"[LAUNCHER] A process exited unexpectedly (code {proc.returncode}).")
                    stop_event.set()
                    break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()
