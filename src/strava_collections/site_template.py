import shutil
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path


@dataclass(frozen=True)
class SitePaths:
    site_root: Path
    source_dir: Path
    astro_dir: Path
    page_dir: Path
    generated_dir: Path
    manifest_path: Path
    public_static_dir: Path


def build_site_paths(site_root: str | Path) -> SitePaths:
    root = Path(site_root).resolve()
    astro_dir = root / "astro"
    generated_dir = astro_dir / "src" / "generated"
    return SitePaths(
        site_root=root,
        source_dir=root / "source",
        astro_dir=astro_dir,
        page_dir=astro_dir / "src" / "pages" / "collections",
        generated_dir=generated_dir,
        manifest_path=generated_dir / "collections.ts",
        public_static_dir=astro_dir / "public" / "_static",
    )


def ensure_site_template(site_root: str | Path) -> SitePaths:
    paths = build_site_paths(site_root)
    template_root = files("strava_collections").joinpath("site_template").joinpath("astro")

    with as_file(template_root) as template_dir:
        shutil.copytree(template_dir, paths.astro_dir, dirs_exist_ok=True)

    paths.source_dir.mkdir(parents=True, exist_ok=True)
    (paths.source_dir / "_static").mkdir(parents=True, exist_ok=True)
    paths.page_dir.mkdir(parents=True, exist_ok=True)
    paths.generated_dir.mkdir(parents=True, exist_ok=True)
    paths.public_static_dir.mkdir(parents=True, exist_ok=True)

    manifest_stub = (
        "export type CollectionSummary = {\n"
        "  title: string;\n"
        "  slug: string;\n"
        "  fileSlug: string;\n"
        "};\n\n"
        "export const collections: CollectionSummary[] = [];\n"
    )
    if not paths.manifest_path.exists():
        paths.manifest_path.write_text(manifest_stub, encoding="utf-8")

    return paths
