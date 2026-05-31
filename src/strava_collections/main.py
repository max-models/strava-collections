import argparse
import glob
import os

import yaml

from strava_collections.collection import (
    StravaCollection,
    mapbox_token,
    mapbox_token_help,
)


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


def generate_collection_from_yaml(input_path: str, args) -> None:
    with open(input_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        print(data)
        activity_ids = data["activity_ids"]
        output = data["output_dir"]
        collection_name = data["collection_name"]

    collection_filename = "collection-" + collection_name.lower().replace(" ", "-")

    # Parse activity IDs into integers
    activity_ids_flip = []
    for id in activity_ids:
        id = id.replace("https://www.strava.com/activities/", "")

        if id.lower().endswith("f"):
            flip = True
            id = int(id[:-1])
        else:
            flip = False
            id = int(id)
        activity_ids_flip.append((id, flip))

    # Create collection and plot
    collection = StravaCollection(
        name=collection_name,
        activity_ids=activity_ids_flip,
        force_update=args.force_update,
    )

    # Set filenames
    path_static = os.path.join(output, "_static")
    mapfig_name = f"{collection_filename}-map.html"
    map_path = os.path.join(path_static, mapfig_name)
    map_asset_paths = [
        map_path,
        map_path.replace(".html", ".png"),
        map_path.replace(".html", "-thick.png"),
    ]

    elevation_extension = elevation_extension_for_backend(args.backend)
    elevfig_name = f"{collection_filename}-elev.{elevation_extension}"
    elev_path = os.path.join(path_static, elevfig_name)

    path_collection_astro = os.path.join(output, f"{collection_filename}.astro")
    legacy_markdown_path = os.path.join(output, f"{collection_filename}.md")

    if args.include_activity_elevation:
        for activity in collection.activities:
            activity.plot_elevation(
                filepath=os.path.join(
                    path_static,
                    f"activity-{activity.activity_id}.{elevation_extension}",
                ),
                backend=args.backend,
            )

    collection.plot_elevation(filepath=elev_path, backend=args.backend)

    if mapbox_token:
        collection.plot_map(
            filepath=map_path,
            linewidths=[8, 2],
            width_to_height=3.0,
        )
        collection.plot_map(
            filepath=map_path.replace(".html", ".png"),
            linewidths=[16, 8],
            height=500,
            width_to_height=1.0,
        )
        collection.plot_map(
            filepath=map_path.replace(".html", "-thick.png"),
            linewidths=[32, 16],
            height=500,
            width_to_height=1.0,
        )
    elif all(os.path.exists(path) for path in map_asset_paths):
        print(
            "MAPBOX_TOKEN is not set; reusing existing map assets in "
            f"{path_static}."
        )
    else:
        raise RuntimeError(mapbox_token_help)

    collection.generate_astro(
        filepath=path_collection_astro,
        mapfig_name=mapfig_name,
        elevfig_name=elevfig_name,
        include_activity_elevation=args.include_activity_elevation,
        activity_elevation_extension=elevation_extension,
        prettify=args.prettify,
    )

    if os.path.exists(legacy_markdown_path):
        os.remove(legacy_markdown_path)
        print(f"Removed legacy markdown page at {legacy_markdown_path}")


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
        default="./",
        help="Output directory (default: ./)",
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

    if args.input:
        input_paths = resolve_input_paths(args.input)
        for input_path in input_paths:
            generate_collection_from_yaml(input_path=input_path, args=args)
        return
    else:
        activity_ids = args.ids
        output = args.output
        collection_name = args.collection

    collection_filename = "collection-" + collection_name.lower().replace(" ", "-")

    # Parse activity IDs into integers
    activity_ids_flip = []
    for id in activity_ids:
        id = id.replace("https://www.strava.com/activities/", "")

        if id.lower().endswith("f"):
            flip = True
            id = int(id[:-1])
        else:
            flip = False
            id = int(id)
        activity_ids_flip.append((id, flip))

    # Create collection and plot
    collection = StravaCollection(
        name=collection_name,
        activity_ids=activity_ids_flip,
        force_update=args.force_update,
    )

    # print(
    #     collection.to_yaml(
    #         output_dir=output,
    #         # filename=args.input,
    #     )
    # )

    # Set filenames
    path_static = os.path.join(output, "_static")
    mapfig_name = f"{collection_filename}-map.html"
    map_path = os.path.join(path_static, mapfig_name)
    map_asset_paths = [
        map_path,
        map_path.replace(".html", ".png"),
        map_path.replace(".html", "-thick.png"),
    ]

    elevation_extension = elevation_extension_for_backend(args.backend)
    elevfig_name = f"{collection_filename}-elev.{elevation_extension}"
    elev_path = os.path.join(path_static, elevfig_name)

    path_collection_astro = os.path.join(output, f"{collection_filename}.astro")
    legacy_markdown_path = os.path.join(output, f"{collection_filename}.md")

    if args.include_activity_elevation:
        for activity in collection.activities:
            activity.plot_elevation(
                filepath=os.path.join(
                    path_static,
                    f"activity-{activity.activity_id}.{elevation_extension}",
                ),
                backend=args.backend,
            )

    plot_elevation = True
    if plot_elevation:
        collection.plot_elevation(filepath=elev_path, backend=args.backend)

    # Plot figures
    plot_map = True
    if plot_map:
        if mapbox_token:
            collection.plot_map(
                filepath=map_path,
                # height=1000,
                linewidths=[8, 2],
                width_to_height=3.0,
            )
            collection.plot_map(
                filepath=map_path.replace(".html", ".png"),
                linewidths=[16, 8],
                height=500,
                width_to_height=1.0,
            )
            collection.plot_map(
                filepath=map_path.replace(".html", "-thick.png"),
                linewidths=[32, 16],
                height=500,
                width_to_height=1.0,
            )
        elif all(os.path.exists(path) for path in map_asset_paths):
            print(
                "MAPBOX_TOKEN is not set; reusing existing map assets in "
                f"{path_static}."
            )
        else:
            raise RuntimeError(mapbox_token_help)

    collection.generate_astro(
        filepath=path_collection_astro,
        mapfig_name=mapfig_name,
        elevfig_name=elevfig_name,
        include_activity_elevation=args.include_activity_elevation,
        activity_elevation_extension=elevation_extension,
        prettify=args.prettify,
    )

    if os.path.exists(legacy_markdown_path):
        os.remove(legacy_markdown_path)
        print(f"Removed legacy markdown page at {legacy_markdown_path}")


if __name__ == "__main__":
    main()
