import argparse
import glob
from pathlib import Path

import yaml

from strava_collections.collection import (
    StravaCollection,
    mapbox_token,
    mapbox_token_help,
)
from strava_collections.site_sync import sync_site
from strava_collections.site_template import ensure_site_template


def elevation_extension_for_backend(backend: str) -> str:
    if backend == "plotly":
        return "html"
    if backend in {"tikzfigure", "matplotlib"}:
        return "png"
    raise ValueError(f"Unsupported backend: {backend}")


def resolve_input_paths(input_patterns: list[str]) -> list[str]:
    resolved_paths: list[str] = []

    for pattern in input_patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            resolved_paths.extend(matches)
            continue

        if glob.has_magic(pattern):
            raise FileNotFoundError(f"No input files matched pattern: {pattern}")

        resolved_paths.append(pattern)

    return resolved_paths


def parse_activity_ids(activity_ids: list[str]) -> list[tuple[int, bool]]:
    activity_ids_flip = []
    for activity_id in activity_ids:
        normalized = activity_id.replace("https://www.strava.com/activities/", "")

        if normalized.lower().endswith("f"):
            flip = True
            parsed_id = int(normalized[:-1])
        else:
            flip = False
            parsed_id = int(normalized)
        activity_ids_flip.append((parsed_id, flip))

    return activity_ids_flip


def resolve_output_directory(args, yaml_output_dir: str | None = None) -> tuple[Path, Path | None]:
    if args.output:
        site_root = Path(args.output).resolve()
        ensure_site_template(site_root)
        return site_root / "source", site_root

    if yaml_output_dir is not None:
        return Path(yaml_output_dir).resolve(), None

    return Path("./").resolve(), None


def generate_collection(
    *,
    collection_name: str,
    activity_ids: list[str],
    output_dir: Path,
    fallback_static_dir: Path | None,
    args,
) -> None:
    collection_filename = "collection-" + collection_name.lower().replace(" ", "-")
    activity_ids_flip = parse_activity_ids(activity_ids)

    collection = StravaCollection(
        name=collection_name,
        activity_ids=activity_ids_flip,
        force_update=args.force_update,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    path_static = output_dir / "_static"
    path_static.mkdir(parents=True, exist_ok=True)

    mapfig_name = f"{collection_filename}-map.html"
    map_path = path_static / mapfig_name
    map_asset_paths = [
        map_path,
        map_path.with_suffix(".png"),
        path_static / f"{collection_filename}-map-thick.png",
    ]

    elevation_extension = elevation_extension_for_backend(args.backend)
    elevfig_name = f"{collection_filename}-elev.{elevation_extension}"
    elev_path = path_static / elevfig_name

    path_collection_astro = output_dir / f"{collection_filename}.astro"
    legacy_markdown_path = output_dir / f"{collection_filename}.md"

    if args.include_activity_elevation:
        for activity in collection.activities:
            activity.plot_elevation(
                filepath=str(
                    path_static / f"activity-{activity.activity_id}.{elevation_extension}"
                ),
                backend=args.backend,
            )

    collection.plot_elevation(filepath=str(elev_path), backend=args.backend)

    if mapbox_token:
        collection.plot_map(
            filepath=str(map_path),
            linewidths=[8, 2],
            width_to_height=3.0,
        )
        collection.plot_map(
            filepath=str(map_path.with_suffix(".png")),
            linewidths=[16, 8],
            height=500,
            width_to_height=1.0,
        )
        collection.plot_map(
            filepath=str(path_static / f"{collection_filename}-map-thick.png"),
            linewidths=[32, 16],
            height=500,
            width_to_height=1.0,
        )
    elif fallback_static_dir is not None and all(
        (fallback_static_dir / path.name).exists() for path in map_asset_paths
    ):
        for map_asset_path in map_asset_paths:
            fallback_asset = fallback_static_dir / map_asset_path.name
            map_asset_path.write_bytes(fallback_asset.read_bytes())
        print(
            "MAPBOX_TOKEN is not set; copied existing map assets from "
            f"{fallback_static_dir}."
        )
    elif all(path.exists() for path in map_asset_paths):
        print(
            "MAPBOX_TOKEN is not set; reusing existing map assets in "
            f"{path_static}."
        )
    else:
        raise RuntimeError(mapbox_token_help)

    collection.generate_astro(
        filepath=str(path_collection_astro),
        mapfig_name=mapfig_name,
        elevfig_name=elevfig_name,
        include_activity_elevation=args.include_activity_elevation,
        activity_elevation_extension=elevation_extension,
        prettify=args.prettify,
    )

    if legacy_markdown_path.exists():
        legacy_markdown_path.unlink()
        print(f"Removed legacy markdown page at {legacy_markdown_path}")


def generate_collection_from_yaml(input_path: str, args) -> Path | None:
    with open(input_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    output_dir, site_root = resolve_output_directory(args, data.get("output_dir"))
    generate_collection(
        collection_name=data["collection_name"],
        activity_ids=data["activity_ids"],
        output_dir=output_dir,
        fallback_static_dir=Path(data["output_dir"]).resolve() / "_static",
        args=args,
    )
    return site_root


def main():
    """Main method called from the command line."""
    parser = argparse.ArgumentParser(description="Plot Strava activities.")
    parser.add_argument(
        "ids",
        nargs="*",
        type=str,
        help="Space-separated list of Strava activity IDs, e.g., 123 456 789",
    )

    parser.add_argument(
        "-i",
        "--input",
        nargs="+",
        default=None,
        help="One or more input yaml files or glob patterns (default: None)",
    )

    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help=(
            "Site output directory. When set, a self-contained Astro template is "
            "copied to <output>/astro and generated collection data is written to "
            "<output>/source."
        ),
    )

    parser.add_argument(
        "-c",
        "--collection",
        default="Example collection",
        help="Collection name, default: Example collection",
    )

    parser.add_argument(
        "-b",
        "--backend",
        default="plotly",
        choices=["plotly", "tikzfigure", "matplotlib"],
    )

    parser.add_argument(
        "-f",
        "--force-update",
        action="store_true",
        help="Force update strava activities",
    )

    parser.add_argument(
        "-p",
        "--prettify",
        action="store_true",
        help="Prettify generated collection files",
    )
    parser.add_argument(
        "--include-activity-elevation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate and embed each activity elevation plot in the collection page.",
    )

    args = parser.parse_args()

    site_root: Path | None = None
    if args.input:
        input_paths = resolve_input_paths(args.input)
        for input_path in input_paths:
            site_root = generate_collection_from_yaml(input_path=input_path, args=args)
        if site_root is not None:
            sync_site(site_root)
        return

    output_dir, site_root = resolve_output_directory(args)
    generate_collection(
        collection_name=args.collection,
        activity_ids=args.ids,
        output_dir=output_dir,
        fallback_static_dir=None,
        args=args,
    )
    if site_root is not None:
        sync_site(site_root)


if __name__ == "__main__":
    main()
