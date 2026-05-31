from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from strava_collections.activity import StravaActivity
from strava_collections.collection import StravaCollection
from strava_collections.main import main
from strava_collections.utils import build_maxplotlib_elevation_canvas


def test_main_uses_tikz_png_for_yaml_input(monkeypatch, tmp_path):
    yaml_path = tmp_path / "taiwan.yml"
    yaml_path.write_text(
        '\n'.join(
            [
                'collection_name: "Taiwan"',
                f'output_dir: "{tmp_path.as_posix()}"',
                "activity_ids:",
                '  - "123"',
            ]
        ),
        encoding="utf-8",
    )

    calls = {}

    class FakeActivity:
        activity_id = 123

        def plot_elevation(self, filepath, **kwargs):
            calls.setdefault("activity_plot_elevation", []).append((filepath, kwargs))

    class FakeCollection:
        def __init__(self, name, activity_ids, force_update=False):
            calls["name"] = name
            calls["activity_ids"] = activity_ids
            calls["force_update"] = force_update
            self.activities = [FakeActivity()]

        def plot_map(self, filepath, **kwargs):
            calls.setdefault("plot_map", []).append((filepath, kwargs))

        def plot_elevation(self, filepath, **kwargs):
            calls["plot_elevation"] = (filepath, kwargs)

        def generate_markdown(self, filepath, **kwargs):
            calls["generate_markdown"] = (filepath, kwargs)

    monkeypatch.setattr("strava_collections.main.StravaCollection", FakeCollection)
    monkeypatch.setattr(
        "sys.argv",
        ["strava-collections", "-i", str(yaml_path)],
    )

    main()

    assert calls["activity_plot_elevation"][0][0].endswith("activity-123.png")
    assert calls["activity_plot_elevation"][0][1]["backend"] == "tikzfigure"
    assert calls["plot_elevation"][0].endswith("collection-taiwan-elev.png")
    assert calls["plot_elevation"][1]["backend"] == "tikzfigure"
    assert calls["generate_markdown"][1]["elevfig_name"] == "collection-taiwan-elev.png"
    assert calls["generate_markdown"][1]["include_activity_elevation"] is True
    assert calls["generate_markdown"][1]["activity_elevation_extension"] == "png"


def test_activity_summary_uses_png_elevation_asset_by_default():
    activity = StravaActivity.__new__(StravaActivity)
    activity._activity_id = 1324271479
    activity._activity = SimpleNamespace(
        name="Day 1",
        start_date_local=datetime(2025, 1, 1),
        distance=1000.0,
        total_elevation_gain=50.0,
        elapsed_time=3600,
        description="",
    )
    activity._photos = []

    markdown = activity.generate_markdown_summary(include_elevation=True)

    assert 'src="/_static/activity-1324271479.png"' in markdown
    assert 'alt="Day 1 elevation profile"' in markdown
    assert "<img " in markdown
    assert "loading=\"lazy\"" not in markdown
    assert "lazy-" not in markdown


def test_collection_markdown_uses_direct_image_for_png_elevation(tmp_path):
    collection = StravaCollection.__new__(StravaCollection)
    collection._name = "Taiwan"
    collection._activities = []

    output_path = tmp_path / "collection-taiwan.md"
    collection.generate_markdown(
        filepath=str(output_path),
        mapfig_name="collection-taiwan-map.html",
        elevfig_name="collection-taiwan-elev.png",
    )

    markdown = output_path.read_text(encoding="utf-8")

    assert 'src="/_static/collection-taiwan-map.html"' in markdown
    assert 'src="/_static/collection-taiwan-elev.png"' in markdown
    assert "<iframe " in markdown
    assert "<img " in markdown
    assert "loading=\"lazy\"" not in markdown
    assert "lazy-" not in markdown


def test_elevation_canvas_uses_2_to_1_ratio():
    canvas = build_maxplotlib_elevation_canvas(
        traces=[{"x": [0, 1], "y": [10, 20], "color": "black"}],
        height=200,
    )
    fig, _ = canvas.plot(backend="matplotlib")

    width, height = fig.get_size_inches()
    assert width == 2 * height
