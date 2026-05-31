import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPHINX_SOURCE = ROOT / "docs" / "source"
ASTRO_ROOT = ROOT / "docs" / "astro"
CONTENT_DIR = ASTRO_ROOT / "src" / "content" / "collections"
PUBLIC_STATIC_DIR = ASTRO_ROOT / "public" / "_static"
ASTRO_BASE_PATH = os.getenv("ASTRO_BASE_PATH", "/strava-collections/").strip()
if not ASTRO_BASE_PATH.endswith("/"):
    ASTRO_BASE_PATH = f"{ASTRO_BASE_PATH}/"


def title_from_markdown(markdown: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    if not match:
        raise ValueError("Collection markdown is missing an H1 title")
    return match.group(1).strip()


def convert_markdown(markdown: str) -> str:
    title = title_from_markdown(markdown)
    body = markdown.replace('src="_static/', f'src="{ASTRO_BASE_PATH}_static/')
    body = body.replace('href="_static/', f'href="{ASTRO_BASE_PATH}_static/')
    body = body.replace('src="/_static/', f'src="{ASTRO_BASE_PATH}_static/')
    body = body.replace('href="/_static/', f'href="{ASTRO_BASE_PATH}_static/')
    return f"---\ntitle: {json.dumps(title)}\n---\n{body}"


def sync_collections() -> None:
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    for old_file in CONTENT_DIR.glob("collection-*.md"):
        old_file.unlink()

    for source_file in sorted(SPHINX_SOURCE.glob("collection-*.md")):
        target_file = CONTENT_DIR / source_file.name
        target_file.write_text(
            convert_markdown(source_file.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        print(f"Synced collection content: {target_file.relative_to(ROOT)}")


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
