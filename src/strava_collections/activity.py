import os
import pickle
import sys
from datetime import datetime, timedelta

import fastrdp
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import polyline
import requests
from stravalib import Client
from stravalib.model import DetailedActivity

from strava_collections.utils import (
    build_maxplotlib_elevation_plot,
    export_plotly_fig,
    export_tikz_figure,
)

# CACHE_PATH = strava_collections.__path__[0]
CACHE_PATH = os.getenv("STRAVA_CACHE_DIR", "cache")
_AUTHENTICATED_CLIENT: Client | None = None
_ROTATED_REFRESH_TOKEN: str | None = None


def _reset_auth_state_for_testing() -> None:
    global _AUTHENTICATED_CLIENT, _ROTATED_REFRESH_TOKEN
    _AUTHENTICATED_CLIENT = None
    _ROTATED_REFRESH_TOKEN = None


def _required_strava_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(
        f"Missing required environment variable {name}. "
        "Run `python update_strava_tokens.py` and export the printed credentials."
    )


def get_authenticated_client() -> Client:
    global _AUTHENTICATED_CLIENT, _ROTATED_REFRESH_TOKEN

    if _AUTHENTICATED_CLIENT is not None:
        return _AUTHENTICATED_CLIENT

    client_id = _required_strava_env("STRAVA_CLIENT_ID")
    client_secret = _required_strava_env("STRAVA_CLIENT_SECRET")
    refresh_token = _ROTATED_REFRESH_TOKEN or _required_strava_env(
        "STRAVA_REFRESH_TOKEN"
    )

    client = Client()
    token_response = client.refresh_access_token(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    client.access_token = token_response["access_token"]

    rotated_refresh_token = token_response["refresh_token"]
    _ROTATED_REFRESH_TOKEN = rotated_refresh_token
    _AUTHENTICATED_CLIENT = client

    if rotated_refresh_token != refresh_token:
        print(
            "Strava rotated the refresh token. Update STRAVA_REFRESH_TOKEN to:\n"
            f'export STRAVA_REFRESH_TOKEN="{rotated_refresh_token}"',
            file=sys.stderr,
        )

    return client


def embed_iframe(
    src: str,
    *,
    height: str = "220px",
    aspect_ratio: str = "3 / 1",
) -> str:
    return f"""
<div style="position: relative; width: 100%; height: {height}; aspect-ratio: {aspect_ratio};">
  <iframe src="{src}" style="width:100%; height:100%; border:none; border-radius: 12px;"></iframe>
</div>\n\n"""


def embed_image(
    src: str,
    *,
    alt: str,
    height: str = "220px",
    aspect_ratio: str = "3 / 1",
) -> str:
    return f"""
<img src="{src}" alt="{alt}" style="width:100%; height:{height}; aspect-ratio:{aspect_ratio}; object-fit:contain; display:block;" />\n\n"""


def get_icon_link(
    src,
    href=None,
):
    """Return an HTML <img> tag, optionally wrapped in a link."""

    if href:
        img_tag = f'<img src="{src}" class="icon">'
        return (
            f'<a href="{href}" class="icon-link" target="_blank" rel="noopener">'
            + f"{img_tag}"
            + "</a>"
        )
    else:
        return f'<img src="{src}" class="static-icon">'

    # <a href="https://www.strava.com/activities/9327605554" class="icon-link" target="_blank" rel="noopener">
    # <img src="https://cdn.worldvectorlogo.com/logos/strava-2.svg" class="icon">
    # </a>


def get_activity_photos_from_web(activity_id, access_token, size=5000):
    # https://communityhub.strava.com/t5/developer-discussions/download-all-photos-of-my-own-activities/m-p/11262
    # Construct the URL manually
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/photos?size={size}"

    # Headers including the OAuth token for authentication
    headers = {"Authorization": f"Bearer {access_token}"}

    # Making the GET request to Strava API
    response = requests.get(url, headers=headers)

    # Check if the request was successful
    if response.status_code == 200:
        photos = response.json()  # The photos data in JSON format
        return photos
    else:
        print("Error:", response.status_code, response.text)


def format_pace_min_per_km(speed_mps: float | None) -> str | None:
    """Format a speed in m/s as a running pace string like "5:12 /km"."""
    if not speed_mps:
        return None
    pace_seconds_per_km = 1000.0 / speed_mps
    minutes, seconds = divmod(round(pace_seconds_per_km), 60)
    return f"{minutes}:{seconds:02d} /km"


def is_running_activity_type(activity_type: str | None) -> bool:
    return bool(activity_type) and "run" in activity_type.lower()


# (seconds, label) pairs for the best-effort duration curves.
PROFILE_CURVE_WINDOWS: list[tuple[int, str]] = [
    (5, "5s"),
    (10, "10s"),
    (20, "20s"),
    (30, "30s"),
    (60, "60s"),
    (120, "2min"),
    (300, "5min"),
    (600, "10min"),
    (1200, "20min"),
    (1800, "30min"),
    (3600, "1h"),
]


def best_rolling_mean(values_1hz: np.ndarray, window_s: int) -> float | None:
    """Return the highest mean of `values_1hz` over any contiguous window_s-second span."""
    if values_1hz.size < window_s:
        return None
    cumulative = np.cumsum(np.insert(values_1hz, 0, 0.0))
    window_sums = cumulative[window_s:] - cumulative[:-window_s]
    return float(np.max(window_sums)) / window_s


# (lower bound seconds, upper bound seconds or None for unbounded, label) for
# the stop-duration histogram buckets.
STOP_TIME_BINS: list[tuple[float, float | None, str]] = [
    (15, 30, "15-30s"),
    (30, 60, "30s-1min"),
    (60, 300, "1-5min"),
    (300, 600, "5-10min"),
    (600, 1200, "10-20min"),
    (1200, 1800, "20-30min"),
    (1800, 3600, "30-60min"),
    (3600, None, "1h+"),
]


class StravaActivity:
    """Wrapper around stravalib's DetailedActivity with convenience methods."""

    def __init__(
        self,
        activity_id: int,
        flip: bool = False,
        force_update: bool = False,
        photos_size: int = 640,
        verbose: bool = False,
    ):
        self._activity_id = activity_id
        os.makedirs(name=CACHE_PATH, exist_ok=True)
        pickle_path = f"{CACHE_PATH}/{self.activity_id}.pkl"
        if os.path.exists(pickle_path) and force_update is False:
            print(f"{self.activity_id} (cached)", end=", ")
            with open(pickle_path, "rb") as f:
                data = pickle.load(f)
            self._activity = data["activity"]
            self._activity_stream = data["activity_stream"]
            self._photos = data["photos"]
        else:
            print(f"{self.activity_id} (downloaded)", end=", ")
            client = get_authenticated_client()

            self._activity_stream = client.get_activity_streams(activity_id=activity_id)
            self._activity = client.get_activity(activity_id=activity_id)
            self._photos = get_activity_photos_from_web(
                self.activity_id, client.access_token, size=photos_size
            )
            self.dump(filepath=pickle_path)
        self._flip = flip

    def to_gpx(self, rdp_epsilon: float | None = None) -> str:
        """Return activity as a GPX XML string."""
        latlng_stream = self.activity_stream.get("latlng")
        if not latlng_stream:
            return ""

        latlng = np.array(latlng_stream.data)
        altitude = self.activity_stream.get("altitude")
        elapsed = self.activity_stream.get("time")
        heart_rate = self.activity_stream.get("heartrate")
        cadence = self.activity_stream.get("cadence")
        power = self.activity_stream.get("watts")

        # Prepare arrays for simplification if needed
        alt_data = np.array(altitude.data) if altitude else None
        elapsed_data = np.array(elapsed.data) if elapsed else None
        hr_data = np.array(heart_rate.data) if heart_rate else None
        cad_data = np.array(cadence.data) if cadence else None
        pwr_data = np.array(power.data) if power else None

        if rdp_epsilon is not None:
            # We only simplify based on lat/lon
            indices = fastrdp.rdp_index(latlng[:, 0], latlng[:, 1], rdp_epsilon)
            latlng = latlng[indices]
            if alt_data is not None:
                alt_data = alt_data[indices]
            if elapsed_data is not None:
                elapsed_data = elapsed_data[indices]
            if hr_data is not None:
                hr_data = hr_data[indices]
            if cad_data is not None:
                cad_data = cad_data[indices]
            if pwr_data is not None:
                pwr_data = pwr_data[indices]

        start = self.activity.start_date_local or self.activity.start_date
        name = self.activity.name or f"Activity {self.activity_id}"

        trkpts = []
        for index in range(len(latlng)):
            lat, lon = latlng[index]

            inner = []
            if alt_data is not None:
                inner.append(f"<ele>{alt_data[index]:.2f}</ele>")

            if isinstance(start, datetime) and elapsed_data is not None:
                time_val = start + timedelta(seconds=float(elapsed_data[index]))
                inner.append(f"<time>{time_val.isoformat()}Z</time>")

            extensions = []
            if hr_data is not None or cad_data is not None:
                ext = ["<gpxtpx:TrackPointExtension>"]
                if hr_data is not None:
                    ext.append(f"<gpxtpx:hr>{int(hr_data[index])}</gpxtpx:hr>")
                if cad_data is not None:
                    ext.append(f"<gpxtpx:cad>{int(cad_data[index])}</gpxtpx:cad>")
                ext.append("</gpxtpx:TrackPointExtension>")
                extensions.append("\n".join(ext))

            if pwr_data is not None:
                extensions.append(f"<power>{int(pwr_data[index])}</power>")

            if extensions:
                inner.append("<extensions>")
                inner.extend(extensions)
                inner.append("</extensions>")

            inner_str = "".join(inner)
            trkpts.append(f'      <trkpt lat="{lat}" lon="{lon}">{inner_str}</trkpt>')

        trkpts_str = "\n".join(trkpts)

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="strava-collections" 
  xmlns="http://www.topografix.com/GPX/1/1"
  xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
  <trk>
    <name>{name}</name>
    <trkseg>
{trkpts_str}
    </trkseg>
  </trk>
</gpx>"""

    def add_elevation_to_fig(
        self,
        fig,
        distance_traveled=0.0,
        color="black",
        rdp_epsilon=0.1,
    ):

        distance = np.array(self.activity_stream["distance"].data) * 1e-3
        elev = np.array(self.activity_stream["altitude"].data)
        distance, elev = fastrdp.rdp(distance, elev, epsilon=rdp_epsilon)

        if self.flip:
            dmax = distance[-1]
            distance = np.array([dmax - dist for dist in distance])[::-1]
            elev = elev[::-1]
        else:
            distance = np.array(self.activity_stream["distance"].data) * 1e-3
            elev = np.array(self.activity_stream["altitude"].data)

        fig.add_trace(
            go.Scatter(
                x=distance + distance_traveled,
                y=elev,
                mode="lines",
                name=self.activity.name or f"Activity {self.activity.id}",
                line=dict(color=color),
                fill="tozeroy",
                hovertemplate="Distance: %{x:.1f} m<br>Elevation: %{y:.1f} m<extra></extra>",
            )
        )

    def plot_elevation(
        self,
        filepath=None,
        height=200,
        config=None,
        backend="plotly",
        rdp_epsilon=0.1,
        verbose: bool = False,
    ):
        """Plot the activity elevation profile with maxplotlib."""
        if config is None:
            config = {"staticPlot": True, "displayModeBar": False}

        distance = np.array(self.activity_stream["distance"].data) * 1e-3
        elev = np.array(self.activity_stream["altitude"].data)
        distance, elev = fastrdp.rdp(distance, elev, epsilon=rdp_epsilon)

        if self.flip:
            dmax = distance[-1]
            distance = np.array([dmax - dist for dist in distance])[::-1]
            elev = elev[::-1]

        fig = build_maxplotlib_elevation_plot(
            [
                {
                    "x": distance,
                    "y": elev,
                    "color": "black",
                }
            ],
            height=height,
            backend=backend,
        )

        if isinstance(filepath, str):
            if backend == "plotly":
                export_plotly_fig(
                    fig=fig,
                    filepath=filepath,
                    config=config,
                    full_html=filepath.lower().endswith(".html"),
                )
            elif backend == "tikzfigure":
                export_tikz_figure(fig=fig, filepath=filepath)
            else:
                raise ValueError(f"Unsupported elevation backend: {backend}")
            if verbose:
                print(f"Saved elevation plot to: {filepath}")
        return fig

    def get_coords(self):
        """Decode the map polyline into a list of (lat, lon) tuples."""
        strava_map = getattr(self.activity, "map", None)
        if strava_map and getattr(strava_map, "polyline", None):
            return polyline.decode(strava_map.polyline)
        return []

    def to_dataframe(self):
        """Return activity coordinates as a pandas DataFrame."""
        coords = self.get_coords()
        return pd.DataFrame(coords, columns=["lat", "lon"])

    def add_trace_to_map(self, fig: go.Figure):
        """Add this activity as a line to an existing Plotly figure."""
        df = self.to_dataframe()
        if df.empty:
            return  # skip if no polyline available

        fig.add_trace(
            go.Scatter(
                x=df["lon"],
                y=df["lat"],
                mode="lines",
                name=self.activity.name or f"Activity {self.activity.id}",
            )
        )

    def dump(self, filepath: str):
        """Serialize activity + stream to disk using pickle."""
        with open(filepath, "wb") as f:
            pickle.dump(
                {
                    "activity": self._activity,
                    "activity_stream": self._activity_stream,
                    "photos": self._photos,
                },
                f,
            )

    def generate_markdown_summary(
        self,
        include_elevation: bool = False,
        elevation_asset_extension: str = "html",
    ):
        out_str = ""
        #         out_str += """<div style="
        #     # background-color: #dbf9e1;
        #     background-color: #ffffff;
        #     border-radius: 10px;
        #     padding: 15px;
        #     border: 1px solid #ccc;
        #     max-width: 100%;
        # ">\n"""

        # Heading
        # out_str += f"## {self.name}\n\n"
        out_str += '<div class="description-box">\n'
        out_str += (
            '<h2 class="description-title">'
            f'<a href="/activities/{self.activity_id}/">{self.name}</a>'
            "</h2>\n"
        )

        out_str += "<div>\n"

        # Date
        out_str += f"{self.activity.start_date_local.date()} "
        # Icon row
        out_str += get_icon_link(
            "https://media.istockphoto.com/id/1442152045/vector/path-route-icon-distance-symbol.jpg?s=612x612&w=0&k=20&c=2ilIa1pWHJp550B31t__1NPc0CHpouutgdxt7QO4EJg="
        )
        out_str += f"{round(self.activity.distance * 1e-3)} km "
        out_str += get_icon_link(
            "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcS_EkMEkMAdgDcE0W6nELzmmMrqHToRcoS8eA&s"
        )
        out_str += f"{round(self.activity.total_elevation_gain)} m "
        out_str += get_icon_link(
            "https://cdn-icons-png.freepik.com/512/13063/13063145.png"
        )
        out_str += f"<span>{timedelta(seconds=self.activity.moving_time)}</span>\n "
        out_str += "       "
        out_str += get_icon_link(
            "https://cdn.worldvectorlogo.com/logos/strava-2.svg",
            href=self.link,
        )
        out_str += "</div>\n\n<br>\n\n"
        description = self.activity.description
        if len(description) > 0:
            out_str += '<div class="description-text">'
            out_str += description
            out_str += "</div>\n"

        # Activity-specific map
        if not self.no_map:
            out_str += f'<div class="activity-map-canvas" id="map-{self.activity_id}" data-activity-id="{self.activity_id}"></div>\n'

        # Activity-specific elevation
        if not self.no_map:
            out_str += f'<div class="activity-elevation-canvas" id="elev-{self.activity_id}" data-activity-id="{self.activity_id}"></div>\n'

        # Photos
        # TODO: Get photos from the DetailedActivity (currently seems broken?)
        # print(self.activity.full_photos)
        # for photo in self.activity.full_photos:
        #     print(photo.urls)
        #     # out_str += f"![{photo.urls['1800']}]({photo.urls['1800']})\n"
        #     # out_str += f'<img src="{photo.urls['1800']}" width="50" height="50">'
        if self.photos:
            if len(self.photos) > 0:
                out_str += '<div class="gallery">'
                for index, photo in enumerate(self.photos, start=1):
                    size = list(photo["urls"].keys())[0]
                    url = photo["urls"][str(size)]
                    out_str += (
                        f'<img src="{url}" height="200" class="lightbox-trigger" '
                        f'loading="lazy" decoding="async" '
                        f'alt="{self.activity.name} photo {index}">'
                    )
                out_str += "</div>"
        # out_str += "</div>"
        out_str += "</div>\n\n\n"
        return out_str

    def generate_activity_page_metadata(self) -> dict:
        """Return stats and identifiers used to render this activity's own page."""
        activity = self.activity
        moving_time = (
            str(timedelta(seconds=activity.moving_time))
            if activity.moving_time
            else None
        )
        elapsed_time = (
            str(timedelta(seconds=activity.elapsed_time))
            if activity.elapsed_time
            else None
        )
        activity_type = (
            getattr(activity.type, "root", None) or str(activity.type)
            if activity.type
            else None
        )
        is_running = is_running_activity_type(activity_type)

        avg_speed_kmh = None
        max_speed_kmh = None
        avg_pace = None
        max_pace = None
        if is_running:
            avg_pace = format_pace_min_per_km(activity.average_speed)
            max_pace = format_pace_min_per_km(activity.max_speed)
        else:
            avg_speed_kmh = (
                round(float(activity.average_speed) * 3.6, 1)
                if activity.average_speed
                else None
            )
            max_speed_kmh = (
                round(float(activity.max_speed) * 3.6, 1)
                if activity.max_speed
                else None
            )
        start_date = activity.start_date_local or activity.start_date

        return {
            "activityId": self.activity_id,
            "flip": self.flip,
            "title": activity.name or f"Activity {self.activity_id}",
            "date": str(start_date.date()) if start_date else None,
            "activityType": activity_type,
            "stravaLink": self.link,
            "distanceKm": (
                round(float(activity.distance) * 1e-3, 1) if activity.distance else None
            ),
            "elevationGainM": (
                round(float(activity.total_elevation_gain))
                if activity.total_elevation_gain
                else None
            ),
            "movingTime": moving_time,
            "elapsedTime": elapsed_time,
            "avgSpeedKmh": avg_speed_kmh,
            "maxSpeedKmh": max_speed_kmh,
            "avgPace": avg_pace,
            "maxPace": max_pace,
            "avgHeartRate": (
                round(float(activity.average_heartrate))
                if getattr(activity, "average_heartrate", None)
                else None
            ),
            "maxHeartRate": (
                round(float(activity.max_heartrate))
                if getattr(activity, "max_heartrate", None)
                else None
            ),
            "avgWatts": (
                round(float(activity.average_watts))
                if getattr(activity, "average_watts", None)
                else None
            ),
            "calories": (
                round(float(activity.calories))
                if getattr(activity, "calories", None)
                else None
            ),
            "profileCurves": self.compute_profile_curves(),
            "timeSeries": self.compute_time_series(),
            "stopTimeHistogram": self.compute_stop_time_histogram(),
        }

    def generate_activity_page_body_html(self) -> str:
        """Return the description + photo gallery markup for this activity's own page."""
        out_str = ""
        description = self.activity.description
        if description:
            out_str += f'<div class="description-text">{description}</div>\n'

        if self.photos:
            out_str += '<div class="gallery">'
            for index, photo in enumerate(self.photos, start=1):
                size = list(photo["urls"].keys())[0]
                url = photo["urls"][str(size)]
                out_str += (
                    f'<img src="{url}" height="200" class="lightbox-trigger" '
                    f'loading="lazy" decoding="async" '
                    f'alt="{self.activity.name} photo {index}">'
                )
            out_str += "</div>\n"

        return out_str

    def compute_profile_curves(self) -> dict:
        """Best-effort duration curves (log-log "power curve" style profiles).

        For each window in PROFILE_CURVE_WINDOWS, finds the highest average
        power (W), speed (km/h), and elevation gain rate (m/h) sustained over
        any contiguous span of that duration within the activity.
        """
        curves = {
            "windowsSeconds": [],
            "windowLabels": [],
            "power": [],
            "speedKmh": [],
            "elevationGainMH": [],
        }

        time_stream = self.activity_stream.get("time")
        if not time_stream or len(time_stream.data) < 2:
            return curves

        t_raw = np.array(time_stream.data, dtype=float)
        duration_s = int(t_raw[-1])
        if duration_s < PROFILE_CURVE_WINDOWS[0][0]:
            return curves

        t_1hz = np.arange(0, duration_s + 1, dtype=float)

        watts_stream = self.activity_stream.get("watts")
        watts_1hz = (
            np.interp(t_1hz, t_raw, np.array(watts_stream.data, dtype=float))
            if watts_stream
            else None
        )

        speed_1hz = None
        if self.activity_stream.get("velocity_smooth"):
            speed_1hz = np.interp(
                t_1hz,
                t_raw,
                np.array(self.activity_stream["velocity_smooth"].data, dtype=float),
            )
        elif self.activity_stream.get("distance"):
            distance_1hz = np.interp(
                t_1hz,
                t_raw,
                np.array(self.activity_stream["distance"].data, dtype=float),
            )
            speed_1hz = np.gradient(distance_1hz, t_1hz)

        altitude_stream = self.activity_stream.get("altitude")
        gain_1hz = None
        if altitude_stream:
            altitude_1hz = np.interp(
                t_1hz, t_raw, np.array(altitude_stream.data, dtype=float)
            )
            gain_1hz = np.clip(np.diff(altitude_1hz, prepend=altitude_1hz[0]), 0, None)

        for window_s, label in PROFILE_CURVE_WINDOWS:
            if window_s > duration_s:
                break

            power_value = (
                best_rolling_mean(watts_1hz, window_s)
                if watts_1hz is not None
                else None
            )
            speed_value = (
                best_rolling_mean(speed_1hz, window_s)
                if speed_1hz is not None
                else None
            )
            gain_value = (
                best_rolling_mean(gain_1hz, window_s) if gain_1hz is not None else None
            )

            curves["windowsSeconds"].append(window_s)
            curves["windowLabels"].append(label)
            curves["power"].append(
                round(power_value) if power_value is not None else None
            )
            curves["speedKmh"].append(
                round(speed_value * 3.6, 2) if speed_value is not None else None
            )
            curves["elevationGainMH"].append(
                round(gain_value * 3600) if gain_value is not None else None
            )

        if watts_1hz is None or all(v is None for v in curves["power"]):
            curves["power"] = []
        if speed_1hz is None or all(v is None for v in curves["speedKmh"]):
            curves["speedKmh"] = []
        if gain_1hz is None or all(v is None for v in curves["elevationGainMH"]):
            curves["elevationGainMH"] = []

        return curves

    def compute_time_series(self, max_points: int = 1500) -> dict:
        """Downsampled time-series traces for every relevant stream.

        Returns a dict with a shared `timeS`/`distanceKm` x-axis (in the
        activity's original sample order) plus one entry per available
        metric under `series`, each an object with `label`, `unit`, and
        `values` aligned to the shared x-axis.
        """
        result: dict = {"timeS": [], "distanceKm": [], "series": {}}

        time_stream = self.activity_stream.get("time")
        if not time_stream or len(time_stream.data) < 2:
            return result

        t = np.array(time_stream.data, dtype=float)
        n = t.size

        distance_stream = self.activity_stream.get("distance")
        distance_km = (
            np.array(distance_stream.data, dtype=float) / 1000.0
            if distance_stream
            else None
        )

        metric_specs: list[tuple[str, str, str, np.ndarray]] = []

        altitude_stream = self.activity_stream.get("altitude")
        if altitude_stream:
            metric_specs.append(
                (
                    "elevation",
                    "Elevation",
                    "m",
                    np.array(altitude_stream.data, dtype=float),
                )
            )

        velocity_stream = self.activity_stream.get("velocity_smooth")
        if velocity_stream:
            speed_kmh = np.array(velocity_stream.data, dtype=float) * 3.6
            metric_specs.append(("speed", "Speed", "km/h", speed_kmh))
        elif distance_stream is not None and n > 1:
            speed_kmh = np.gradient(distance_km * 1000.0, t) * 3.6
            metric_specs.append(("speed", "Speed", "km/h", speed_kmh))

        heartrate_stream = self.activity_stream.get("heartrate")
        if heartrate_stream:
            metric_specs.append(
                (
                    "heartrate",
                    "Heart Rate",
                    "bpm",
                    np.array(heartrate_stream.data, dtype=float),
                )
            )

        cadence_stream = self.activity_stream.get("cadence")
        if cadence_stream:
            metric_specs.append(
                (
                    "cadence",
                    "Cadence",
                    "rpm",
                    np.array(cadence_stream.data, dtype=float),
                )
            )

        watts_stream = self.activity_stream.get("watts")
        if watts_stream:
            metric_specs.append(
                ("power", "Power", "W", np.array(watts_stream.data, dtype=float))
            )

        grade_stream = self.activity_stream.get("grade_smooth")
        if grade_stream:
            metric_specs.append(
                ("grade", "Grade", "%", np.array(grade_stream.data, dtype=float))
            )

        temp_stream = self.activity_stream.get("temp")
        if temp_stream:
            metric_specs.append(
                (
                    "temperature",
                    "Temperature",
                    "°C",
                    np.array(temp_stream.data, dtype=float),
                )
            )

        if not metric_specs:
            return result

        if n > max_points:
            indices = np.unique(np.linspace(0, n - 1, max_points).round().astype(int))
        else:
            indices = np.arange(n)

        result["timeS"] = [round(v) for v in t[indices].tolist()]
        if distance_km is not None:
            result["distanceKm"] = [round(v, 3) for v in distance_km[indices].tolist()]

        for key, label, unit, values in metric_specs:
            sampled = values[indices]
            result["series"][key] = {
                "label": label,
                "unit": unit,
                "values": [
                    round(float(v), 2) if np.isfinite(v) else None for v in sampled
                ],
            }

        return result

    def compute_stop_time_histogram(self) -> dict:
        """Bucket contiguous non-moving spans by duration, per STOP_TIME_BINS.

        Uses the `moving` stream to find every contiguous stretch where the
        athlete wasn't moving, then buckets each stop's duration into the
        length ranges in STOP_TIME_BINS, tracking both the accumulated time
        and the number of stops per bucket.
        """
        result = {
            "labels": [label for _, _, label in STOP_TIME_BINS],
            "totalMinutes": [0.0] * len(STOP_TIME_BINS),
            "counts": [0] * len(STOP_TIME_BINS),
            "totalStoppedMinutes": 0.0,
            "totalStopsCount": 0,
        }

        moving_stream = self.activity_stream.get("moving")
        time_stream = self.activity_stream.get("time")
        if not moving_stream or not time_stream:
            return result

        n = min(len(moving_stream.data), len(time_stream.data))
        if n < 2:
            return result

        moving = np.array(moving_stream.data[:n], dtype=bool)
        t = np.array(time_stream.data[:n], dtype=float)

        min_stop_seconds = STOP_TIME_BINS[0][0]
        durations = []
        i = 0
        while i < n:
            if not moving[i]:
                start = i
                while i < n and not moving[i]:
                    i += 1
                end_index = i if i < n else n - 1
                duration = t[end_index] - t[start]
                if duration >= min_stop_seconds:
                    durations.append(duration)
            else:
                i += 1

        for duration in durations:
            for bin_index, (lower, upper, _) in enumerate(STOP_TIME_BINS):
                if duration >= lower and (upper is None or duration < upper):
                    result["totalMinutes"][bin_index] += duration / 60.0
                    result["counts"][bin_index] += 1
                    break

        result["totalMinutes"] = [round(v, 1) for v in result["totalMinutes"]]
        result["totalStoppedMinutes"] = round(sum(durations) / 60.0, 1)
        result["totalStopsCount"] = len(durations)
        return result

    @property
    def activity_id(self):
        return self._activity_id

    @property
    def activity(self) -> DetailedActivity:
        return self._activity

    @property
    def activity_stream(self):
        return self._activity_stream

    @property
    def flip(self):
        return self._flip

    @property
    def link(self):
        return f"https://www.strava.com/activities/{self.activity_id}"

    @property
    def no_map(self):
        return len(self.get_coords()) == 0

    @property
    def photos(self):
        return self._photos

    def __getattr__(self, name):
        """Delegate attribute access to the underlying DetailedActivity."""
        return getattr(self.activity, name)
