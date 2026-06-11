import json
import re
from html import unescape
from pathlib import Path

import markdown

TITLE_FROM_ASTRO_RE = re.compile(r'const title = (?P<literal>"(?:[^"\\]|\\.)*");')
FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n?", re.DOTALL)
MARKDOWN_TITLE_RE = re.compile(
    r'^\s*title:\s*["\']?(?P<title>.+?)["\']?\s*$', re.MULTILINE
)
H1_RE = re.compile(r"^\s*#\s+(?P<title>.+?)\s*$", re.MULTILINE)
SCRIPT_TAG_RE = re.compile(r"<script(?P<attrs>[^>]*)>")
STATIC_ASSET_ATTR_RE = re.compile(
    r'(?P<attr>src|href)="(?P<prefix>/?_static/)(?P<asset>[^"]+)"'
)
IFRAME_WRAPPER_RE = re.compile(
    r"<div[^>]*>\s*<iframe[^>]*src=\"(?P<src>/ ?_static/[^\">]+\.html)\"[^>]*></iframe>\s*</div>",
    re.DOTALL,
)
IFRAME_RE = re.compile(
    r"<iframe[^>]*src=\"(?P<src>/?_static/[^\">]+\.html)\"[^>]*></iframe>",
    re.DOTALL,
)
BODY_RE = re.compile(r"<body[^>]*>(?P<body>.*)</body>", re.DOTALL | re.IGNORECASE)
PLOTLY_CDN_RE = re.compile(
    r"<script[^>]*src=\"https://cdn\.plot\.ly/plotly-[^\"]+\"[^>]*>\s*</script>",
    re.DOTALL | re.IGNORECASE,
)
PLOTLY_CONFIG_RE = re.compile(
    r"<script[^>]*>\s*window\.PlotlyConfig\s*=\s*\{.*?\};?\s*</script>",
    re.DOTALL,
)
LEGACY_LIGHTBOX_RE = re.compile(
    r"<div id=\"lightbox\".*?</div>\s*<script>.*?querySelectorAll\('\.gallery img'\).*?</script>",
    re.DOTALL,
)
DESCRIPTION_TITLE_RE = re.compile(
    r'<div class="description-title">(?P<text>.*?)</div>',
    re.DOTALL,
)
GALLERY_RE = re.compile(r"<div class=\"gallery\">(?P<content>.*?)</div>", re.DOTALL)
IMG_RE = re.compile(r"<img(?P<attrs>[^>]*?)>")
SRC_RE = re.compile(r'src="(?P<src>[^"]+)"')
ALT_RE = re.compile(r'alt="(?P<alt>[^"]*)"')
CLASS_RE = re.compile(r'class="(?P<classname>[^"]*)"')
HEADING_RE = re.compile(
    r"<h(?P<level>[1-3])(?P<attrs>[^>]*)>(?P<text>.*?)</h(?P=level)>",
    re.DOTALL | re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


METADATA_FROM_ASTRO_RE = re.compile(r"const metadata = (?P<json>\{.*?\});", re.DOTALL)


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1)


def route_slug_from_filename(file_slug: str) -> str:
    return file_slug.removeprefix("collection-")


def title_from_markdown(source_text: str) -> str:
    frontmatter_match = MARKDOWN_TITLE_RE.search(source_text)
    if frontmatter_match:
        return frontmatter_match.group("title").strip()
    heading_match = H1_RE.search(strip_frontmatter(source_text))
    if heading_match:
        return heading_match.group("title").strip()
    raise ValueError("Could not extract title from markdown source")


def title_from_astro(source_text: str) -> str:
    match = TITLE_FROM_ASTRO_RE.search(source_text)
    if not match:
        raise ValueError("Could not extract title from Astro source")
    return json.loads(match.group("literal"))


def metadata_from_astro(source_text: str) -> dict:
    match = METADATA_FROM_ASTRO_RE.search(source_text)
    if not match:
        return {}
    return json.loads(match.group("json"))


def load_local_plotly_asset(asset_path: Path) -> str:
    asset_html = asset_path.read_text(encoding="utf-8")
    body_match = BODY_RE.search(asset_html)
    body = body_match.group("body") if body_match else asset_html
    body = PLOTLY_CDN_RE.sub("", body)
    body = PLOTLY_CONFIG_RE.sub("", body)
    return body.strip()


