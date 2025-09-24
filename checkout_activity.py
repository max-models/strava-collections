from stravalib import Client
import os

client_id = os.getenv("STRAVA_CLIENT_ID")
client_secret = os.getenv("STRAVA_CLIENT_SECRET")
refresh_token = os.getenv("STRAVA_REFRESH_TOKEN")

client = Client()

token_response = client.refresh_access_token(
    client_id=client_id,
    client_secret=client_secret,
    refresh_token=refresh_token,
)

# 2. Get tokens
access_token = token_response["access_token"]
new_refresh_token = token_response["refresh_token"]  # may rotate

# 3. Set access token on client
client.access_token = access_token

# 4. Use the client (example: list last 5 activities)
for activity in client.get_activities(limit=5):
    print(activity.id, activity.name, activity.start_date)