# engine/parts/subtitler/node.py

import json
import subprocess
import re
from pathlib import Path
from engine.parts.core.logger import log_detail, log_error, log_overview

NODE_NAME = "SUBTITLER"

VOICE_DIR = Path("REDACTED — production voiceover directory")
META_DIR  = Path("REDACTED — production metadata directory")
ASS_DIR   = Path("REDACTED — production subtitle output directory")
ASS_DIR.mkdir(parents=True, exist_ok=True)


# -------------------------------
# Utility: get duration of audio
# -------------------------------
def get_audio_duration(path: Path) -> float:
    """Use ffprobe to get total duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
    )

    try:
        duration = float(result.stdout.strip())
        return max(duration, 0.1)  # avoid zero
    except Exception:
        raise RuntimeError("ffprobe failed to read audio duration.")


# -------------------------------
# Utility: ASS timestamp formatting
# -------------------------------
def ts(seconds: float) -> str:
    """Convert seconds → ASS timestamp h:mm:ss.xx"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# -------------------------------
# Parse script → phrases
# -------------------------------
def extract_phrases(raw_script: str):
    """
    Take e.g.
    '[whisper] let your shoulders fall, breathe with the quiet pier and water, stay here softly'

    → [
        'let your shoulders fall',
        'breathe with the quiet pier and water',
        'stay here softly'
      ]
    """

    script = raw_script.replace("[whisper]", "").strip()

    # Split on commas or periods
    parts = re.split(r"[,.]", script)

    # Remove empty fragments
    phrases = [p.strip() for p in parts if p.strip()]

    return phrases


# -------------------------------
# Build the .ass file
# -------------------------------
def write_ass(slug: str, phrases, audio_duration: float):
    """Render each phrase at evenly divided intervals."""

    ass_path = ASS_DIR / f"{slug}.ass"

    HEADER = """[Script Info]
ScriptType: v4.00+
Collisions: Normal
PlayResX: 720
PlayResY: 1280
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: StellaSoft,Comfortaa,42,&H00FAEFFF,&H00000000,&H00FFB3F6,&H00000000,0,0,0,0,100,100,0,0,1,3,0,2,40,40,120,0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    n = len(phrases)
    if n == 0:
        raise RuntimeError("No phrases after parsing script.")

    # Equal slice duration
    usable_duration = max(audio_duration - 0.3, 0.1)
    per_phrase = usable_duration / n

    # Small offset so first line doesn't flash instantly
    cursor = 0.3

    lines = [HEADER]

    for phrase in phrases:
        start = cursor
        end   = cursor + per_phrase

        # EXACT TEXT — ZERO REWRITING
        text = phrase

        line = (
            f"Dialogue: 0,{ts(start)},{ts(end)},StellaSoft,,0,0,0,,"
            f"{{\\fad(150,150)}}{text}\n"
        )
        lines.append(line)

        cursor = end

    ass_path.write_text("".join(lines), encoding="utf-8")
    return ass_path


# -------------------------------
# MAIN ENTRYPOINT
# -------------------------------
def generate_subtitles(slug: str):
    try:
        log_overview("[SUBTITLER] Starting subtitle generation.")

        voice_path = VOICE_DIR / f"{slug}.mp3"
        meta_path  = META_DIR  / f"{slug}.json"

        if not voice_path.exists():
            raise FileNotFoundError("Missing voiceover input.")

        if not meta_path.exists():
            raise FileNotFoundError("Missing metadata input.")

        meta = json.loads(meta_path.read_text())
        raw_script = meta.get("voice", "").strip()

        if not raw_script:
            raise RuntimeError("Metadata JSON missing 'voice' text.")

        phrases = extract_phrases(raw_script)
        log_detail(f"[SUBTITLER] Parsed {len(phrases)} phrase(s).")

        duration = get_audio_duration(voice_path)
        log_detail(f"[SUBTITLER] Audio duration = {duration:.2f}s")

        ass_path = write_ass(slug, phrases, duration)

        log_overview("[SUBTITLER] Subtitle generation complete.")
        return {"success": True, "slug": slug, "ass_path": "[REDACTED]"}

    except Exception as e:
        log_error(f"[SUBTITLER] FAILED — {type(e).__name__}")
        return {"success": False, "error": type(e).__name__}
