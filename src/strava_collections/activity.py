import os
import pickle

import pandas as pd
import plotly.graph_objects as go
import polyline
from stravalib import Client

import strava_collections

LIBPATH = strava_collections.__path__[0]


class StravaActivity:
    """Wrapper around stravalib's DetailedActivity with convenience methods."""

    def __init__(self, client: Client, activity_id: int, flip: bool = False):
        self._activity_id = activity_id

        pickle_path = f"{LIBPATH}/{self.activity_id}.pkl"
        if os.path.exists(pickle_path):
            # Load
            with open(pickle_path, "rb") as f:
                data = pickle.load(f)
            self._activity = data["activity"]
            self._activity_stream = data["activity_stream"]
        else:
            self._activity_stream = client.get_activity_streams(activity_id=activity_id)
            self._activity = client.get_activity(activity_id=activity_id)
            self.dump(filepath=pickle_path)
        self._flip = flip

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
                },
                f,
            )

    @property
    def activity_id(self):
        return self._activity_id

    @property
    def activity(self):
        return self._activity

    @property
    def activity_stream(self):
        return self._activity_stream

    @property
    def flip(self):
        return self._flip

    def __getattr__(self, name):
        """Delegate attribute access to the underlying DetailedActivity."""
        return getattr(self.activity, name)
