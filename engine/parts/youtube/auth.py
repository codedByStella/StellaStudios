# engine/parts/youtube/auth.py

import os
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# Scope we used when generating the refresh token
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeAuthError(Exception):
    """Thrown when YouTube auth cannot be initialized properly."""
    pass


def build_youtube_client() -> "googleapiclient.discovery.Resource":
    """
    Build an authenticated YouTube Data API client using:
    - client_id
    - client_secret
    - refresh_token
    - token_uri

    These must be present in the environment.
    """

    client_id = os.getenv("YT_CLIENT_ID")
    client_secret = os.getenv("YT_CLIENT_SECRET")
    refresh_token = os.getenv("YT_REFRESH_TOKEN")
    token_uri = os.getenv("YT_TOKEN_URI", "https://oauth2.googleapis.com/token")

    missing = [
        name for name, val in [
            ("YT_CLIENT_ID", client_id),
            ("YT_CLIENT_SECRET", client_secret),
            ("YT_REFRESH_TOKEN", refresh_token),
        ]
        if not val
    ]
    if missing:
        raise YouTubeAuthError(f"Missing YouTube OAuth env vars: {', '.join(missing)}")

    # Create credentials object from the saved refresh token
    creds = Credentials(
        token=None,               # Access token will be fetched via refresh
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=YT_SCOPES,
    )

    # Ensure we actually have a fresh access token before building the client
    if not creds.valid:
        if creds.refresh_token:
            creds.refresh(Request())
        else:
            raise YouTubeAuthError("Credentials invalid and no refresh token present.")

    # Build the YouTube Data API client
    youtube = build("youtube", "v3", credentials=creds)
    return youtube
