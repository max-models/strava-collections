import json
import shutil
from pathlib import Path

from strava_collections.astro_page import (
    markdown_to_body_html,
    render_collection_page,
    route_slug_from_filename,
    title_from_astro,
    title_from_markdown,
)
from strava_collections.site_template import SitePaths, build_site_paths


def display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
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


def sync_collections(paths: SitePaths) -> None:
    paths.page_dir.mkdir(parents=True, exist_ok=True)
    paths.generated_dir.mkdir(parents=True, exist_ok=True)

    collection_sources: dict[str, tuple[str, Path]] = {}
    for astro_file in sorted(paths.source_dir.glob("collection-*.astro")):
        collection_sources[astro_file.stem] = ("astro", astro_file)
    for markdown_file in sorted(paths.source_dir.glob("collection-*.md")):
        collection_sources.setdefault(markdown_file.stem, ("markdown", markdown_file))

    manifest = []
    synced_filenames = set()
    asset_dir = paths.source_dir / "_static"
    for file_slug, (source_type, source_file) in sorted(collection_sources.items()):
        route_slug = route_slug_from_filename(file_slug)
        target_filename = f"{route_slug}.astro"
        target_file = paths.page_dir / target_filename
        synced_filenames.add(target_filename)
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
        print(f"Synced collection page: {display_path(target_file, paths.site_root)}")

    # Clean up obsolete pages
    for old_file in paths.page_dir.glob("*.astro"):
        if old_file.name not in synced_filenames:
            old_file.unlink()
            print(f"Removed obsolete collection page: {display_path(old_file, paths.site_root)}")

    paths.manifest_path.write_text(
        render_collections_manifest(manifest),
        encoding="utf-8",
    )
    print(
        f"Synced collection manifest: {display_path(paths.manifest_path, paths.site_root)}"
    )


def sync_static(paths: SitePaths) -> None:
    source_static = paths.source_dir / "_static"
    paths.public_static_dir.mkdir(parents=True, exist_ok=True)

    source_filenames = set()
    for source_file in source_static.iterdir():
        if source_file.is_file():
            source_filenames.add(source_file.name)
            target_file = paths.public_static_dir / source_file.name
            shutil.copy2(source_file, target_file)

    # Handle thick images and collect their names to prevent deletion
    extra_filenames = set()
    for map_image in paths.public_static_dir.glob("collection-*-map.png"):
        thick_name = map_image.name.replace("-map.png", "-map-thick.png")
        thick_image = map_image.with_name(thick_name)
        extra_filenames.add(thick_name)
        if not thick_image.exists():
            shutil.copy2(map_image, thick_image)
            print(
                f"Created missing hover image: {display_path(thick_image, paths.site_root)}"
            )

    # Clean up obsolete assets
    all_valid_filenames = source_filenames | extra_filenames
    for old_file in paths.public_static_dir.iterdir():
        if old_file.is_file() and old_file.name not in all_valid_filenames:
            old_file.unlink()
            print(f"Removed obsolete asset: {display_path(old_file, paths.site_root)}")

    print(
        f"Synced static assets: {display_path(paths.public_static_dir, paths.site_root)}"
    )


def sync_site(site_root: str | Path) -> SitePaths:
    paths = build_site_paths(site_root)
    sync_collections(paths)
    sync_static(paths)
    return paths
