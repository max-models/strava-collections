import os
import subprocess
import tempfile
from html import escape
from pathlib import Path
from typing import List

import fastrdp
import numpy as np
import pandas as pd
import plotly.colors as pc
import plotly.graph_objects as go

from strava_collections.activity import StravaActivity, embed_iframe, embed_image
from strava_collections.astro_page import (
    prepare_collection_markup,
    render_collection_page,
)
from strava_collections.utils import (
    build_maxplotlib_elevation_plot,
    export_plotly_fig,
    export_tikz_figure,
)

palette = pc.qualitative.Plotly  # default Plotly categorical colors
tikz_palette = [
    "RoyalBlue",
    "Orange",
    "ForestGreen",
    "BrickRed",
    "DarkOrchid",
    "Goldenrod",
    "CadetBlue",
    "Magenta",
    "SaddleBrown",
    "Gray",
]
# Plotly's MapLibre-backed `map` subplot no longer needs a Mapbox access token.
mapbox_token = os.getenv("MAPBOX_TOKEN")
mapbox_token_help = (
    "MAPBOX_TOKEN is no longer required for the default interactive map styles."
)
PLACE_MARKER_SIZE = 5
PLACE_NEARBY_TRACK_THRESHOLD_KM = 20.0


def haversine_distance_km(
    lat1: float | np.ndarray,
    lon1: float | np.ndarray,
    lat2: float | np.ndarray,
    lon2: float | np.ndarray,
) -> np.ndarray:
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2)
    lon2_rad = np.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return 6371.0 * c


def is_place_near_any_track(
    place_lat: float,
    place_lon: float,
    track_coordinates: list[tuple[np.ndarray, np.ndarray]],
) -> bool:
    for track_lats, track_lons in track_coordinates:
        if track_lats.size == 0:
            continue
        distances_km = haversine_distance_km(
            place_lat, place_lon, track_lats, track_lons
        )
        if float(np.min(distances_km)) <= PLACE_NEARBY_TRACK_THRESHOLD_KM:
            return True
    return False


