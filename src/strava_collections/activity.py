import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import polyline
from stravalib.model import DetailedActivity


class StravaActivity:
    """Wrapper around stravalib's DetailedActivity with convenience methods."""

    def __init__(self, activity: DetailedActivity):
        self.activity = activity

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

    def __getattr__(self, name):
        """Delegate attribute access to the underlying DetailedActivity."""
        return getattr(self.activity, name)
