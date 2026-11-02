# engine/parts/elevenlab/node.py

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

import requests

from engine.parts.core.logger import log_overview, log_detail, log_error
from engine.parts.core.secrets import get_secret


# ---------------------------------------------------------
# CONSTANTS & PATHS
# ---------------------------------------------------------

NODE = "ELEVENLABS"

BASE_DIR = Path(__file__).resolve().parent
PRESET_DIR = BASE_DIR / "presets"

# Dropbox wiring
# REDACTED — production filesystem locations.
METADATA_PENDING = Path("REDACTED")
VOICE_PENDING = Path("REDACTED")

# Shared secret resolution keeps OS environment variables authoritative.
ELEVENLABS_API_KEY = get_secret("ELEVENLABS_API_KEY")


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def clear_pending():
    """Ensure the pending directory exists without deleting other jobs' files."""
    VOICE_PENDING.mkdir(parents=True, exist_ok=True)


def resolve_metadata(slug: Optional[str]) -> Optional[Path]:
    """Return a metadata JSON path by slug or newest file."""
    METADATA_PENDING.mkdir(parents=True, exist_ok=True)

    if slug:
        candidate = METADATA_PENDING / f"{slug}.json"
        return candidate if candidate.is_file() else None

    files = list(METADATA_PENDING.glob("*.json"))
    if not files:
        return None

    return max(files, key=lambda f: f.stat().st_mtime)


def load_metadata(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise RuntimeError("Metadata file malformed: [REDACTED]")

    return data


def extract_voice(metadata: Dict[str, Any]) -> str:
    if "voice" not in metadata:
        raise RuntimeError("Metadata missing 'voice' field.")

    voice = metadata["voice"]

    if not isinstance(voice, str) or not voice.strip():
        raise RuntimeError("'voice' field empty or not a string.")

    return voice.strip()


# ---------------------------------------------------------
# PRESET LOADING
# ---------------------------------------------------------

def load_preset(mode: str, manual: Optional[Dict[str, Any]] = None):
    if mode == "manual":
        if not manual:
            raise RuntimeError("Manual mode requires manual preset dict.")
        return manual

    if mode == "auto":
        preset_path = PRESET_DIR / "defaults.json"
    elif mode == "debug":
        preset_path = PRESET_DIR / "debugging.json"
    else:
        raise RuntimeError("Invalid mode: must be auto/debug/manual")

    if not preset_path.exists():
        raise RuntimeError("Preset missing: [REDACTED]")

    with open(preset_path, "r", encoding="utf-8") as f:
        preset = json.load(f)

    required = ("voice_id", "model_id")
    for r in required:
        if r not in preset:
            raise RuntimeError(f"Preset missing key '{r}'")

    return preset


# ---------------------------------------------------------
# ELEVENLABS TTS CALL
# ---------------------------------------------------------

def call_tts(text: str, preset: dict, out_path: Path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{preset['voice_id']}/stream"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }

    body = {
        "model_id": preset["model_id"],
        "text": text,
        "voice_settings": {
            "stability": float(preset.get("stability", 0.5)),
            "similarity_boost": float(preset.get("similarity_boost", 0.8)),
            "style": float(preset.get("style", 0.0)),
            "use_speaker_boost": bool(preset.get("use_speaker_boost", False)),
        },
        "output_format": "mp3",
        "speed": float(preset.get("speed", 1.0)),
        "optimize_streaming_latency": 1,
    }

    # REDACTED — original log included a preview of generated voice text.
    log_detail(f"[{NODE}] Sending TTS request.")

    resp = requests.post(url, headers=headers, json=body, timeout=40)

    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs error {resp.status_code}: [REDACTED — API response body]")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(resp.content)

    if not out_path.exists():
        raise RuntimeError("TTS output not created: [REDACTED]")

    log_detail(f"[{NODE}] Audio saved → [REDACTED — production filesystem path]")


# ---------------------------------------------------------
# MASTER ENTRY
# ---------------------------------------------------------

def generate_voiceover(mode="auto", manual_preset=None, slug=None):
    start = time.time()
    log_overview(f"[{NODE}] Start (mode={mode})")

    try:
        # Step 1: Clear pending
        clear_pending()

        # Step 2: Resolve metadata
        meta_path = resolve_metadata(slug)
        if not meta_path:
            raise RuntimeError("No metadata JSON found.")

        effective_slug = meta_path.stem
        log_detail(f"[{NODE}] Using metadata: [REDACTED — production filesystem path]")

        metadata = load_metadata(meta_path)
        text = extract_voice(metadata)

        # Step 3: Load preset
        preset = load_preset(mode, manual_preset)

        # Step 4: Perform TTS
        out_path = VOICE_PENDING / f"{effective_slug}.mp3"
        call_tts(text, preset, out_path)

        # Step 5: Done
        elapsed = time.time() - start
        log_overview(f"[{NODE}] Completed voiceover in {elapsed:.2f}s")

        return {
            "success": True,
            "slug": effective_slug,
            "audio_path": "[REDACTED — production filesystem path]",
        }

    except Exception as e:
        elapsed = time.time() - start
        log_error(f"[{NODE}] FAILED after {elapsed:.2f}s: {type(e).__name__}")
        return {"success": False, "error": type(e).__name__}


__all__ = ["generate_voiceover"]
