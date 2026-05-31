import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from strava_collections.activity import StravaActivity
from strava_collections.astro_page import markdown_to_body_html, render_collection_page
from strava_collections.collection import StravaCollection
from strava_collections.main import elevation_extension_for_backend, main
from strava_collections.utils import build_maxplotlib_elevation_canvas

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "docs" / "astro" / "scripts"),
)
import sync_generated_content


def test_main_uses_plotly_html_for_yaml_input(monkeypatch, tmp_path):
    yaml_path = tmp_path / "taiwan.yml"
    legacy_markdown = tmp_path / "collection-taiwan.md"
    legacy_markdown.write_text("old", encoding="utf-8")
    yaml_path.write_text(
        "\n".join(
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

        def generate_astro(self, filepath, **kwargs):
            calls["generate_astro"] = (filepath, kwargs)

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
    assert calls["generate_astro"][1]["elevfig_name"] == "collection-taiwan-elev.html"
    assert calls["generate_astro"][0].endswith("collection-taiwan.astro")
    assert calls["generate_astro"][1]["include_activity_elevation"] is True
    assert calls["generate_astro"][1]["activity_elevation_extension"] == "html"
    assert not legacy_markdown.exists()


def test_main_reuses_existing_map_assets_without_mapbox_token(monkeypatch, tmp_path):
    yaml_path = tmp_path / "taiwan.yml"
    yaml_path.write_text(
        "\n".join(
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

        def generate_astro(self, filepath, **kwargs):
            calls["generate_astro"] = (filepath, kwargs)

    monkeypatch.setattr("strava_collections.main.StravaCollection", FakeCollection)
    monkeypatch.setattr("strava_collections.main.mapbox_token", None)
    monkeypatch.setattr(
        "sys.argv",
        ["strava-collections", "-i", str(yaml_path)],
    )

    main()

    assert "plot_map" not in calls
    assert calls["plot_elevation"][0].endswith("collection-taiwan-elev.html")
    assert calls["generate_astro"][0].endswith("collection-taiwan.astro")


def test_main_accepts_multiple_yaml_inputs(monkeypatch, tmp_path):
    yaml_paths = []
    for name, activity_id in (("Taiwan", "123"), ("Japan", "456")):
        yaml_path = tmp_path / f"{name.lower()}.yml"
        yaml_path.write_text(
            "\n".join(
                [
                    f'collection_name: "{name}"',
                    f'output_dir: "{tmp_path.as_posix()}"',
                    "activity_ids:",
                    f'  - "{activity_id}"',
                ]
            ),
            encoding="utf-8",
        )
        yaml_paths.append(yaml_path)

    calls = {"collections": [], "generate_astro": []}

    class FakeActivity:
        def __init__(self, activity_id):
            self.activity_id = activity_id

        def plot_elevation(self, filepath, **kwargs):
            calls.setdefault("activity_plot_elevation", []).append((filepath, kwargs))

    class FakeCollection:
        def __init__(self, name, activity_ids, force_update=False):
            calls["collections"].append((name, activity_ids, force_update))
            self.activities = [FakeActivity(activity_ids[0][0])]

        def plot_map(self, filepath, **kwargs):
            calls.setdefault("plot_map", []).append((filepath, kwargs))

        def plot_elevation(self, filepath, **kwargs):
            calls.setdefault("plot_elevation", []).append((filepath, kwargs))

        def generate_astro(self, filepath, **kwargs):
            calls["generate_astro"].append((filepath, kwargs))

    monkeypatch.setattr("strava_collections.main.StravaCollection", FakeCollection)
    monkeypatch.setattr("strava_collections.main.mapbox_token", "test-token")
    monkeypatch.setattr(
        "sys.argv",
        [
            "strava-collections",
            "-i",
            str(yaml_paths[0]),
            str(yaml_paths[1]),
        ],
    )

    main()

    assert calls["collections"] == [
        ("Taiwan", [(123, False)], False),
        ("Japan", [(456, False)], False),
    ]
    assert calls["generate_astro"][0][0].endswith("collection-taiwan.astro")
    assert calls["generate_astro"][1][0].endswith("collection-japan.astro")


def test_main_expands_globbed_yaml_inputs(monkeypatch, tmp_path):
    for name, activity_id in (("Taiwan", "123"), ("Japan", "456")):
        (tmp_path / f"{name.lower()}.yml").write_text(
            "\n".join(
                [
                    f'collection_name: "{name}"',
                    f'output_dir: "{tmp_path.as_posix()}"',
                    "activity_ids:",
                    f'  - "{activity_id}"',
                ]
            ),
            encoding="utf-8",
        )

    seen_names = []

    class FakeActivity:
        def __init__(self, activity_id):
            self.activity_id = activity_id

        def plot_elevation(self, filepath, **kwargs):
            return None

    class FakeCollection:
        def __init__(self, name, activity_ids, force_update=False):
            seen_names.append(name)
            self.activities = [FakeActivity(activity_ids[0][0])]

        def plot_map(self, filepath, **kwargs):
            return None

        def plot_elevation(self, filepath, **kwargs):
            return None

        def generate_astro(self, filepath, **kwargs):
            return None

    monkeypatch.setattr("strava_collections.main.StravaCollection", FakeCollection)
    monkeypatch.setattr("strava_collections.main.mapbox_token", "test-token")
    monkeypatch.setattr(
        "sys.argv",
        ["strava-collections", "-i", str(tmp_path / "*.yml")],
    )

    main()

    assert seen_names == ["Japan", "Taiwan"]


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
    assert 'loading="lazy"' not in markdown
    assert "lazy-" not in markdown


def test_activity_summary_gallery_images_keep_lightbox_class_and_accessibility():
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
    activity._photos = [{"urls": {"500": "https://example.com/photo.jpg"}}]

    markdown = activity.generate_markdown_summary(include_elevation=False)

    assert '<h2 class="description-title">Day 1</h2>' in markdown
    assert 'class="lightbox-trigger"' in markdown
    assert 'loading="lazy"' in markdown
    assert 'decoding="async"' in markdown
    assert 'alt="Day 1 photo 1"' in markdown


def test_collection_generate_astro_writes_astro_page(tmp_path):
    collection = StravaCollection.__new__(StravaCollection)
    collection._name = "Taiwan"
    collection._activities = []
    static_dir = tmp_path / "_static"
    static_dir.mkdir()
    for asset_name in ("collection-taiwan-map.html", "collection-taiwan-elev.html"):
        (static_dir / asset_name).write_text(
            """
<html>
  <body>
    <div id="plot" class="plotly-graph-div"></div>
    <script>Plotly.newPlot("plot", [], {});</script>
  </body>
</html>
""".strip(),
            encoding="utf-8",
        )

    output_path = tmp_path / "collection-taiwan.astro"
    collection.generate_astro(
        filepath=str(output_path),
        mapfig_name="collection-taiwan-map.html",
        elevfig_name="collection-taiwan-elev.html",
    )

    astro_page = output_path.read_text(encoding="utf-8")

    assert "CollectionPage.astro" in astro_page
    assert 'const title = "Taiwan";' in astro_page
    assert "Plotly.newPlot" in astro_page
    assert "bodyHtml" not in astro_page
    assert "<CollectionPage title={title} headings={headings}>" in astro_page
    assert "<script is:inline>" in astro_page
    assert "<iframe " not in astro_page
    assert 'src="/_static/collection-taiwan-map.html"' not in astro_page


def test_generate_astro_inlines_plotly_and_wraps_gallery(tmp_path):
    markdown = """# Taiwan

<div class="gallery"><img src="/_static/photo.jpg" class="lightbox-trigger"></div>

<div id="lightbox" class="lightbox">
  <img id="lightbox-img" src="" alt="Full Image">
</div>
<script>
document.querySelectorAll('.gallery img').forEach(img => {
  img.addEventListener('click', event => {
    event.preventDefault();
  });
});
</script>
"""

    body_html = markdown_to_body_html(markdown, asset_dir=tmp_path / "_static")
    page = render_collection_page(title="Taiwan", body_html=body_html)

    assert 'id="lightbox"' not in body_html
    assert "querySelectorAll('.gallery img')" not in body_html
    assert 'class="gallery"' in body_html
    assert 'class="glightbox"' in body_html
    assert 'data-gallery="collection-gallery-0"' in body_html
    assert "CollectionPage.astro" in page
    assert 'const title = "Taiwan";' in page
    assert "const headings = [" in page
    assert "bodyHtml" not in page
    assert "<CollectionPage title={title} headings={headings}>" in page
    assert "href={`${base}_static/photo.jpg`}" in page


def test_markdown_to_body_html_inlines_local_plotly_assets(tmp_path):
    static_dir = tmp_path / "_static"
    static_dir.mkdir(parents=True)
    (static_dir / "activity-123.html").write_text(
        """
<html>
  <head><meta charset="utf-8" /></head>
  <body>
    <div>
      <script>window.PlotlyConfig = {MathJaxConfig: 'local'};</script>
      <script charset="utf-8" src="https://cdn.plot.ly/plotly-3.4.0.min.js" integrity="sha256-KEmPoupLpFyGMyGAiOsiNDbKDKAvxXAn/W+oQa0ZAfk=" crossorigin="anonymous"></script>
      <div id="plot-123" class="plotly-graph-div" style="height:200px; width:100%;"></div>
      <script>Plotly.newPlot("plot-123", [], {});</script>
    </div>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    markdown = """# Taiwan

<div style="position: relative; width: 100%; height: 220px; aspect-ratio: 3 / 1;">
  <iframe src="/_static/activity-123.html" style="width:100%; height:100%; border:none; border-radius: 12px;"></iframe>
</div>
"""

    converted = markdown_to_body_html(markdown, asset_dir=static_dir)

    assert "<iframe " not in converted
    assert 'class="plotly-embed plotly-embed--chart"' in converted
    assert 'id="plot-123"' in converted
    assert 'Plotly.newPlot("plot-123", [], {});' in converted
    assert "cdn.plot.ly" not in converted
    assert "window.PlotlyConfig" not in converted


def test_markdown_to_body_html_promotes_description_titles_to_headings(tmp_path):
    converted = markdown_to_body_html(
        """
# Berlin to Tarifa

<div class="description-box">
<div class="description-title">To Dresden 🚴🇪🇺🇨🇿🇩🇪</div>
</div>
""".strip(),
        asset_dir=tmp_path / "_static",
    )

    assert '<h2 class="description-title">To Dresden 🚴🇪🇺🇨🇿🇩🇪</h2>' in converted
    assert '<div class="description-title">To Dresden 🚴🇪🇺🇨🇿🇩🇪</div>' not in converted


def test_render_collection_page_keeps_plotly_scripts_inline():
    page = render_collection_page(
        title="Taiwan",
        body_html="""
<div class="plotly-embed plotly-embed--chart">
  <div id="plot-123" class="plotly-graph-div"></div>
  <script>Plotly.newPlot("plot-123", [], {});</script>
</div>
""".strip(),
    )

    assert '<script is:inline>Plotly.newPlot("plot-123", [], {});</script>' in page
    assert "<script>Plotly.newPlot" not in page


def test_render_collection_page_extracts_heading_links():
    page = render_collection_page(
        title="Taiwan",
        body_html="""
<h1>Taiwan</h1>
<h2>Day 1: Taipei</h2>
<h2>Day 2: Yilan</h2>
<h3>Climb</h3>
""".strip(),
    )

    assert '"title": "Day 1: Taipei"' in page
    assert '"slug": "day-1-taipei"' in page
    assert '"level": 2' in page
    assert '<h2 id="day-1-taipei">Day 1: Taipei</h2>' in page
    assert '<h3 id="climb">Climb</h3>' in page


def test_render_collection_page_extracts_promoted_description_titles():
    page = render_collection_page(
        title="Berlin to Tarifa",
        body_html="""
<h1>Berlin to Tarifa</h1>
<div class="description-box">
  <h2 class="description-title">To Dresden 🚴🇪🇺🇨🇿🇩🇪</h2>
</div>
""".strip(),
    )

    assert "To Dresden" in page
    assert '"slug": "to-dresden"' in page
    assert (
        '<h2 class="description-title" id="to-dresden">To Dresden 🚴🇪🇺🇨🇿🇩🇪</h2>' in page
    )


def test_sync_collections_prefers_generated_astro(monkeypatch, tmp_path):
    source_dir = tmp_path / "source"
    page_dir = tmp_path / "pages"
    generated_dir = tmp_path / "generated"
    static_dir = source_dir / "_static"
    static_dir.mkdir(parents=True)

    (source_dir / "collection-taiwan.md").write_text(
        "# Wrong Title\n",
        encoding="utf-8",
    )
    (source_dir / "collection-taiwan.astro").write_text(
        """---
import CollectionPage from '../../components/CollectionPage.astro';

const title = "Taiwan";
const base = import.meta.env.BASE_URL.endsWith('/')
  ? import.meta.env.BASE_URL
  : `${import.meta.env.BASE_URL}/`;
---

<CollectionPage title={title} headings={[]}>
  <h1>Taiwan</h1>
</CollectionPage>
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(sync_generated_content, "SPHINX_SOURCE", source_dir)
    monkeypatch.setattr(sync_generated_content, "PAGE_DIR", page_dir)
    monkeypatch.setattr(sync_generated_content, "GENERATED_DIR", generated_dir)
    monkeypatch.setattr(
        sync_generated_content,
        "MANIFEST_PATH",
        generated_dir / "collections.ts",
    )

    sync_generated_content.sync_collections()

    synced_page = (page_dir / "taiwan.astro").read_text(encoding="utf-8")
    manifest = (generated_dir / "collections.ts").read_text(encoding="utf-8")

    assert 'const title = "Taiwan";' in synced_page
    assert "Wrong Title" not in synced_page
    assert '"slug": "taiwan"' in manifest


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
