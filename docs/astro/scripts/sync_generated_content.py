import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from strava_collections.astro_page import (  # noqa: E402
    markdown_to_body_html,
    render_collection_page,
    route_slug_from_filename,
    title_from_astro,
    title_from_markdown,
)

SPHINX_SOURCE = ROOT / "docs" / "source"
PAGE_DIR = ROOT / "docs" / "astro" / "src" / "pages" / "collections"
GENERATED_DIR = ROOT / "docs" / "astro" / "src" / "generated"
MANIFEST_PATH = GENERATED_DIR / "collections.ts"
PUBLIC_STATIC_DIR = ROOT / "docs" / "astro" / "public" / "_static"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


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
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    for old_file in PAGE_DIR.glob("*.astro"):
        old_file.unlink()

    collection_sources: dict[str, tuple[str, Path]] = {}
    for astro_file in sorted(SPHINX_SOURCE.glob("collection-*.astro")):
        collection_sources[astro_file.stem] = ("astro", astro_file)
    for markdown_file in sorted(SPHINX_SOURCE.glob("collection-*.md")):
        collection_sources.setdefault(markdown_file.stem, ("markdown", markdown_file))

    manifest = []
    asset_dir = SPHINX_SOURCE / "_static"
    for file_slug, (source_type, source_file) in sorted(collection_sources.items()):
        route_slug = route_slug_from_filename(file_slug)
        target_file = PAGE_DIR / f"{route_slug}.astro"
        source_text = source_file.read_text(encoding="utf-8")

        if source_type == "astro":
            title = title_from_astro(source_text)
            target_file.write_text(source_text, encoding="utf-8")
        else:
            title = title_from_markdown(source_text)
            body_html = markdown_to_body_html(source_text, asset_dir=asset_dir)
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
        print(f"Synced collection page: {display_path(target_file)}")

    MANIFEST_PATH.write_text(
        render_collections_manifest(manifest),
        encoding="utf-8",
    )
    print(f"Synced collection manifest: {display_path(MANIFEST_PATH)}")


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
            print(f"Created missing hover image: {display_path(thick_image)}")

    print(f"Synced static assets: {display_path(PUBLIC_STATIC_DIR)}")


def main() -> None:
    sync_collections()
    sync_static()


if __name__ == "__main__":
    main()
