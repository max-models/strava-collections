import signal
import subprocess
import sys
import time
from pathlib import Path

import sync_generated_content

ASTRO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ASTRO_ROOT.parent / "source"
POLL_INTERVAL_SECONDS = 1.0


def snapshot_source_tree() -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    for path in sorted(SOURCE_ROOT.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        state[str(path.relative_to(SOURCE_ROOT))] = (stat.st_mtime_ns, stat.st_size)
    return state


def run_sync() -> None:
    sync_generated_content.main()


def main() -> int:
    run_sync()
    previous_snapshot = snapshot_source_tree()

    astro_process = subprocess.Popen(
        ["npm", "run", "astro:dev"],
        cwd=ASTRO_ROOT,
    )

    def stop_astro(signum=None, frame=None):
        if astro_process.poll() is None:
            astro_process.terminate()
            try:
                astro_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                astro_process.kill()

    signal.signal(signal.SIGINT, stop_astro)
    signal.signal(signal.SIGTERM, stop_astro)

    try:
        while astro_process.poll() is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            current_snapshot = snapshot_source_tree()
            if current_snapshot != previous_snapshot:
                run_sync()
                previous_snapshot = current_snapshot
    finally:
        stop_astro()

    return astro_process.returncode or 0


if __name__ == "__main__":
    sys.exit(main())
