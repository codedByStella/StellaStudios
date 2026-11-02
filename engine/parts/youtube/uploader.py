# engine/parts/youtube/uploader.py

import os
from pathlib import Path
from typing import Optional, Dict, Any

from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from engine.parts.youtube.auth import build_youtube_client
from engine.parts.core.logger import log_overview, log_detail, log_error


def upload_video_to_youtube(
    file_path: Path,
    title: str,
    description: str,
    tags: Optional[list[str]] = None,
    category_id: str = "22",   # 22 = People & Blogs (common for ASMR)
    privacy_status: str = "unlisted"
) -> Dict[str, Any]:
    """
    Upload a video file to YouTube.

    Returns a dict with:
    - 'video_id': str
    - 'status': 'success' or 'error'
    - 'error': Optional[str]
    """
    log_overview("Preparing video upload.", component="youtube")

    if not file_path.exists():
        msg = "Video file does not exist. # REDACTED — local path"
        log_error(msg, component="youtube")
        return {"status": "error", "error": msg}

    youtube = build_youtube_client()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
        }
    }

    if tags:
        body["snippet"]["tags"] = tags

    # Resumable upload, chunked
    media = MediaFileUpload(
        str(file_path),
        mimetype="video/mp4",
        chunksize=8 * 1024 * 1024,  # 8 MiB resumable upload chunks
        resumable=True
    )

    try:
        log_detail("Starting upload.", component="youtube")
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                # status.progress() gives a float 0.0–1.0
                pct = int(status.progress() * 100)
                log_detail(f"Upload progress: {pct}%", component="youtube")

        video_id = response.get("id")
        if not video_id:
            raise RuntimeError("YouTube upload response did not include a video ID.")
        log_overview("Upload complete.", component="youtube")

        return {
            "status": "success",
            "video_id": video_id,
            "error": None,
        }

    except HttpError:
        msg = "YouTube API upload error. # REDACTED — provider response"
        log_error(msg, component="youtube")
        return {
            "status": "error",
            "video_id": None,
            "error": "YouTube API upload error",
        }
    except Exception as e:
        msg = f"Unexpected upload error: {type(e).__name__}"
        log_error(msg, component="youtube")
        return {
            "status": "error",
            "video_id": None,
            "error": type(e).__name__,
        }
