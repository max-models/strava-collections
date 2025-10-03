import numpy as np
import plotly.graph_objects as go
from stravalib import Client

from strava_collections.activity import StravaActivity


class StravaCollection:
    def __init__(self, client: Client, activity_ids: list[int]) -> None:
        self._client = client
        self._activity_ids = activity_ids
        self._activities = [
            StravaActivity(client.get_activity(activity_id))
            for activity_id in activity_ids
        ]

    def plot_map(self, zoom=12, height=600):
        """Plot all activities together as lon/lat lines."""
        fig = go.Figure()

        maxlon, minlon = -9999, 9999
        maxlat, minlat = -9999, 9999

        for activity in self.activities:
            df = activity.to_dataframe()

            lons, lats = df["lon"], df["lat"]

            maxlon = max(maxlon, max(lons))
            minlon = min(minlon, min(lons))
            maxlat = max(maxlat, max(lats))
            minlat = min(minlat, min(lats))

            if df.empty:
                continue
            fig.add_trace(
                go.Scattermapbox(
                    lat=df["lat"],
                    lon=df["lon"],
                    mode="lines",
                    name=activity.activity.name or f"Activity {activity.activity.id}",
                )
            )

        zoom, center = zoom_center(maxlon, minlon, maxlat, minlat, width_to_height=5.0)
        fig.update_layout(
            mapbox_style="open-street-map",
            mapbox_zoom=zoom,
            mapbox_center=center,
            height=height,
            title="Strava Activities (Map View)",
        )
        return fig

    @property
    def activities(self):
        return self._activities

    @property
    def client(self):
        return self._client

    @property
    def activity_ids(self):
        return self._activity_ids


def zoom_center(
    maxlon,
    minlon,
    maxlat,
    minlat,
    lons: tuple = None,
    lats: tuple = None,
    lonlats: tuple = None,
    format: str = "lonlat",
    projection: str = "mercator",
    width_to_height: float = 2.0,
) -> (float, dict):
    """Finds optimal zoom and centering for a plotly mapbox.
    Must be passed (lons & lats) or lonlats.
    Temporary solution awaiting official implementation, see:
    https://github.com/plotly/plotly.js/issues/3434

    Parameters
    --------
    lons: tuple, optional, longitude component of each location
    lats: tuple, optional, latitude component of each location
    lonlats: tuple, optional, gps locations
    format: str, specifying the order of longitud and latitude dimensions,
        expected values: 'lonlat' or 'latlon', only used if passed lonlats
    projection: str, only accepting 'mercator' at the moment,
        raises `NotImplementedError` if other is passed
    width_to_height: float, expected ratio of final graph's with to height,
        used to select the constrained axis.

    Returns
    --------
    zoom: float, from 1 to 20
    center: dict, gps position with 'lon' and 'lat' keys

    >>> print(zoom_center((-109.031387, -103.385460),
    ...     (25.587101, 31.784620)))
    (5.75, {'lon': -106.208423, 'lat': 28.685861})
    """
    # if lons is None and lats is None:
    #     if isinstance(lonlats, tuple):
    #         lons, lats = zip(*lonlats)
    #     else:
    #         raise ValueError("Must pass lons & lats or lonlats")

    # maxlon, minlon = max(lons), min(lons)
    # maxlat, minlat = max(lats), min(lats)
    center = {
        "lon": round((maxlon + minlon) / 2, 6),
        "lat": round((maxlat + minlat) / 2, 6),
    }

    # longitudinal range by zoom level (20 to 1)
    # in degrees, if centered at equator
    lon_zoom_range = np.array(
        [
            0.0007,
            0.0014,
            0.003,
            0.006,
            0.012,
            0.024,
            0.048,
            0.096,
            0.192,
            0.3712,
            0.768,
            1.536,
            3.072,
            6.144,
            11.8784,
            23.7568,
            47.5136,
            98.304,
            190.0544,
            360.0,
        ]
    )

    if projection == "mercator":
        margin = 1.2
        height = (maxlat - minlat) * margin * width_to_height
        width = (maxlon - minlon) * margin
        lon_zoom = np.interp(width, lon_zoom_range, range(20, 0, -1))
        lat_zoom = np.interp(height, lon_zoom_range, range(20, 0, -1))
        zoom = round(min(lon_zoom, lat_zoom), 2)
    else:
        raise NotImplementedError(f"{projection} projection is not implemented")

    return zoom, center
