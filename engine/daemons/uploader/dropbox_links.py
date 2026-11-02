# engine/daemons/uploader/dropbox_links.py

from __future__ import annotations

import os
import requests

from engine.parts.core.logger import log_overview, log_error
from engine.parts.core.secrets import get_secret

# Dropbox API token from your secret store
DROPBOX_TOKEN = get_secret("DROPBOX_ACCESS_TOKEN")


def _to_dropbox_path(local_path: str) -> str:
    """
    Convert an absolute local Dropbox-synced path.

    # REDACTED — original production filesystem path.
    Into a Dropbox API-relative path.
    """
    # REDACTED — original production Dropbox root.
    prefix = "REDACTED"
    if local_path.startswith(prefix):
        rel = local_path[len(prefix):]
    else:
        rel = local_path
    if not rel.startswith("/"):
        rel = "/" + rel
    return rel

def create_public_link(dropbox_path: str) -> str:
    """
    Attempts to create a new Dropbox public link.
    If the link already exists (409/shared_link_already_exists),
    retrieve the existing link instead.
    """

    url = "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings"
    headers = {
        "Authorization": f"Bearer {DROPBOX_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {"path": dropbox_path, "settings": {"requested_visibility": "public"}}

    resp = requests.post(url, headers=headers, json=data, timeout=30)

    # Success: return the new link
    if resp.status_code == 200:
        link = resp.json()["url"]
        # REDACTED — Dropbox path and generated public sharing URL.
        log_overview("[UPLOADER-DAEMON] Created new Dropbox link")
        return link

    # Already exists: retrieve the existing link instead
    if resp.status_code == 409 and resp.json().get("error", {}).get(".tag") == "shared_link_already_exists":
        list_url = "https://api.dropboxapi.com/2/sharing/list_shared_links"
        list_headers = {
            "Authorization": f"Bearer {DROPBOX_TOKEN}",
            "Content-Type": "application/json",
        }
        list_data = {"path": dropbox_path}

        list_resp = requests.post(list_url, headers=list_headers, json=list_data, timeout=30)

        if list_resp.status_code == 200:
            links = list_resp.json().get("links", [])
            if links:
                link = links[0]["url"]
                # REDACTED — Dropbox path and existing public sharing URL.
                log_overview("[UPLOADER-DAEMON] Reusing existing Dropbox link")
                return link

        # REDACTED — raw Dropbox API response may contain sensitive data.
        raise RuntimeError("Existing link retrieval failed")

    # Any other error
    # REDACTED — raw Dropbox API response may contain sensitive data.
    log_error(f"[UPLOADER-DAEMON] Dropbox link error {resp.status_code}")
    raise RuntimeError("Dropbox link creation failed")
