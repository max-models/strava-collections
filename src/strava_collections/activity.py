import os
import pickle
from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import polyline
import requests
from stravalib import Client
from stravalib.model import DetailedActivity

from strava_collections.utils import export_plotly_fig

# CACHE_PATH = strava_collections.__path__[0]
CACHE_PATH = "cache"


class StravaActivity:
    """Wrapper around stravalib's DetailedActivity with convenience methods."""

    def __init__(
        self,
        activity_id: int,
        flip: bool = False,
        force_update: bool = False,
        photos_size: int = 640,
    ):
        self._activity_id = activity_id
        os.makedirs(name=CACHE_PATH, exist_ok=True)
        pickle_path = f"{CACHE_PATH}/{self.activity_id}.pkl"
        if os.path.exists(pickle_path) and force_update is False:
            print(f"Loading cached activity {self.activity_id}")
            with open(pickle_path, "rb") as f:
                data = pickle.load(f)
            self._activity = data["activity"]
            self._activity_stream = data["activity_stream"]
            self._photos = data["photos"]
        else:
            print(f"Downloading activity {self.activity_id}")

            # Load Strava credentials from environment
            client_id = os.getenv("STRAVA_CLIENT_ID")
            client_secret = os.getenv("STRAVA_CLIENT_SECRET")
            refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")

            client = Client()

            # Refresh access token
            token_response = client.refresh_access_token(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )
            client.access_token = token_response["access_token"]

            self._activity_stream = client.get_activity_streams(activity_id=activity_id)
            self._activity = client.get_activity(activity_id=activity_id)
            self._photos = get_activity_photos_from_web(
                self.activity_id, client.access_token, size=photos_size
            )
            self.dump(filepath=pickle_path)
        self._flip = flip

    def add_elevation_to_fig(self, fig, distance_traveled=0.0, color="black"):
        if self.flip:
            dmax = self.activity_stream["distance"].data[-1]
            distance = (
                np.array(
                    [dmax - dist for dist in self.activity_stream["distance"].data]
                )[::-1]
                * 1e-3
            )
            elev = np.array(self.activity_stream["altitude"].data)[::-1]
        else:
            distance = np.array(self.activity_stream["distance"].data) * 1e-3
            elev = np.array(self.activity_stream["altitude"].data)

            # pick a line color from palette
            # line_color = palette[color_index % len(palette)]
            # convert to rgba with alpha=0.3
            # rgba_color = pc.hex_to_rgb(line_color)
            # fillcolor = f"rgba({rgba_color[0]},{rgba_color[1]},{rgba_color[2]},0.3)"

            fig.add_trace(
                go.Scatter(
                    x=distance + distance_traveled,
                    y=elev,
                    mode="lines",
                    name=self.activity.name or f"Activity {self.activity.id}",
                    line=dict(color=color),
                    fill="tozeroy",
                    # fillcolor=fillcolor,
                    hovertemplate="Distance: %{x:.1f} m<br>Elevation: %{y:.1f} m<extra></extra>",
                )
            )

    def plot_elevation(
        self,
        filepath=None,
        height=200,
        config={"staticPlot": True, "displayModeBar": False},
    ):
        """Plot elevation profile of all activities with filled translucent area."""
        fig = go.Figure()
        self.add_elevation_to_fig(fig, distance_traveled=0.0, color="black")

        fig.update_layout(
            # title="Elevation Profiles",
            xaxis_title="Distance (km)",
            yaxis_title="Elevation (m)",
            height=height,
            hovermode="x unified",
            showlegend=False,
            xaxis=dict(tickformat=",.0f"),
            margin=dict(l=0, r=0, t=0, b=0),
            autosize=True,
            plot_bgcolor="white",
            paper_bgcolor="white",
        )

        if isinstance(filepath, str):
            export_plotly_fig(fig=fig, filepath=filepath, config=config)
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

    def generate_markdown_summary(self):
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
        out_str += f'<div class="description-title">{self.name}</div>\n'

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

        out_str += f"""
<div style="position: relative; width: 100%; padding-bottom: 250px; height: 0;">
<iframe src="_static/{self.activity_id}.html" style="position:absolute; top:0; left:0; width:100%; height:100%; border:none;"></iframe>
</div>\n\n"""

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
                for photo in self.photos:
                    size = list(photo["urls"].keys())[0]
                    url = photo["urls"][str(size)]
                    out_str += (
                        f'<img src="{url}" height="200" class="lightbox-trigger">'
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
    def photos(self):
        return self._photos

    def __getattr__(self, name):
        """Delegate attribute access to the underlying DetailedActivity."""
        return getattr(self.activity, name)


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