def inline_local_plotly_iframes(markup: str, asset_dir: Path) -> str:
    def replace_iframe(match: re.Match[str]) -> str:
        src = match.group("src").replace(" ", "")
        asset_name = Path(src).name
        asset_path = asset_dir / asset_name
        if not asset_path.exists():
            return match.group(0)
        embed_variant = (
            "plotly-embed--map" if "map" in asset_name else "plotly-embed--chart"
        )
        body = load_local_plotly_asset(asset_path)

        return f'<div class="plotly-embed {embed_variant}">\n{body}\n</div>'

    updated = IFRAME_WRAPPER_RE.sub(replace_iframe, markup)
    return IFRAME_RE.sub(replace_iframe, updated)


def strip_legacy_lightbox(markup: str) -> str:
    return LEGACY_LIGHTBOX_RE.sub("", markup)


def promote_description_titles(markup: str) -> str:
    return DESCRIPTION_TITLE_RE.sub(
        lambda match: f'<h2 class="description-title">{match.group("text")}</h2>',
        markup,
    )


def wrap_gallery_images(markup: str) -> str:
    def replace_gallery(match: re.Match[str]) -> str:
        gallery_index = replace_gallery.counter
        replace_gallery.counter += 1
        gallery_id = f"collection-gallery-{gallery_index}"
        content = match.group("content")

        def replace_img(img_match: re.Match[str]) -> str:
            attrs = img_match.group("attrs")
            src_match = SRC_RE.search(attrs)
            if not src_match:
                return img_match.group(0)
            src = src_match.group("src")
            alt_match = ALT_RE.search(attrs)
            alt = alt_match.group("alt") if alt_match else ""
            class_match = CLASS_RE.search(attrs)
            class_attr = (
                f' class="{class_match.group("classname")}"' if class_match else ""
            )
            return (
                f'<a href="{src}" class="glightbox" data-gallery="{gallery_id}"'
                f' aria-label="{alt or "Open gallery image"}">'
                f"<img{attrs}></a>"
            )

        wrapped = IMG_RE.sub(replace_img, content)
        return f'<div class="gallery">{wrapped}</div>'

    replace_gallery.counter = 0
    return GALLERY_RE.sub(replace_gallery, markup)


def prepare_collection_markup(markup: str, asset_dir: Path) -> str:
    prepared = strip_legacy_lightbox(markup)
    prepared = promote_description_titles(prepared)
    prepared = wrap_gallery_images(prepared)
    return prepared


def markdown_to_body_html(markdown_text: str, asset_dir: Path) -> str:
    body = strip_frontmatter(markdown_text)
    body = prepare_collection_markup(markup=body, asset_dir=asset_dir)
    return markdown.markdown(body, extensions=["tables"])


