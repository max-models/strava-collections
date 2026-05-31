from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from strava_collections.activity import StravaActivity
from strava_collections.collection import StravaCollection
from strava_collections.main import elevation_extension_for_backend, main
from strava_collections.utils import build_maxplotlib_elevation_canvas


def test_main_uses_plotly_html_for_yaml_input(monkeypatch, tmp_path):
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
    monkeypatch.setattr("strava_collections.main.mapbox_token", "test-token")
    monkeypatch.setattr(
        "sys.argv",
        ["strava-collections", "-i", str(yaml_path)],
    )

    main()

    assert calls["activity_plot_elevation"][0][0].endswith("activity-123.html")
    assert calls["activity_plot_elevation"][0][1]["backend"] == "plotly"
    assert calls["plot_elevation"][0].endswith("collection-taiwan-elev.html")
    assert calls["plot_elevation"][1]["backend"] == "plotly"
    assert (
        calls["generate_markdown"][1]["elevfig_name"] == "collection-taiwan-elev.html"
    )
    assert calls["generate_markdown"][1]["include_activity_elevation"] is True
    assert calls["generate_markdown"][1]["activity_elevation_extension"] == "html"


def test_main_reuses_existing_map_assets_without_mapbox_token(monkeypatch, tmp_path):
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

    static_dir = tmp_path / "_static"
    static_dir.mkdir()
    for suffix in ("map.html", "map.png", "map-thick.png"):
        (static_dir / f"collection-taiwan-{suffix}").write_text("", encoding="utf-8")

    calls = {}

    class FakeActivity:
        activity_id = 123

        def plot_elevation(self, filepath, **kwargs):
            calls.setdefault("activity_plot_elevation", []).append((filepath, kwargs))

    class FakeCollection:
        def __init__(self, name, activity_ids, force_update=False):
            self.activities = [FakeActivity()]

        def plot_map(self, filepath, **kwargs):
            calls.setdefault("plot_map", []).append((filepath, kwargs))

        def plot_elevation(self, filepath, **kwargs):
            calls["plot_elevation"] = (filepath, kwargs)

        def generate_markdown(self, filepath, **kwargs):
            calls["generate_markdown"] = (filepath, kwargs)

    monkeypatch.setattr("strava_collections.main.StravaCollection", FakeCollection)
    monkeypatch.setattr("strava_collections.main.mapbox_token", None)
    monkeypatch.setattr(
        "sys.argv",
        ["strava-collections", "-i", str(yaml_path)],
    )

    main()

    assert "plot_map" not in calls
    assert calls["plot_elevation"][0].endswith("collection-taiwan-elev.html")
    assert calls["generate_markdown"][0].endswith("collection-taiwan.md")


def test_activity_summary_uses_html_elevation_iframe_by_default():
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

    assert 'src="/_static/activity-1324271479.html"' in markdown
    assert "<iframe " in markdown
    assert "aspect-ratio: 3 / 1" in markdown
    assert "loading=\"lazy\"" not in markdown
    assert "lazy-" not in markdown


def test_collection_markdown_uses_direct_iframe_for_html_elevation(tmp_path):
    collection = StravaCollection.__new__(StravaCollection)
    collection._name = "Taiwan"
    collection._activities = []

    output_path = tmp_path / "collection-taiwan.md"
    collection.generate_markdown(
        filepath=str(output_path),
        mapfig_name="collection-taiwan-map.html",
        elevfig_name="collection-taiwan-elev.html",
    )

    markdown = output_path.read_text(encoding="utf-8")

    assert 'src="/_static/collection-taiwan-map.html"' in markdown
    assert 'src="/_static/collection-taiwan-elev.html"' in markdown
    assert "<iframe " in markdown
    assert "aspect-ratio: 3 / 1" in markdown
    assert "loading=\"lazy\"" not in markdown
    assert "lazy-" not in markdown


def test_elevation_canvas_is_wider_than_2_to_1():
    canvas = build_maxplotlib_elevation_canvas(
        traces=[{"x": [0, 1], "y": [10, 20], "color": "black"}],
        height=200,
    )
    fig, _ = canvas.plot(backend="matplotlib")

    width, height = fig.get_size_inches()
    assert width > 2 * height


def test_elevation_extension_matches_backend():
    assert elevation_extension_for_backend("plotly") == "html"
    assert elevation_extension_for_backend("tikzfigure") == "png"
    assert elevation_extension_for_backend("matplotlib") == "png"
