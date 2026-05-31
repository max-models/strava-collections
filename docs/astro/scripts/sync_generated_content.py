import json
import os
import re
import shutil
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[3]
SPHINX_SOURCE = ROOT / "docs" / "source"
ASTRO_ROOT = ROOT / "docs" / "astro"
CONTENT_DIR = ASTRO_ROOT / "src" / "content" / "collections"
PAGE_DIR = ASTRO_ROOT / "src" / "pages" / "collections"
GENERATED_DIR = ASTRO_ROOT / "src" / "generated"
MANIFEST_PATH = GENERATED_DIR / "collections.ts"
PUBLIC_STATIC_DIR = ASTRO_ROOT / "public" / "_static"
ASTRO_BASE_PATH = os.getenv("ASTRO_BASE_PATH", "/strava-collections/").strip()
if not ASTRO_BASE_PATH.endswith("/"):
    ASTRO_BASE_PATH = f"{ASTRO_BASE_PATH}/"


FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
LEGACY_LIGHTBOX_RE = re.compile(
    r'\n*<div id="lightbox" class="lightbox">.*?</script>\s*$',
    re.DOTALL,
)
GALLERY_BLOCK_RE = re.compile(r'<div class="gallery">(.*?)</div>', re.DOTALL)
GALLERY_IMAGE_RE = re.compile(r'<img\b[^>]*\bclass="[^"]*\blightbox-trigger\b[^"]*"[^>]*>')


def strip_frontmatter(markdown: str) -> str:
    return FRONTMATTER_RE.sub("", markdown, count=1)


def strip_legacy_lightbox(markdown: str) -> str:
    return LEGACY_LIGHTBOX_RE.sub("\n", markdown)


def add_glightbox_to_galleries(markdown: str) -> str:
    def replace_gallery_block(match: re.Match[str]) -> str:
        gallery_index = replace_gallery_block.counter
        replace_gallery_block.counter += 1

        def replace_img(img_match: re.Match[str]) -> str:
            img_tag = img_match.group(0)
            src_match = re.search(r'src="([^"]+)"', img_tag)
            if src_match is None:
                return img_tag
            src = src_match.group(1)
            return (
                f'<a href="{src}" class="glightbox" '
                f'data-gallery="collection-gallery-{gallery_index}">{img_tag}</a>'
            )

        return (
            '<div class="gallery">'
            + GALLERY_IMAGE_RE.sub(replace_img, match.group(1))
            + "</div>"
        )

    replace_gallery_block.counter = 0
    return GALLERY_BLOCK_RE.sub(replace_gallery_block, markdown)


def route_slug_from_filename(filename: str) -> str:
    return filename.removeprefix("collection-")


def title_from_markdown(markdown: str) -> str:
    match = re.search(r"^#\s+(.+)$", strip_frontmatter(markdown), re.MULTILINE)
    if not match:
        raise ValueError("Collection markdown is missing an H1 title")
    return match.group(1).strip()


def upgrade_elevation_embeds(markdown: str) -> str:
    def replace_image(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        asset_name = match.group("asset_name")
        html_asset = f"{asset_name}.html"
        if not (SPHINX_SOURCE / "_static" / html_asset).exists():
            return match.group(0)
        return (
            '<div style="position: relative; width: 100%; height: 220px; aspect-ratio: 3 / 1;">\n'
            f'  <iframe src="{prefix}{html_asset}" style="width:100%; height:100%; border:none; border-radius: 12px;"></iframe>\n'
            "</div>"
        )

    pattern = re.compile(
        r'<img\s+src="(?P<prefix>/?_static/)(?P<asset_name>(?:collection-.*?-elev|activity-\d+))\.png"[^>]*>',
        re.IGNORECASE,
    )
    return pattern.sub(replace_image, markdown)


def convert_markdown(markdown: str) -> str:
    body = strip_frontmatter(markdown)
    body = strip_legacy_lightbox(body)
    body = upgrade_elevation_embeds(body)
    body = add_glightbox_to_galleries(body)
    body = body.replace('src="_static/', f'src="{ASTRO_BASE_PATH}_static/')
    body = body.replace('href="_static/', f'href="{ASTRO_BASE_PATH}_static/')
    body = body.replace('src="/_static/', f'src="{ASTRO_BASE_PATH}_static/')
    body = body.replace('href="/_static/', f'href="{ASTRO_BASE_PATH}_static/')
    return body


def markdown_to_html(markdown_text: str) -> str:
    return markdown.markdown(markdown_text, extensions=["tables"])


def render_collection_page(title: str, body_html: str) -> str:
    return (
        "---\n"
        "import CollectionPage from '../../components/CollectionPage.astro';\n\n"
        f"const title = {json.dumps(title)};\n"
        f"const bodyHtml = {json.dumps(body_html)};\n"
        "---\n\n"
        "<CollectionPage title={title} bodyHtml={bodyHtml} />\n"
    )


def render_collections_manifest(collections: list[dict[str, str]]) -> str:
    return (
        "export type CollectionSummary = {\n"
        "  title: string;\n"
        "  slug: string;\n"
        "  fileSlug: string;\n"
        "};\n\n"
        f"export const collections: CollectionSummary[] = {json.dumps(collections, indent=2)};\n"
    )


def sync_collections() -> None:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    for old_file in CONTENT_DIR.glob("collection-*.md"):
        old_file.unlink()

    for old_file in PAGE_DIR.glob("*.astro"):
        old_file.unlink()

    manifest = []
    for source_file in sorted(SPHINX_SOURCE.glob("collection-*.md")):
        source_text = source_file.read_text(encoding="utf-8")
        title = title_from_markdown(source_text)
        file_slug = source_file.stem
        route_slug = route_slug_from_filename(file_slug)
        body_html = markdown_to_html(convert_markdown(source_text))

        target_file = PAGE_DIR / f"{route_slug}.astro"
        target_file.write_text(
            render_collection_page(title=title, body_html=body_html),
            encoding="utf-8",
        )
        manifest.append(
            {
                "title": title,
                "slug": route_slug,
                "fileSlug": file_slug,
            }
        )
        print(f"Synced collection page: {target_file.relative_to(ROOT)}")

    MANIFEST_PATH.write_text(
        render_collections_manifest(manifest),
        encoding="utf-8",
    )
    print(f"Synced collection manifest: {MANIFEST_PATH.relative_to(ROOT)}")


def sync_static() -> None:
    source_static = SPHINX_SOURCE / "_static"
    if PUBLIC_STATIC_DIR.exists():
        shutil.rmtree(PUBLIC_STATIC_DIR)
    shutil.copytree(source_static, PUBLIC_STATIC_DIR)

    for map_image in PUBLIC_STATIC_DIR.glob("collection-*-map.png"):
        thick_image = map_image.with_name(
            map_image.name.replace("-map.png", "-map-thick.png")
        )
        if not thick_image.exists():
            shutil.copy2(map_image, thick_image)
            print(f"Created missing hover image: {thick_image.relative_to(ROOT)}")

    print(f"Synced static assets: {PUBLIC_STATIC_DIR.relative_to(ROOT)}")


def main() -> None:
    sync_collections()
    sync_static()


if __name__ == "__main__":
    main()
