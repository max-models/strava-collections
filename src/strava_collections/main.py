import argparse
import os

import plotly.express as px
from stravalib import Client

from strava_collections.collection import StravaCollection


def main():
    """Main method called from the command line."""
    parser = argparse.ArgumentParser(description="Plot Strava activities.")
    parser.add_argument(
        "ids",
        nargs="+",
        type=int,
        help="Space-separated list of Strava activity IDs, e.g., 123 456 789",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="./",
        help="Output directory (default: ./)",
    )
    args = parser.parse_args()

    # Parse activity IDs into integers
    activity_ids = args.ids

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
    fig = collection.plot_map()

    # Save HTML
    map_path = os.path.join(args.output, "map.html")
    fig.write_html(map_path, include_plotlyjs="cdn", full_html=True)
    print(f"Saved plot to {map_path}")


if __name__ == "__main__":
    main()
