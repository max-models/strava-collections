import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from strava_collections.site_sync import sync_site
from strava_collections.site_template import build_site_paths

SITE_ROOT = Path(__file__).resolve().parents[2]
PATHS = build_site_paths(SITE_ROOT)
POLL_INTERVAL_SECONDS = 1.0


def snapshot_source_tree() -> dict[str, tuple[int, int]]:
    state: dict[str, tuple[int, int]] = {}
    for path in sorted(PATHS.source_dir.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        state[str(path.relative_to(PATHS.source_dir))] = (
            stat.st_mtime_ns,
            stat.st_size,
        )
    return state


def run_sync() -> None:
    sync_site(SITE_ROOT)


def clear_vite_dependency_cache() -> None:
    vite_cache_dir = PATHS.astro_dir / "node_modules" / ".vite"
    if vite_cache_dir.exists():
        shutil.rmtree(vite_cache_dir)


def main() -> int:
    run_sync()
    clear_vite_dependency_cache()
    previous_snapshot = snapshot_source_tree()

    astro_command = ["npm", "run", "astro:dev"]
    if len(sys.argv) > 1:
        astro_command.extend(["--", *sys.argv[1:]])

    astro_process = subprocess.Popen(
        astro_command,
        cwd=PATHS.astro_dir,
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
