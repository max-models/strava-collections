import argparse
import os

from stravalib import Client

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
        if id.lower().endswith("f"):
            flip = True
            id = int(id[:-1])
        else:
            flip = False
            id = int(id)
        activity_ids.append((id, flip))

    # Load Strava credentials from environment
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")

    client = Client()

    # Refresh access token
    token_response = client.refresh_access_token(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
    )
    client.access_token = token_response["access_token"]

    # Create collection and plot
    collection = StravaCollection(client, activity_ids=activity_ids)
    fig_map = collection.plot_map()
    fig_elev = collection.plot_elevation()

    # Save HTML
    mapfig_name = f"{collection_filename}-map.html"
    map_path = os.path.join(args.output, mapfig_name)
    fig_map.write_html(map_path, include_plotlyjs="cdn", full_html=True)
    print(f"Saved map plot to {map_path}")

    elevfig_name = f"{collection_filename}-elev.html"
    elev_path = os.path.join(args.output, elevfig_name)
    fig_elev.write_html(elev_path, include_plotlyjs="cdn", full_html=True)
    print(f"Saved elevation plot to {elev_path}")

    path_collection_md = os.path.join(args.output, f"{collection_filename}.md")
    with open(path_collection_md, "w") as f:
        f.write(f"# {args.collection}\n")
        f.write(
            f"""
<div style="position: relative; width: 100%; height: 650px;">
  <iframe src="_static/{mapfig_name}" style="width:100%; height:100%; border:none;"></iframe>
</div>
\n\n"""
        )
        f.write(
            f"""
<div style="position: relative; width: 100%; height: 350;">
  <iframe src="_static/{elevfig_name}" style="width:100%; height:100%; border:none;"></iframe>
</div>\n\n"""
        )

    print(f"Saved markdown page to {path_collection_md}")


if __name__ == "__main__":
    main()