def zoom_center(
    maxlon,
    minlon,
    maxlat,
    minlat,
    # lons: tuple = None,
    # lats: tuple = None,
    # lonlats: tuple = None,
    # format: str = "lonlat",
    projection: str = "mercator",
    width_to_height: float = 3.0,
) -> (float, dict):
    """Finds optimal zoom and centering for a Plotly map subplot.
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
    # print(
    #     f"{width_to_height = } for mercator, {maxlat = } {minlat = } {maxlon = } {minlon = }"
    # )
    if projection == "mercator":
        # margin = 1.2
        # height = (maxlat - minlat) * margin * width_to_height
        # width = (maxlon - minlon) * margin
        # lon_zoom = np.interp(width, lon_zoom_range, range(20, 0, -1))
        # lat_zoom = np.interp(height, lon_zoom_range, range(20, 0, -1))
        # zoom = round(min(lon_zoom, lat_zoom), 2)

        margin = 1.7

        # Determine raw aspect ratio of the bounding box
        bbox_width = maxlon - minlon
        bbox_height = maxlat - minlat

        # Apply margin
        bbox_width *= margin
        bbox_height *= margin

        # Adjust dimensions so that the final figure has the desired width/height ratio
        target_ratio = width_to_height
        current_ratio = bbox_width / bbox_height
        # print(f"{current_ratio = } {target_ratio = }")

        if current_ratio > target_ratio:
            # Too wide — increase height
            # width_to_height = width / height <-> height = width / width_to_height
            width = bbox_width
            height = bbox_width / width_to_height
        else:
            # Too tall — increase width
            # width_to_height = width / height <-> width = height * width_to_height
            height = bbox_height
            width = bbox_height * width_to_height
        # print(width, height)
        lon_zoom = np.interp(width, lon_zoom_range, range(20, 0, -1))
        lat_zoom = np.interp(height, lon_zoom_range, range(20, 0, -1))
        zoom = round(min(lon_zoom, lat_zoom), 2)
    else:
        raise NotImplementedError(f"{projection} projection is not implemented")
    # print(f"{zoom = }"); exit()
    return zoom, center


class StravaCollection:
    def __init__(
        self,
        name: str,
        activities: list[dict],
        force_update: bool = False,
        description: str | None = None,
        route_gpx_file: str | list[str] | None = None,
        garmin_livetrack_url: str | None = None,
        verbose: bool = False,
        places: list[dict] | None = None,
    ) -> None:
        self._name = name
        self._description = description
        self._route_gpx_file = route_gpx_file
        self._garmin_livetrack_url = garmin_livetrack_url
        self._places = places or []

        self._activity_defs = activities
        print(f"Loading collection '{self.name}':")
        self._activities = []
        for act_def in activities:
            if "strava_id" in act_def:
                parsed_id, flip = act_def["strava_id"]
                self._activities.append(
                    StravaActivity(
                        parsed_id,
                        flip=flip,
                        force_update=force_update,
                        verbose=verbose,
                    )
                )
        print()
        self._total_distance = 0.0
        self._total_elevation_gain = 0.0
        self._total_moving_time = 0.0
        for activity in self.activities:
            self._total_distance += activity.activity.distance
            self._total_elevation_gain += activity.activity.total_elevation_gain
            self._total_moving_time += activity.activity.moving_time
            print(
                f"{activity.activity.name}, distance: {round(activity.activity.distance * 1e-3, 1)} km, elevation gain: {round(activity.activity.total_elevation_gain)} m"
            )
        print(f"Total elevation gain: {round(self._total_elevation_gain)} m")
        print(f"Total distance: {round(self._total_distance * 1e-3, 1)} km")
        print(f"Total moving time: {round(self._total_moving_time / 3600, 1)} hours")

    def plot_elevation(
        self,
        filepath=None,
        height=200,
        config={"staticPlot": True, "displayModeBar": False},
        backend="plotly",
        verbose: bool = False,
    ):
        """Plot elevation profile of all activities with maxplotlib."""
        distance_traveled = 0.0
        traces = []

        for color_index, activity in enumerate(self.activities):
            if activity.no_map:
                continue

            line_color = (
                tikz_palette[color_index % len(tikz_palette)]
                if backend == "tikzfigure"
                else palette[color_index % len(palette)]
            )
            distance = np.array(activity.activity_stream["distance"].data) * 1e-3
            elev = np.array(activity.activity_stream["altitude"].data)
            distance, elev = fastrdp.rdp(distance, elev, epsilon=0.1)

            if activity.flip:
                dmax = distance[-1]
                distance = np.array([dmax - dist for dist in distance])[::-1]
                elev = elev[::-1]

            traces.append(
                {
                    "x": distance + distance_traveled,
                    "y": elev,
                    "color": line_color,
                }
            )

            distance_traveled += activity.activity_stream["distance"].data[-1] * 1e-3

        fig = build_maxplotlib_elevation_plot(
            traces,
            height=height,
            backend=backend,
        )
        print(f"Total distance travelled: {distance_traveled} km")
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

    def plot_map(
        self,
        filepath: str | None = None,
        config: dict = {"scrollZoom": True},
        height: int = 300,
        linewidths: list = [8, 1],
        width_to_height=5.0,
        verbose: bool = False,
        places: list[dict] | None = None,
    ):
        """Plot all activities together as lon/lat lines.

        Args:
            places: List of dicts with 'name', 'lat', 'lon' keys to mark as red dots.
        """
        fig = go.Figure()

        maxlon, minlon = -9999, 9999
        maxlat, minlat = -9999, 9999

        color_index = 0
        track_coordinates: list[tuple[np.ndarray, np.ndarray]] = []

        for activity in self.activities:
            if activity.no_map:
                continue

            df = activity.to_dataframe()

            if df.empty:
                continue

            lons, lats = df["lon"], df["lat"]
            track_coordinates.append((np.array(lats), np.array(lons)))

            maxlon = max(maxlon, max(lons))
            minlon = min(minlon, min(lons))
            maxlat = max(maxlat, max(lats))
            minlat = min(minlat, min(lats))

            # pick a line color from palette
            line_color = palette[color_index % len(palette)]
            # # convert to rgba with alpha=0.3
            # rgba_color = pc.hex_to_rgb(line_color)

            x = np.array(df["lat"])
            y = np.array(df["lon"])
            x_new, y_new = fastrdp.rdp(x, y, 0.001)

            for linestyle in [
                dict(color="white", width=linewidths[0]),
                dict(color=line_color, width=linewidths[1]),
            ]:
                fig.add_trace(
                    go.Scattermap(
                        lat=x_new,
                        lon=y_new,
                        mode="lines",
                        line=linestyle,
                        showlegend=False,
                    )
                )

            # fig.add_trace(
            #     go.Scattermap(
            #         lat=df["lat"],
            #         lon=df["lon"],
            #         mode="lines",
            #         line=dict(color=line_color, width=8),
            #         name=activity.activity.name or f"Activity {activity.activity.id}",
            #     )
            # )
            color_index += 1

        # Add places as markers, turning green if a track passes nearby.
        if places:
            place_lats = [place["lat"] for place in places]
            place_lons = [place["lon"] for place in places]
            place_names = [
                place.get("name", f"Place {i + 1}") for i, place in enumerate(places)
            ]
            place_colors = [
                (
                    "green"
                    if is_place_near_any_track(
                        place["lat"], place["lon"], track_coordinates=track_coordinates
                    )
                    else "red"
                )
                for place in places
            ]

            # Update bounds to include places
            if place_lats:
                maxlat = max(maxlat, max(place_lats))
                minlat = min(minlat, min(place_lats))
                maxlon = max(maxlon, max(place_lons))
                minlon = min(minlon, min(place_lons))

            fig.add_trace(
                go.Scattermap(
                    lat=place_lats,
                    lon=place_lons,
                    mode="markers",
                    marker=dict(
                        size=PLACE_MARKER_SIZE,
                        color=place_colors,
                        opacity=0.8,
                    ),
                    text=place_names,
                    hovertemplate="<b>%{text}</b><br>Lat: %{lat}<br>Lon: %{lon}<extra></extra>",
                    showlegend=False,
                )
            )

        zoom, center = zoom_center(
            maxlon, minlon, maxlat, minlat, width_to_height=width_to_height
        )

        styles = [
            "outdoors",
            "streets",
            "light",
            "dark",
            "satellite",
            "satellite-streets",
            # "navigation-day",
            # "navigation-night"
        ]
        # Create buttons for each style
        buttons = [
            dict(
                label=style.replace("-", " ").title(),
                method="relayout",
                args=["map.style", style],
            )
            for style in styles
        ]
        map_layout = {
            "style": "outdoors",
            "center": center,
            "zoom": zoom,
        }

        fig.update_layout(
            height=height,
            dragmode="zoom",
            showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            # title="Strava Activities",
            map=map_layout,
            updatemenus=[
                dict(
                    type="dropdown",
                    x=0.0,
                    y=1.0,
                    buttons=buttons,
                    showactive=True,
                    xanchor="left",
                    yanchor="top",
                )
            ],
        )

        if isinstance(filepath, str):
            export_plotly_fig(
                fig=fig,
                filepath=filepath,
                config=config,
                height=height,
                width_to_height=width_to_height,
                full_html=True,
            )
            if verbose:
                print(f"Saved map plot to: {filepath}")
        return fig

    def build_collection_body_html(
        self,
        mapfig_name: str,
        elevfig_name: str,
        include_activity_elevation: bool = False,
        activity_elevation_extension: str = "html",
        sort_by_date: bool = False,
        include_table: bool = False,
    ):
        html_str = ""

        collection_table_md = ""
        if include_table:
            data = []
            for activity in self.activities:
                name_link = (
                    f'<a href="{activity.link}" target="_blank" rel="noopener">'
                    f"{escape(activity.activity.name)}</a>"
                )
                data.append(
                    {
                        "Activity": name_link,
                        "Date": activity.activity.start_date_local.date(),
                        "Distance (km)": round(
                            float(activity.activity.distance) * 1e-3, 1
                        ),
                        "Elevation Gain (m)": round(
                            float(activity.activity.total_elevation_gain)
                        ),
                    }
                )

            df = pd.DataFrame(data)
            if sort_by_date:
                df = df.sort_values(by="Date", ascending=True)

            collection_table_md = df.to_html(index=False, escape=False, border=0)

        html_str += "\n\n"
        for activity in self.activities:
            html_str += activity.generate_markdown_summary(
                include_elevation=include_activity_elevation,
                elevation_asset_extension=activity_elevation_extension,
            )
        return f"{html_str}{collection_table_md}"

    def generate_markdown(
        self,
        filepath: str,
        mapfig_name: str,
        elevfig_name: str,
        include_activity_elevation: bool = False,
        activity_elevation_extension: str = "html",
        sort_by_date: bool = False,
        include_table: bool = False,
        prettify: bool = False,
        verbose: bool = False,
    ):
        body_html = self.build_collection_body_html(
            mapfig_name=mapfig_name,
            elevfig_name=elevfig_name,
            include_activity_elevation=include_activity_elevation,
            activity_elevation_extension=activity_elevation_extension,
            sort_by_date=sort_by_date,
            include_table=include_table,
        )

        if prettify:
            with tempfile.NamedTemporaryFile(
                "w+", suffix=".html", delete=False, encoding="utf-8"
            ) as tmp_file:
                tmp_file.write(body_html)
                tmp_file.flush()
                tmp_path = Path(tmp_file.name)
                tmp_folder = tmp_path.parent
            subprocess.run(
                ["prettier", "--write", str(tmp_path)], check=True, cwd=tmp_folder
            )

            with open(tmp_path, "r", encoding="utf-8") as f:
                body_html = f.read()

        title_heading = f"<h1>{escape(self.name)}</h1>\n"
        if body_html.startswith(title_heading):
            body_html = body_html.removeprefix(title_heading)
        collection_full_md = (
            f'---\ntitle: "{self.name}"\n---\n# {self.name}\n{body_html}'
        )

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(collection_full_md)
        if verbose:
            print(f"Saved markdown page to {filepath}")

    @property
    def activity_defs(self):
        return self._activity_defs

    @property
    def route_gpx_file(self):
        return self._route_gpx_file

    @property
    def garmin_livetrack_url(self):
        return self._garmin_livetrack_url

    @property
    def description(self):
        return self._description

    @property
    def places(self):
        return self._places

    @property
    def total_distance_km(self):
        """Total distance in kilometers."""
        return round(self._total_distance * 1e-3, 1)

    @property
    def total_elevation_gain_m(self):
        """Total elevation gain in meters."""
        return round(self._total_elevation_gain)

    @property
    def total_moving_time_hours(self):
        """Total moving time in hours."""
        return round(self._total_moving_time / 3600, 1)

    def generate_gpx_assets(
        self,
        output_dir: Path,
        rdp_epsilon: float = 0.0001,
        verbose: bool = False,
    ):
        """Export GPX files for all activities to the output directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        for activity in self.activities:
            if activity.no_map:
                continue
            gpx_path = output_dir / f"activity-{activity.activity_id}.gpx"
            gpx_content = activity.to_gpx(rdp_epsilon=rdp_epsilon)
            gpx_path.write_text(gpx_content, encoding="utf-8")
            if verbose:
                print(f"Saved GPX asset to: {gpx_path}")

    def generate_astro(
        self,
        filepath: str,
        mapfig_name: str,
        elevfig_name: str,
        include_activity_elevation: bool = False,
        activity_elevation_extension: str = "html",
        sort_by_date: bool = False,
        include_table: bool = False,
        prettify: bool = False,
        verbose: bool = False,
    ):
        body_html = self.build_collection_body_html(
            mapfig_name=mapfig_name,
            elevfig_name=elevfig_name,
            include_activity_elevation=include_activity_elevation,
            activity_elevation_extension=activity_elevation_extension,
            sort_by_date=sort_by_date,
            include_table=include_table,
        )
        asset_dir = Path(filepath).parent / "_static"
        metadata = {
            "activities": self.activity_defs,
            "routeGpxFile": self.route_gpx_file,
            "garminLivetrackUrl": self.garmin_livetrack_url,
            "description": self.description,
            "places": self.places,
            "totalDistanceKm": self.total_distance_km,
            "totalElevationGainM": self.total_elevation_gain_m,
            "totalMovingTimeHours": self.total_moving_time_hours,
        }
        page_source = render_collection_page(
            title=self.name,
            body_html=prepare_collection_markup(body_html, asset_dir=asset_dir),
            metadata=metadata,
        )

        if prettify:
            with tempfile.NamedTemporaryFile(
                "w+", suffix=".astro", delete=False, encoding="utf-8"
            ) as tmp_file:
                tmp_file.write(page_source)
                tmp_file.flush()
                tmp_path = Path(tmp_file.name)
                tmp_folder = tmp_path.parent
            subprocess.run(
                ["prettier", "--write", str(tmp_path)], check=True, cwd=tmp_folder
            )

            with open(tmp_path, "r", encoding="utf-8") as f:
                page_source = f.read()

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(page_source)
        if verbose:
            print(f"Saved Astro page to {filepath}")

    def to_yaml(self, output_dir, filename: str | None = None):
        yaml_str = ""
        yaml_str += f'collection_name: "{self.name}"\n'
        yaml_str += f'output_dir: "{output_dir}"\n'
        yaml_str += "activity_ids:\n"
        for activity in self.activities:
            id = f"{activity.activity_id}"
            if activity.flip:
                id += "F"
            yaml_str += f'  - "{id}" # {activity.activity.name}\n'

        if filename:
            with open(filename, "w") as f:
                f.write(yaml_str)

        return yaml_str

    @property
    def activities(self) -> List[StravaActivity]:
        return self._activities

    @property
    def client(self):
        return self._client

    @property
    def activity_ids(self):
        return self._activity_ids

    @property
    def name(self):
        return self._name
