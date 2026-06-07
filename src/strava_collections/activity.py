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

    def add_elevation_to_fig(self, fig, distance_traveled=0.0, color="black", rdp_epsilon=0.1,):

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
        if self.activity.map and self.activity.map.polyline:
            return polyline.decode(self.activity.map.polyline)
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
        out_str += f'<h2 class="description-title">{self.name}</h2>\n'

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
        out_str += f"<span>{timedelta(seconds=self.activity.elapsed_time)}</span>\n "
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

        # Elevation profile
        if include_elevation:
            elevation_asset_extension = elevation_asset_extension.lstrip(".")
            elevation_src = (
                f"/_static/activity-{self.activity_id}.{elevation_asset_extension}"
            )
            if elevation_asset_extension == "html":
                out_str += embed_iframe(
                    src=elevation_src,
                )
            else:
                out_str += embed_image(
                    src=elevation_src,
                    alt=f"{self.activity.name} elevation profile",
                )

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
