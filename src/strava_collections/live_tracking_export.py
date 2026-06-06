import json
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from typing import Any

from strava_collections.activity import StravaActivity


def _stream_values(activity: StravaActivity, key: str) -> list[Any] | None:
    stream = activity.activity_stream.get(key)
    if stream is None:
        return None
    return list(stream.data)


def _stream_value_at(values: list[Any] | None, index: int) -> Any | None:
    if values is None or index >= len(values):
        return None
    return values[index]


def build_strava_route_data(activity_id: int) -> str | dict[str, Any]:
    try:
        with redirect_stdout(StringIO()):
            activity = StravaActivity(activity_id=activity_id)
        gpx = activity.to_gpx()
        if not gpx:
            return {"status": "empty"}
        return gpx
    except Exception:
        return {"status": "error"}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Export Strava activity routes for live tracking."
    )
    parser.add_argument(
        "activity_ids", nargs="+", help="One or more Strava activity IDs"
    )
    args = parser.parse_args()

    payload = {
        activity_id: build_strava_route_data(int(activity_id))
        for activity_id in args.activity_ids
    }
    print(json.dumps(payload, separators=(",", ":")))


if __name__ == "__main__":
    main()
