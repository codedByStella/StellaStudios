# engine/parts/sora/node.py

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

from openai import OpenAI

from engine.parts.core.logger import log_overview, log_detail, log_error
from engine.parts.core.secrets import get_secret


# ---------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------

NODE = "SORA"

BASE_DIR = Path(__file__).resolve().parent
PRESET_DIR = BASE_DIR / "presets"

METADATA_PENDING = Path("REDACTED — production metadata directory")
VIDEO_PENDING = Path("REDACTED — production video directory")

# Shared secret resolution keeps OS environment variables authoritative.
OPENAI_KEY = get_secret("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY)


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def clear_pending():
    """Ensure the pending directory exists without deleting other jobs' files."""
    VIDEO_PENDING.mkdir(parents=True, exist_ok=True)


def resolve_metadata(slug: Optional[str]) -> Optional[Path]:
    METADATA_PENDING.mkdir(parents=True, exist_ok=True)

    if slug:
        p = METADATA_PENDING / f"{slug}.json"
        return p if p.is_file() else None

    files = list(METADATA_PENDING.glob("*.json"))
    if not files:
        return None

    return max(files, key=lambda f: f.stat().st_mtime)


def load_metadata(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise RuntimeError("Metadata invalid (not object)")

    return data


def extract_prompt(metadata: Dict[str, Any]) -> str:
    if "video" not in metadata:
        raise RuntimeError("Metadata missing 'video' field")

    prompt = metadata["video"]
    if not isinstance(prompt, str):
        raise RuntimeError("'video' field is not a string")

    prompt = prompt.strip()
    if not prompt:
        raise RuntimeError("'video' field empty after stripping")

    return prompt


# ---------------------------------------------------------
# PRESETS
# ---------------------------------------------------------

def load_preset(mode: str, manual: Optional[dict] = None) -> dict:
    if mode == "manual":
        if not manual:
            raise RuntimeError("Manual mode requires manual preset dict")
        return manual

    if mode == "auto":
        p = PRESET_DIR / "defaults.json"
    elif mode == "debug":
        p = PRESET_DIR / "debugging.json"
    else:
        raise RuntimeError("Mode must be auto/debug/manual")

    if not p.exists():
        raise RuntimeError("Sora preset missing")

    with open(p, "r", encoding="utf-8") as f:
        preset = json.load(f)

    if "model" not in preset:
        raise RuntimeError("Sora preset missing 'model'")

    return preset


# ---------------------------------------------------------
# CALL SORA
# ---------------------------------------------------------

def call_sora(prompt: str, preset: dict) -> bytes:
    model = preset.get("model")
    seconds = str(preset.get("seconds", "12"))
    size = preset.get("size", "720x1280")

    # REDACTED — prompt preview omitted to avoid exposing generated content.
    log_detail(
        f"[{NODE}] Sora request: model='{model}', seconds='{seconds}', "
        f"size='{size}'"
    )

    job = client.videos.create_and_poll(
        model=model,
        prompt=prompt,
        seconds=seconds,
        size=size,
    )

    raw = client.videos.download_content(job.id)
    video_bytes = raw.read()

    if not video_bytes:
        raise RuntimeError("Sora returned empty video content")

    return video_bytes


# ---------------------------------------------------------
# MASTER ENTRYPOINT
# ---------------------------------------------------------

def generate_sora_video(
    mode: str = "auto",
    manual_preset: Optional[dict] = None,
    slug: Optional[str] = None,
) -> Dict[str, Any]:

    start = time.time()
    log_overview(f"[{NODE}] Start (mode={mode})")

    try:
        clear_pending()

        meta_path = resolve_metadata(slug)
        if not meta_path:
            raise RuntimeError("No metadata JSON found")

        effective_slug = meta_path.stem
        log_detail(f"[{NODE}] Using metadata: [REDACTED]")

        metadata = load_metadata(meta_path)
        prompt = extract_prompt(metadata)

        preset = load_preset(mode, manual_preset)

        video_bytes = call_sora(prompt, preset)

        # ********** FIXED OUTPUT NAMING HERE **********
        out_path = VIDEO_PENDING / f"{effective_slug}.mp4"
        # ************************************************

        VIDEO_PENDING.mkdir(parents=True, exist_ok=True)

        with open(out_path, "wb") as f:
            f.write(video_bytes)

        if not out_path.exists():
            raise RuntimeError("Sora output write failed")

        elapsed = time.time() - start
        log_overview(
            f"[{NODE}] Completed video generation (took {elapsed:.2f}s)"
        )

        return {
            "success": True,
            "slug": effective_slug,
            "video_path": "[REDACTED]",
        }

    except Exception as e:
        elapsed = time.time() - start
        log_error(
            f"[{NODE}] FAILED after {elapsed:.2f}s: {type(e).__name__}"
        )
        return {
            "success": False,
            "error": type(e).__name__,
        }


__all__ = ["generate_sora_video"]