def slugify_heading(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def extract_text(html_fragment: str) -> str:
    return WHITESPACE_RE.sub(" ", unescape(TAG_RE.sub("", html_fragment))).strip()


def add_heading_ids_and_collect(body_html: str) -> tuple[str, list[dict[str, str]]]:
    seen: dict[str, int] = {}
    headings: list[dict[str, str]] = []

    def replace_heading(match: re.Match[str]) -> str:
        level = int(match.group("level"))
        attrs = match.group("attrs")
        inner = match.group("text")
        title = extract_text(inner)
        if not title:
            return match.group(0)

        slug_base = slugify_heading(title)
        count = seen.get(slug_base, 0)
        seen[slug_base] = count + 1
        slug = slug_base if count == 0 else f"{slug_base}-{count + 1}"

        headings.append({"title": title, "slug": slug, "level": level})

        if re.search(r'\sid="[^"]+"', attrs):
            return match.group(0)
        return f'<h{level}{attrs} id="{slug}">{inner}</h{level}>'

    return HEADING_RE.sub(replace_heading, body_html), headings


def rewrite_static_asset_paths_for_astro(markup: str) -> str:
    def replace_attr(match: re.Match[str]) -> str:
        attr = match.group("attr")
        asset = match.group("asset")
        return f"{attr}={{`${{base}}_static/{asset}`}}"

    return STATIC_ASSET_ATTR_RE.sub(replace_attr, markup)


def inline_scripts_for_astro(markup: str) -> str:
    def replace_script(match: re.Match[str]) -> str:
        attrs = match.group("attrs")
        if "is:inline" in attrs:
            return match.group(0)
        return f"<script is:inline{attrs}>"

    return SCRIPT_TAG_RE.sub(replace_script, markup)


def body_html_to_astro_markup(body_html: str) -> tuple[str, list[dict[str, str]]]:
    markup_with_ids, headings = add_heading_ids_and_collect(body_html.strip())
    markup = rewrite_static_asset_paths_for_astro(markup_with_ids)
    return inline_scripts_for_astro(markup), headings


def render_collection_page(
    title: str, body_html: str, metadata: dict | None = None
) -> str:
    markup, headings = body_html_to_astro_markup(body_html)
    metadata_json = json.dumps(metadata or {}, indent=2)
    
    # Generate fullscreen map URL based on collection name
    collection_slug = title.lower().replace(" ", "-")
    fullscreen_map_url = f"${{base}}_static/collection-{collection_slug}-map-fullscreen.html"
    
    return (
        "---\n"
        "import CollectionPage from '../../components/CollectionPage.astro';\n"
        "import Map from '../../components/Map.astro';\n"
        "import { loadStravaRouteData, loadPlannedRouteData, loadPlannedRoutesIndividually } from '../../scripts/data-helpers';\n\n"
        f"const title = {json.dumps(title)};\n"
        f"const headings = {json.dumps(headings, indent=2)};\n"
        f"const metadata = {metadata_json};\n"
        "const base = import.meta.env.BASE_URL.endsWith('/')\n"
        "  ? import.meta.env.BASE_URL\n"
        "  : `${import.meta.env.BASE_URL}/`;\n\n"
        "// Prepare map data\n"
        "const palette = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52'];\n"
        "const stravaRouteData = loadStravaRouteData(metadata.activities || []);\n"
        "const plannedRoutesIndividual = loadPlannedRoutesIndividually(metadata.routeGpxFile);\n"
        "const trackerPayload = {\n"
        "  collections: [{\n"
        "    name: title,\n"
        "    color: '#fc4c02',\n"
        "    plannedRoutes: plannedRoutesIndividual,\n"
        "    activities: (metadata.activities || []).map((act, i) => ({\n"
        "      ...act,\n"
        "      color: palette[i % palette.length],\n"
        "      routeData: stravaRouteData[i],\n"
        "      plannedRouteData: loadPlannedRouteData(act.routeGpxFile),\n"
        "    }))\n"
        "  }]\n"
        "};\n"
        f"const fullscreenMapUrl = `{fullscreen_map_url}`;\n"
        "---\n\n"
        "<CollectionPage title={title} headings={headings}>\n"
        "  {metadata.garminLivetrackUrl && (\n"
        "    <section class=\"garmin-livetrack-section mb-12\">\n"
        "      <h2 class=\"text-2xl font-bold text-slate-900 mb-6 flex items-center gap-2\">\n"
        "        <span class=\"inline-block w-3 h-3 bg-red-500 rounded-full animate-pulse\"></span>\n"
        "        Live Tracking\n"
        "      </h2>\n"
        "      <div class=\"garmin-iframe-container\" style=\"border: 3px solid #ef4444; border-radius: 12px; overflow: hidden; margin-bottom: 24px;\">\n"
        "        <iframe\n"
        "          src={metadata.garminLivetrackUrl}\n"
        "          style=\"width: 100%; height: 600px; border: none;\"\n"
        "          title=\"Garmin LiveTrack Map\"\n"
        "        ></iframe>\n"
        "      </div>\n"
        "      <div class=\"grid grid-cols-2 md:grid-cols-4 gap-4 mb-8\">\n"
        "        <div class=\"bg-white p-5 rounded-2xl border border-slate-100 shadow-sm\">\n"
        "          <span class=\"block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1\">Distance</span>\n"
        "          <strong class=\"text-2xl text-slate-900\">Live</strong>\n"
        "        </div>\n"
        "        <div class=\"bg-white p-5 rounded-2xl border border-slate-100 shadow-sm\">\n"
        "          <span class=\"block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1\">Elevation</span>\n"
        "          <strong class=\"text-2xl text-slate-900\">Live</strong>\n"
        "        </div>\n"
        "        <div class=\"bg-white p-5 rounded-2xl border border-slate-100 shadow-sm\">\n"
        "          <span class=\"block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1\">Moving Time</span>\n"
        "          <strong class=\"text-2xl text-slate-900\">Live</strong>\n"
        "        </div>\n"
        "        <div class=\"bg-white p-5 rounded-2xl border border-slate-100 shadow-sm\">\n"
        "          <span class=\"block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1\">Avg Speed</span>\n"
        "          <strong class=\"text-2xl text-slate-900\">Live</strong>\n"
        "        </div>\n"
        "      </div>\n"
        "      <p class=\"text-sm text-slate-500 italic\">\n"
        "        📍 Live tracking data is provided by Garmin LiveTrack. Statistics update automatically during the activity.\n"
        "      </p>\n"
        "    </section>\n"
        "  )}\n"
        "  <Map payload={trackerPayload} fullscreenUrl={fullscreenMapUrl} />\n"
        f"  {markup}\n"
        "</CollectionPage>\n"
    )
