import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path

import yaml

from strava_collections.collection import (
    StravaCollection,
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
        force_update=getattr(args, "force_update", False),
        verbose=verbose,
        description=description,
        route_gpx_file=route_gpx_file,
        garmin_livetrack_url=garmin_livetrack_url,
        places=places,
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

    backend = getattr(args, "backend", "plotly")
    elevation_extension = elevation_extension_for_backend(backend)
    elevfig_name = f"{collection_filename}-elev.{elevation_extension}"
    elev_path = path_static / elevfig_name

    path_collection_astro = output_dir / f"{collection_filename}.astro"
    legacy_markdown_path = output_dir / f"{collection_filename}.md"

    skip_assets = getattr(args, "skip_assets", False)
    skip_pages = getattr(args, "skip_pages", False)

    if not skip_assets:
        if getattr(args, "include_activity_elevation", True):
            for activity in collection.activities:
                activity.plot_elevation(
                    filepath=str(
                        path_static
                        / f"activity-{activity.activity_id}.{elevation_extension}"
                    ),
                    backend=backend,
                    verbose=verbose,
                )

        collection.plot_elevation(filepath=str(elev_path), backend=backend)

        # Export GPX assets for each activity
        collection.generate_gpx_assets(path_static, verbose=verbose)

        # Export map as html
        collection.plot_map(
            filepath=str(map_full_path),
            linewidths=[4, 2],
            height=800,
            width_to_height=1.0,
            places=places,
            verbose=verbose,
        )

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

    if not skip_pages:
        collection.generate_astro(
            filepath=str(path_collection_astro),
            mapfig_name=mapfig_name,
            elevfig_name=elevfig_name,
            include_activity_elevation=getattr(
                args, "include_activity_elevation", True
            ),
            activity_elevation_extension=elevation_extension,
            prettify=getattr(args, "prettify", False),
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

    # Support both "planned_routes" (new) and "routeGpxFile" (legacy) fields
    planned_routes = data.get("planned_routes") or data.get("routeGpxFile")

    generate_collection(
        collection_name=data["collection_name"],
        activities=data.get("activities") or data.get("activity_ids", []),
        output_dir=output_dir,
        fallback_static_dir=Path(data.get("output_dir", ".")).resolve() / "_static",
        args=args,
        places=data.get("places"),
        verbose=verbose,
        description=data.get("description"),
        route_gpx_file=planned_routes,
        garmin_livetrack_url=data.get("garmin_livetrack_url")
        or data.get("garminLivetrackUrl"),
    )
    return site_root


def main():
    """Main method called from the command line."""
    parser = argparse.ArgumentParser(
        description="Strava Collections: Analyze, build and serve your adventures.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Command: build
    build_parser = subparsers.add_parser(
        "build", help="Process collections and generate pages/assets"
    )
    build_parser.add_argument(
        "ids",
        nargs="*",
        type=str,
        help="Space-separated list of Strava activity IDs",
    )
    build_parser.add_argument(
        "-i",
        "--input",
        nargs="+",
        help="One or more input YAML files or glob patterns",
    )
    build_parser.add_argument(
        "-c",
        "--collection",
        default="Example collection",
        help="Collection name",
    )
    build_parser.add_argument(
        "-o",
        "--output",
        help="Site output directory (overrides YAML output_dir)",
    )
    build_parser.add_argument(
        "-f",
        "--force-update",
        action="store_true",
        help="Force update strava activities",
    )
    build_parser.add_argument(
        "-b",
        "--backend",
        default="plotly",
        choices=["plotly", "tikzfigure", "matplotlib"],
        help="Elevation plotting backend",
    )
    build_parser.add_argument(
        "-p",
        "--prettify",
        action="store_true",
        help="Prettify generated collection files",
    )
    build_parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="Skip generating figures and GPX assets",
    )
    build_parser.add_argument(
        "--skip-pages",
        action="store_true",
        help="Skip generating Astro pages",
    )
    build_parser.add_argument(
        "--no-elevation",
        dest="include_activity_elevation",
        action="store_false",
        help="Disable individual activity elevation plots",
    )
    build_parser.add_argument(
        "--serve",
        action="store_true",
        help="Serve the site after building",
    )
    build_parser.add_argument(
        "--host",
        action="store_true",
        help="Expose server to host",
    )
    build_parser.set_defaults(include_activity_elevation=True)

    # Command: analyze
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze collections and show statistics without building"
    )
    analyze_parser.add_argument(
        "-i",
        "--input",
        nargs="+",
        required=True,
        help="One or more input YAML files or glob patterns",
    )
    analyze_parser.add_argument(
        "-f",
        "--force-update",
        action="store_true",
        help="Force update strava activities",
    )

    # Command: site
    site_parser = subparsers.add_parser("site", help="Manage the Astro website")
    site_subparsers = site_parser.add_subparsers(
        dest="site_command", help="Site sub-command"
    )

    site_init_parser = site_subparsers.add_parser(
        "init", help="Initialize/update the Astro template"
    )
    site_init_parser.add_argument("-o", "--output", help="Site directory")

    site_sync_parser = site_subparsers.add_parser(
        "sync", help="Sync generated source files to the Astro site"
    )
    site_sync_parser.add_argument("-o", "--output", help="Site directory")

    site_build_parser = site_subparsers.add_parser(
        "build", help="Run npm build for the Astro site"
    )
    site_build_parser.add_argument("-o", "--output", help="Site directory")

    # Command: serve
    serve_parser = subparsers.add_parser("serve", help="Run the development server")
    serve_parser.add_argument("-o", "--output", help="Site directory")
    serve_parser.add_argument(
        "--host", action="store_true", help="Expose server to host"
    )

    # Command: activities
    act_parser = subparsers.add_parser("activities", help="Individual activity tasks")
    act_parser.add_argument("ids", nargs="+", help="Strava activity IDs")
    act_parser.add_argument(
        "--download", action="store_true", help="Download activity streams to JSON"
    )

    # LEGACY / Shortcut handling
    if (
        len(sys.argv) > 1
        and sys.argv[1] not in subparsers.choices
        and sys.argv[1] not in ["-h", "--help", "-v", "--verbose"]
    ):
        if any(
            arg in sys.argv
            for arg in ["-i", "--input", "-o", "--output", "-c", "--collection"]
        ):
            sys.argv.insert(1, "build")
        elif sys.argv[1].isdigit():
            # If we have other build-related flags but no subcommand, it's a build
            if any(
                arg in sys.argv
                for arg in [
                    "-b",
                    "--backend",
                    "-f",
                    "--force-update",
                    "-p",
                    "--prettify",
                ]
            ):
                sys.argv.insert(1, "build")
            else:
                sys.argv.insert(1, "activities")

    args = parser.parse_args()

    if getattr(args, "command", None) == "activities":
        if args.download:
            import json

            from strava_collections.activity import StravaActivity

            for aid in args.ids:
                act = StravaActivity(int(aid))
                stream = act._activity_stream
                data = {k: v.data for k, v in stream.items()}
                out_path = Path("docs/source") / f"strava_{aid}.json"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "w") as f:
                    json.dump(data, f)
                print(f"Downloaded {aid} to {out_path}")
        return

    if getattr(args, "command", None) == "analyze":
        input_paths = resolve_input_paths(args.input)
        for input_path in input_paths:
            with open(input_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            StravaCollection(
                name=data["collection_name"],
                activities=data.get("activities") or data.get("activity_ids", []),
                force_update=args.force_update,
                verbose=args.verbose,
                description=data.get("description"),
                places=data.get("places"),
            )
        return

    if getattr(args, "command", None) == "site":
        site_root = (
            Path(args.output).resolve() if args.output else Path("docs").resolve()
        )
        if args.site_command == "init":
            print(f"Initializing/Updating site at: {site_root}")
            ensure_site_template(site_root)
        elif args.site_command == "sync":
            print(f"Syncing site at: {site_root}")
            sync_site(site_root)
        elif args.site_command == "build":
            astro_dir = site_root / "astro"
            print(f"Building site at: {astro_dir}")
            subprocess.run(
                ["npm", "run", "build:from-generated"], cwd=astro_dir, check=True
            )
        return

    site_root: Path | None = None
    if getattr(args, "command", None) == "build":
        if args.input:
            input_paths = resolve_input_paths(args.input)
            for input_path in input_paths:
                site_root = generate_collection_from_yaml(
                    input_path=input_path, args=args, verbose=args.verbose
                )
        elif args.ids:
            output_dir, site_root = resolve_output_directory(args)
            generate_collection(
                collection_name=args.collection,
                activities=args.ids,
                output_dir=output_dir,
                fallback_static_dir=None,
                args=args,
                verbose=args.verbose,
            )

        if site_root is None:
            print("No site generated since no output directory was specified.")
            return

        sync_site(site_root)
        if os.path.exists("live-tracking.yaml"):
            import shutil

            shutil.copy(
                "live-tracking.yaml", site_root / "source" / "live-tracking.yaml"
            )
        print_site_instructions(site_root)

        if getattr(args, "serve", False):
            astro_dir = site_root / "astro"
            print(f"\n🚀 Starting development server in {astro_dir}...")
            try:
                subprocess.run(["npm", "ci"], cwd=astro_dir, check=True)
                npm_command = ["npm", "run", "dev"]
                if args.host:
                    npm_command.extend(["--", "--host"])
                subprocess.run(npm_command, cwd=astro_dir, check=True)
            except KeyboardInterrupt:
                print("\n👋 Server stopped.")
            except Exception as e:
                print(f"❌ Error starting server: {e}")
                sys.exit(1)

    if getattr(args, "command", None) == "serve":
        site_root = (
            Path(args.output).resolve() if args.output else Path("docs").resolve()
        )
        astro_dir = site_root / "astro"
        print(f"\n🚀 Starting development server in {astro_dir}...")
        try:
            subprocess.run(["npm", "ci"], cwd=astro_dir, check=True)
            npm_command = ["npm", "run", "dev"]
            if args.host:
                npm_command.extend(["--", "--host"])
            subprocess.run(npm_command, cwd=astro_dir, check=True)
        except KeyboardInterrupt:
            print("\n👋 Server stopped.")
        except Exception as e:
            print(f"❌ Error starting server: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
