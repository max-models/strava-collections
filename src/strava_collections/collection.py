import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

import fastrdp
import numpy as np
import pandas as pd
import plotly.colors as pc
import plotly.graph_objects as go
import yaml

from strava_collections.activity import StravaActivity
from strava_collections.utils import export_plotly_fig

palette = pc.qualitative.Plotly  # default Plotly categorical colors
mapbox_token = os.getenv("MAPBOX_TOKEN")


class StravaCollection:
    def __init__(
        self,
        name: str,
        activity_ids: list[tuple],
        force_update: bool = False,
    ) -> None:
        self._name = name

        self._activity_ids = activity_ids
        self._activities = [
            StravaActivity(
                *(activity_id),
                force_update=force_update,
            )
            for activity_id in activity_ids
        ]
        tot_elevation_gaion = 0.0
        for activity in self.activities:
            tot_elevation_gaion += activity.activity.total_elevation_gain
            print(
                f"{activity.activity.name}, distance: {round(activity.activity.distance * 1e-3, 1)} km, elevation gain: {round(activity.activity.total_elevation_gain)} m"
            )
        print(f"{tot_elevation_gaion = }")

    def plot_elevation(
        self,
        filepath=None,
        height=200,
        config={"staticPlot": True, "displayModeBar": False},
    ):
        """Plot elevation profile of all activities with filled translucent area."""
        fig = go.Figure()

        distance_traveled = 0.0

        for color_index, activity in enumerate(self.activities):

            # pick a line color from palette
            line_color = palette[color_index % len(palette)]

            activity.add_elevation_to_fig(
                fig=fig,
                distance_traveled=distance_traveled,
                color=line_color,
            )

            distance_traveled += activity.activity_stream["distance"].data[-1] * 1e-3

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
        print(f"Total distance travelled: {distance_traveled} km")
        if isinstance(filepath, str):
            export_plotly_fig(fig=fig, filepath=filepath, config=config)
            print(f"Saved elevation plot to: {filepath}")
        return fig

    def plot_map(
        self,
        filepath: str | None = None,
        config: dict = {"scrollZoom": True},
        height: int = 300,
        linewidths: list = [8, 1],
        width_to_height=5.0,
    ):
        """Plot all activities together as lon/lat lines."""
        fig = go.Figure()

        maxlon, minlon = -9999, 9999
        maxlat, minlat = -9999, 9999

        color_index = 0

        for activity in self.activities:
            df = activity.to_dataframe()

            lons, lats = df["lon"], df["lat"]

            maxlon = max(maxlon, max(lons))
            minlon = min(minlon, min(lons))
            maxlat = max(maxlat, max(lats))
            minlat = min(minlat, min(lats))

            if df.empty:
                continue

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
                    go.Scattermapbox(
                        lat=x_new,
                        lon=y_new,
                        mode="lines",
                        line=linestyle,
                        showlegend=False,
                    )
                )

            # fig.add_trace(
            #     go.Scattermapbox(
            #         lat=df["lat"],
            #         lon=df["lon"],
            #         mode="lines",
            #         line=dict(color=line_color, width=8),
            #         name=activity.activity.name or f"Activity {activity.activity.id}",
            #     )
            # )
            color_index += 1

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
                label=style.capitalize().replace("-", " "),
                method="relayout",
                args=["mapbox.style", style],
            )
            for style in styles
        ]

        fig.update_layout(
            height=height,
            dragmode="zoom",
            showlegend=False,
            margin=dict(l=0, r=0, t=0, b=0),
            # title="Strava Activities",
            mapbox={
                "accesstoken": mapbox_token,
                "style": "outdoors",
                # "style": "satellite",
                "center": center,
                "zoom": zoom,
            },
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
            print(f"Saved map plot to: {filepath}")
        return fig

    def generate_markdown(
        self,
        filepath: str,
        mapfig_name: str,
        elevfig_name: str,
        sort_by_date: bool = False,
        include_table: bool = False,
        prettify: bool = False,
    ):

        # This string will contain the the html for the images and activities,
        # and may be prettified before added to the markdown
        html_str = ""
        html_str += f"""
<div style="position: relative; width: 100%; height: 350px;">
<iframe src="_static/{mapfig_name}" style="width:100%; height:100%; border:none;"></iframe>
</div>
\n\n"""

        html_str += f"""
<div style="position: relative; width: 100%; padding-bottom: 250px; height: 0;">
<iframe src="_static/{elevfig_name}" style="position:absolute; top:0; left:0; width:100%; height:100%; border:none;"></iframe>
</div>\n\n"""

        collection_table_md = ""
        if include_table:
            data = []
            for activity in self.activities:
                name_link = f"[{activity.activity.name}]({activity.link})"
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

            # Convert DataFrame to Markdown table
            collection_table_md = df.to_markdown(index=False)

        html_str += "\n\n"
        # Add blocks with each individual activities
        for activity in self.activities:
            html_str += activity.generate_markdown_summary()
        html_str += """
<div id="lightbox" class="lightbox">
  <img id="lightbox-img" src="" alt="Full Image">
</div>"""
        html_str += """
<script>
document.querySelectorAll('.gallery img').forEach(img => {
  img.addEventListener('click', event => {
    event.preventDefault();  // stop the default link behavior
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightbox-img');
    lightboxImg.src = img.src;
    lightbox.classList.add('show');
  });
});

document.getElementById('lightbox').addEventListener('click', () => {
  document.getElementById('lightbox').classList.remove('show');
});
</script>"""

        if prettify:
            with tempfile.NamedTemporaryFile(
                "w+", suffix=".html", delete=False, encoding="utf-8"
            ) as tmp_file:
                tmp_file.write(html_str)
                tmp_file.flush()
                tmp_path = Path(tmp_file.name)
                tmp_folder = tmp_path.parent
            # print(f"{tmp_path = }")
            subprocess.run(
                ["prettier", "--write", str(tmp_path)], check=True, cwd=tmp_folder
            )

            with open(tmp_path, "r", encoding="utf-8") as f:
                html_str = f.read()

        # Add markdown title
        collection_title_md = f"# {self.name}\n"

        collection_full_md = collection_title_md + html_str + collection_table_md

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(collection_full_md)
        print(f"Saved markdown page to {filepath}")

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
