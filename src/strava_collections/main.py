import argparse
import os

from strava_collections.collection import StravaCollection


def main():
    """Main method called from the command line."""
    parser = argparse.ArgumentParser(description="Plot Strava activities.")
    parser.add_argument(
        "ids",
        nargs="+",
        type=str,
        help="Space-separated list of Strava activity IDs, e.g., 123 456 789",
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

    args = parser.parse_args()

    collection_filename = "collection-" + args.collection.lower().replace(" ", "-")

    # Parse activity IDs into integers
    activity_ids = []
    for id in args.ids:
        id = id.replace("https://www.strava.com/activities/", "")

        if id.lower().endswith("f"):
            flip = True
            id = int(id[:-1])
        else:
            flip = False
            id = int(id)
        activity_ids.append((id, flip))

    # Create collection and plot
    collection = StravaCollection(
        name=args.collection,
        activity_ids=activity_ids,
    )

    # Set filenames
    path_static = os.path.join(args.output, "_static")
    mapfig_name = f"{collection_filename}-map.html"
    map_path = os.path.join(path_static, mapfig_name)

    elevfig_name = f"{collection_filename}-elev.html"
    elev_path = os.path.join(path_static, elevfig_name)

    path_collection_md = os.path.join(args.output, f"{collection_filename}.md")

    # Plot figures
    collection.plot_map(filepath=map_path)
    collection.plot_map(filepath=map_path.replace(".html", ".png"))
    collection.plot_elevation(filepath=elev_path)

    # Create markdown for hte collection
    collection.generate_markdown(
        filepath=path_collection_md,
        mapfig_name=mapfig_name,
        elevfig_name=elevfig_name,
    )


if __name__ == "__main__":
    main()
