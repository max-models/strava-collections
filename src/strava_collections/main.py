import argparse
import os
from ast import arg

import yaml

from strava_collections.collection import StravaCollection


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
        default=None,
        help="Path to unput yaml file (default: None)",
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

    args = parser.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            print(data["runs"]["steps"][0]["with"]["activity_ids"])
            activity_ids = data["runs"]["steps"][0]["with"]["activity_ids"].split(" ")
            output = data["runs"]["steps"][0]["with"]["output_dir"]
            collection_name = data["runs"]["steps"][0]["with"]["collection_name"]
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

    # Set filenames
    path_static = os.path.join(output, "_static")
    mapfig_name = f"{collection_filename}-map.html"
    map_path = os.path.join(path_static, mapfig_name)

    elevfig_name = f"{collection_filename}-elev.html"
    elev_path = os.path.join(path_static, elevfig_name)

    path_collection_md = os.path.join(output, f"{collection_filename}.md")

    for activity in collection.activities:
        activity.plot_elevation(
            filepath=os.path.join(path_static, f"activity-{activity.activity_id}.html"),
        )

    # Plot figures
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
    collection.plot_elevation(filepath=elev_path)

    # Create markdown for hte collection
    collection.generate_markdown(
        filepath=path_collection_md,
        mapfig_name=mapfig_name,
        elevfig_name=elevfig_name,
        prettify=args.prettify,
    )


if __name__ == "__main__":
    main()
