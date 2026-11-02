# nodes/wiring/loader.py

import sys
sys.path.append("REDACTED — production application root")

import json
import os

from engine.parts.core.logger import log_detail, log_error
from .helpers import ensure_file, join

RAW_METADATA_DIR = "REDACTED — production metadata directory"
FINAL_VIDEO_DIR = "REDACTED — production final-video directory"

def metadata_path(slug: str):
    return join(RAW_METADATA_DIR, f"{slug}.json")

def final_video_path(slug: str):
    return join(FINAL_VIDEO_DIR, f"{slug}.mp4")


def load_metadata(slug: str):
    """
    Load the GPT output slug.json and parse it.
    """
    path = metadata_path(slug)
    ensure_file(path, "Metadata JSON")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not all(key in data for key in ("title", "description", "video", "voice", "music")):
        raise RuntimeError("Malformed metadata: one or more required schema fields are missing.")

    log_detail("Loaded metadata JSON.", component="wiring")
    return data
