import os

from stravalib import Client

client_id = os.getenv("STRAVA_CLIENT_ID")
client_secret = os.getenv("STRAVA_CLIENT_SECRET")

client = Client()
url = client.authorization_url(
    client_id=client_id,
    redirect_uri="http://127.0.0.1:5000/authorization",
)

print("Open the following website, authenticate, and copy the code:")
print(url)

code = input("Paste the code here: ")

token_response = client.exchange_code_for_token(
    client_id=client_id,
    client_secret=client_secret,
    code=code,
)
# The token response above contains both an access_token and a refresh token.
access_token = token_response["access_token"]
refresh_token = token_response["refresh_token"]  # You'll need this in 6 hours

print(f"{access_token = }")
print(f"{refresh_token = }")
