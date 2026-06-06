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


def build_strava_route_data(activity_id: int) -> dict[str, Any]:
    try:
        with redirect_stdout(StringIO()):
            activity = StravaActivity(activity_id=activity_id)
    except Exception:
        return {"status": "error"}

    latlng = _stream_values(activity, "latlng")
    if not latlng:
        return {"status": "empty"}

    altitude = _stream_values(activity, "altitude")
    distance = _stream_values(activity, "distance")
    elapsed = _stream_values(activity, "time")
    speed = _stream_values(activity, "velocity_smooth")
    heart_rate = _stream_values(activity, "heartrate")
    cadence = _stream_values(activity, "cadence")
    power = _stream_values(activity, "watts")

    start = activity.activity.start_date_local or activity.activity.start_date
    points: list[dict[str, Any]] = []

    for index, point in enumerate(latlng):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        lat, lon = point
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue

        duration_secs = _stream_value_at(elapsed, index)
        time_iso = None
        if isinstance(start, datetime) and isinstance(duration_secs, (int, float)):
            time_iso = (start + timedelta(seconds=float(duration_secs))).isoformat()

        points.append(
            {
                "lat": lat,
                "lon": lon,
                "time": time_iso,
                "distanceMeters": _stream_value_at(distance, index),
                "durationSecs": duration_secs,
                "elevation": _stream_value_at(altitude, index),
                "speedMetersPerSec": _stream_value_at(speed, index),
                "heartRateBeatsPerMin": _stream_value_at(heart_rate, index),
                "cadenceCyclesPerMin": _stream_value_at(cadence, index),
                "powerWatts": _stream_value_at(power, index),
            }
        )

    if not points:
        return {"status": "empty"}

    last = points[-1]
    return {
        "status": "ok",
        "points": points,
        "summary": {
            "pointCount": len(points),
            "totalDistanceMeters": last.get("distanceMeters"),
            "totalDurationSecs": last.get("durationSecs"),
            "lastReportedTime": last.get("time"),
            "isActive": False,
        },
    }


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
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
