from pathlib import Path

from strava_collections.site_sync import sync_site


def main() -> None:
    site_root = Path(__file__).resolve().parents[2]
    sync_site(site_root)


if __name__ == "__main__":
    main()
