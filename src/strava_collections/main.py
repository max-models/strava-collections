import argparse
import glob
import os
import re
import subprocess
import sys
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


def parse_single_strava_id(activity_id: str) -> tuple[int, bool]:
    normalized = activity_id.replace("https://www.strava.com/activities/", "")

    if normalized.lower().endswith("f"):
        return (int(normalized[:-1]), True)
    return (int(normalized), False)


def parse_activity_inputs(activities: list[str | dict]) -> list[dict]:
    parsed = []
    for item in activities:
        if isinstance(item, str):
            parsed.append({"strava_id": parse_single_strava_id(item)})
        elif isinstance(item, dict):
            # Map various ID keys to our internal strava_id
            sid = item.get("stravaActivityId") or item.get("id")
            if sid:
                item["strava_id"] = parse_single_strava_id(str(sid))
            parsed.append(item)
    return parsed


def resolve_output_directory(
    args, yaml_output_dir: str | None = None
) -> tuple[Path, Path | None]:
    if args.output:
        site_root = Path(args.output).resolve()
        ensure_site_template(site_root)
        return site_root / "source", site_root

    if yaml_output_dir is not None:
        output_dir = Path(yaml_output_dir).resolve()
        if output_dir.name == "source":
            site_root = output_dir.parent
            ensure_site_template(site_root)
            return output_dir, site_root
        return output_dir, None

    site_root = Path("docs").resolve()
    ensure_site_template(site_root)
    return site_root / "source", site_root


def print_site_instructions(site_root: Path) -> None:
    astro_dir = site_root / "astro"
    print("")
    print(f"Standalone site ready at: {site_root}")
    print("Next steps:")
    print(f"  cd {astro_dir}")
    print("  npm ci")
    print("  npm run dev")
    print("  npm run build:from-generated")


def generate_collection(
    *,
    collection_name: str,
    activities: list[str | dict],
    output_dir: Path,
    fallback_static_dir: Path | None,
    args,
    places: list[dict] | None = None,
    verbose: bool = False,
    description: str | None = None,
    route_gpx_file: str | list[str] | None = None,
    garmin_livetrack_url: str | None = None,
) -> None:
    collection_filename = "collection-" + collection_name.lower().replace(" ", "-")
    parsed_activities = parse_activity_inputs(activities)

    collection = StravaCollection(
        name=collection_name,
        activities=parsed_activities,
        force_update=args.force_update,
        verbose=verbose,
        description=description,
        route_gpx_file=route_gpx_file,
        garmin_livetrack_url=garmin_livetrack_url,
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # Sync GPX files
    import shutil

    gpx_to_sync = []
    if isinstance(route_gpx_file, str):
        gpx_to_sync.append(route_gpx_file)
    elif isinstance(route_gpx_file, list):
        gpx_to_sync.extend(route_gpx_file)

    for activity in parsed_activities:
        act_gpx = activity.get("routeGpxFile")
        if isinstance(act_gpx, str):
            gpx_to_sync.append(act_gpx)
        elif isinstance(act_gpx, list):
            gpx_to_sync.extend(act_gpx)

    for gf in gpx_to_sync:
        if os.path.exists(gf):
            dest = output_dir / gf
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(gf, dest)
            if verbose:
                print(f"Synced GPX asset: {gf}")

    path_static = output_dir / "_static"
    path_static.mkdir(parents=True, exist_ok=True)

    mapfig_name = f"{collection_filename}-map.html"
    map_path = path_static / mapfig_name
    map_full_name = f"{collection_filename}-map-fullscreen.html"
    map_full_path = path_static / map_full_name
    map_asset_paths = [
        map_path,
        map_full_path,
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
                    path_static
                    / f"activity-{activity.activity_id}.{elevation_extension}"
                ),
                backend=args.backend,
                verbose=verbose,
            )

    collection.plot_elevation(filepath=str(elev_path), backend=args.backend)

    # Export GPX assets for each activity
    collection.generate_gpx_assets(path_static, verbose=verbose)

    # We still plot the map as a PNG for thumbnails/socials
    collection.plot_map(
        filepath=str(map_path.with_suffix(".png")),
        linewidths=[16, 8],
        height=500,
        width_to_height=1.0,
        places=places,
        verbose=verbose,
    )
    collection.plot_map(
        filepath=str(path_static / f"{collection_filename}-map-thick.png"),
        linewidths=[32, 16],
        height=500,
        width_to_height=1.0,
        places=places,
        verbose=verbose,
    )

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


def generate_collection_from_yaml(
    input_path: str, args, verbose: bool = False
) -> Path | None:
    with open(input_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    output_dir, site_root = resolve_output_directory(args, data.get("output_dir"))
    generate_collection(
        collection_name=data["collection_name"],
        activities=data.get("activities") or data.get("activity_ids", []),
        output_dir=output_dir,
        fallback_static_dir=Path(data.get("output_dir", ".")).resolve() / "_static",
        args=args,
        places=data.get("places"),
        verbose=verbose,
        description=data.get("description"),
        route_gpx_file=data.get("routeGpxFile"),
        garmin_livetrack_url=data.get("garminLivetrackUrl"),
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

    parser.add_argument(
        "--download",
        action="store_true",
        help="Download Strava activity streams to JSON",
    )

    parser.add_argument(
        "--serve",
        action="store_true",
        help="Install dependencies and start the development server",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    if args.download:
        import json
        from pathlib import Path

        from strava_collections.activity import StravaActivity

        for aid in args.ids:
            act = StravaActivity(int(aid))
            stream = act._activity_stream
            data = {}
            for k, v in stream.items():
                data[k] = v.data
            out_path = Path("docs/source") / f"strava_{aid}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w") as f:
                json.dump(data, f)
            print(f"Downloaded {aid} to {out_path}")
        return

    site_root: Path | None = None
    if args.input:
        input_paths = resolve_input_paths(args.input)
        for input_path in input_paths:
            site_root = generate_collection_from_yaml(input_path=input_path, args=args)
    else:
        output_dir, site_root = resolve_output_directory(args)
        generate_collection(
            collection_name=args.collection,
            activities=args.ids,
            output_dir=output_dir,
            fallback_static_dir=None,
            args=args,
        )
    if args.verbose:
        print(f"Generated collection with activities: {args.ids}")
    if site_root is not None:
        sync_site(site_root)
        import os
        import shutil

        if os.path.exists("live-tracking.yaml"):
            shutil.copy(
                "live-tracking.yaml", site_root / "source" / "live-tracking.yaml"
            )
        print_site_instructions(site_root)

    if args.serve and site_root is not None:
        astro_dir = site_root / "astro"
        print(f"\n🚀 Starting development server in {astro_dir}...")
        try:
            # Install dependencies
            subprocess.run(["npm", "ci"], cwd=astro_dir, check=True)
            # Start dev server
            subprocess.run(["npm", "run", "dev"], cwd=astro_dir, check=True)
        except KeyboardInterrupt:
            print("\n👋 Server stopped.")
        except Exception as e:
            print(f"❌ Error starting server: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
