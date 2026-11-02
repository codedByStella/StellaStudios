# engine/parts/stitcher/node.py

import time
import subprocess
import json
from pathlib import Path
from typing import Dict, Any

from engine.parts.core.logger import log_overview, log_detail, log_error

def _escape_drawtext_text(text: str) -> str:
    """
    Minimal escaping for ffmpeg drawtext.
    """
    return (
        text.replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
    )

NODE_NAME = "STITCHER"

# Input directories
VIDEO_DIR = Path("REDACTED — production video directory")
VOICE_DIR = Path("REDACTED — production voiceover directory")
MUSIC_DIR = Path("REDACTED — production music directory")
ASS_DIR   = Path("REDACTED — production subtitle directory")

# Preset directories
WATERMARK_DIR = Path("REDACTED — production watermark preset directory")

# Output directory
MERGED_DIR = Path("REDACTED — production merged video directory")
MERGED_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------

def _find_file(directory: Path, slug: str, ext: str) -> Path:
    f = directory / f"{slug}{ext}"
    if not f.is_file():
        raise FileNotFoundError("Missing required input file.")
    return f


# ---------------------------------------------------------
# WATERMARK LOADING
# ---------------------------------------------------------

def _load_watermark_preset():
    if not WATERMARK_DIR.exists():
        return None
    preset_files = list(WATERMARK_DIR.glob("*.json"))
    if not preset_files:
        return None

    import random
    selected = random.choice(preset_files)
    try:
        return selected, json.loads(selected.read_text())
    except Exception as e:
        raise RuntimeError(
            f"Failed to load watermark preset: {type(e).__name__}"
        )


def _make_watermark_filter(preset):
    if not preset:
        return None

    raw_text = preset.get("text", "")
    text = _escape_drawtext_text(str(raw_text))

    fontsize = int(preset.get("fontsize", 24))
    opacity  = float(preset.get("opacity", 0.25))

    fontcolor = (
        preset.get("fontcolor")
        or preset.get("font_color")
        or preset.get("color")
        or "white"
    )

    position = preset.get("position", "bottom-right")

    border_color = (
        preset.get("bordercolor") or preset.get("outline_color")
        or preset.get("outlinecolor")
        or None
    )
    border_width = float(preset.get("borderw") or preset.get("outline_thickness")
                         or preset.get("outlinethickness")
                         or 0)

    shadow_color = (
        preset.get("shadow_color")
        or preset.get("shadowcolor")
        or None
    )
    shadow_x = int(preset.get("shadow_x") or preset.get("shadowx") or 0)
    shadow_y = int(preset.get("shadow_y") or preset.get("shadowy") or 0)

    margin_x = int(preset.get("margin_x", 40))
    margin_y = int(preset.get("margin_y", 40))

    if "x" in preset and "y" in preset:
        x, y = str(preset["x"]), str(preset["y"])
    elif position == "bottom-right":
        x = f"w-text_w-{margin_x}"
        y = f"h-text_h-{margin_y}"
    elif position == "bottom-left":
        x = f"{margin_x}"
        y = f"h-text_h-{margin_y}"
    elif position == "top-left":
        x = f"{margin_x}"
        y = f"{margin_y}"
    elif position == "top-right":
        x = f"w-text_w-{margin_x}"
        y = f"{margin_y}"
    else:
        x = f"w-text_w-{margin_x}"
        y = f"h-text_h-{margin_y}"

    border_params = ""
    if border_color and border_width > 0:
        border_params = f":bordercolor={border_color}:borderw={border_width}"

    shadow_params = ""
    if shadow_color:
        shadow_params = (
            f":shadowcolor={shadow_color}"
            f":shadowx={shadow_x}:shadowy={shadow_y}"
        )

    fontfile = preset.get("font") or preset.get("fontfile")
    fontfile_param = f":fontfile='{fontfile}'" if fontfile else ""
    return (
        f"drawtext=text='{text}':"
        f"x={x}:"
        f"y={y}:"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}@{opacity}"
        f"{fontfile_param}"
        f"{border_params}"
        f"{shadow_params}"
    )


# ---------------------------------------------------------
# FFmpeg COMMAND BUILDER
# ---------------------------------------------------------

def _generate_ffmpeg_command(
    video: Path,
    voice: Path,
    music: Path,
    output: Path,
    ass_path: Path | None,
    watermark_filter: str | None
):
    """
    Subtitle path gets passed through libass.
    Watermark still uses drawtext.
    Audio mixing unchanged.
    """

    # --------------------
    # AUDIO MIXING GRAPH
    # --------------------
    # REDACTED — production audio mixing weights.
    amix_graph = (
        "[0:a]volume=0.50[sora];"
        "[1:a]volume=0.85[voice];"
        "[2:a]volume=0.38[music];"
        "[sora][voice][music]amix=inputs=3:weights=REDACTED[aout]"
    )

    filter_chains = [amix_graph]

    # --------------------
    # VIDEO CHAIN
    # --------------------

    video_chain_parts = []

    if ass_path:
        video_chain_parts.append(f"ass='{ass_path}'")

    if watermark_filter:
        video_chain_parts.append(watermark_filter)

    if video_chain_parts:
        video_chain = "[0:v]" + ",".join(video_chain_parts) + "[vout]"
        filter_chains.append(video_chain)
    else:
        video_chain = None

    filtergraph = ";".join(filter_chains)

    # --------------------
    # FFmpeg command
    # --------------------
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video),
        "-i", str(voice),
        "-i", str(music),
        "-filter_complex", filtergraph,
        "-map", "[vout]" if video_chain else "0:v",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output),
    ]

    # REDACTED — full command contains production paths and filter configuration.
    log_detail(f"{NODE_NAME} ffmpeg command constructed.")
    return cmd


# ---------------------------------------------------------
# MASTER
# ---------------------------------------------------------

def stitch_video(payload: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    log_overview(f"{NODE_NAME} start")

    try:
        slug = payload.get("slug")
        if (
            not isinstance(slug, str)
            or not slug
            or Path(slug).name != slug
            or slug in (".", "..")
            or "\\" in slug
        ):
            raise ValueError("Stitcher requires a valid artifact slug.")

        log_detail("Stitcher received media payload.")

        video = _find_file(VIDEO_DIR, slug, ".mp4")
        voice = _find_file(VOICE_DIR, slug, ".mp3")
        music = _find_file(MUSIC_DIR, slug, ".mp3")

        # Load .ass subtitle file
        ass_path = ASS_DIR / f"{slug}.ass"
        if not ass_path.exists():
            log_detail("No ASS subtitles found — proceeding without them")
            ass_path = None

        # Watermark preset
        watermark_data = _load_watermark_preset()
        watermark_filter = _make_watermark_filter(watermark_data[1]) if watermark_data else None

        # Output
        output_path = MERGED_DIR / f"{slug}.mp4"
        if output_path.exists():
            raise FileExistsError("Merged output already exists for this slug.")
        cmd = _generate_ffmpeg_command(
            video,
            voice,
            music,
            output_path,
            ass_path,
            watermark_filter,
        )

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg processing failed: exit code {result.returncode}"
            )

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError("Stitcher finished but output is missing or empty.")

        elapsed = time.time() - start
        log_overview(
            f"{NODE_NAME} complete ({elapsed:.2f}s)"
        )

        return {
            "success": True,
            "slug": slug,
            "output_path": str(output_path),
        }

    except Exception as e:
        elapsed = time.time() - start
        msg = (
            f"{NODE_NAME} FAILED after {elapsed:.2f}s: "
            f"{type(e).__name__}"
        )
        log_error(msg)
        return {"success": False, "error": type(e).__name__}
