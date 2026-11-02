# engine/parts/music/node.py

import random
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional

from engine.parts.core.logger import log_overview, log_detail, log_error

NODE_NAME = "MUSIC"

# ---------------------------------------------------------
# PATHS (MATCHING YOUR ENGINE LAYOUT)
# ---------------------------------------------------------

METADATA_PENDING_DIR = Path("REDACTED — production metadata directory")

MUSIC_POOL_DIR    = Path("REDACTED — production music pool directory")
MUSIC_PENDING_DIR = Path("REDACTED — production music pending directory")
MUSIC_ARCHIVE_DIR = Path("REDACTED — production music archive directory")

ALLOWED_EXTENSIONS = (".mp3",)


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def _clear_music_pending() -> None:
    """Ensure the pending directory exists without disturbing other jobs."""
    MUSIC_PENDING_DIR.mkdir(parents=True, exist_ok=True)


def _get_latest_metadata_file(slug: Optional[str] = None) -> Optional[Path]:
    """Resolve the requested job metadata, or newest file for legacy callers."""
    if slug:
        candidate = METADATA_PENDING_DIR / f"{slug}.json"
        return candidate if candidate.is_file() else None
    files = list(METADATA_PENDING_DIR.glob("*.json"))
    if not files:
        return None
    latest = max(files, key=lambda f: f.stat().st_mtime)
    log_detail(f"[{NODE_NAME}] Latest metadata file: [REDACTED]")
    return latest


def _list_pool_tracks() -> list[Path]:
    """Return all valid .mp3 files in music pool as Path objects."""
    if not MUSIC_POOL_DIR.exists():
        return []
    tracks = [
        p for p in MUSIC_POOL_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS
    ]
    log_detail(f"[{NODE_NAME}] Found {len(tracks)} tracks in music pool.")
    return tracks


def _probe_duration(path: Path) -> float:
    """
    Use ffprobe to get duration in seconds.
    Raises RuntimeError on failure.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        result = subprocess.check_output(cmd, text=True, timeout=30).strip()
        duration = float(result)
        log_detail(f"[{NODE_NAME}] Duration for selected track: {duration:.3f}s")
        return duration
    except Exception as e:
        raise RuntimeError(
            f"Failed to probe duration: {type(e).__name__}"
        )


def _pick_random_start(duration: float, slice_length: float = 12.0,
                       margin: float = 3.0) -> float:
    """
    Pick a random start time inside [margin, duration - margin - slice_length].
    Requires duration >= slice_length + 2*margin (18s for 12s + 3s/side).
    """
    min_start = margin
    max_start = duration - margin - slice_length

    if max_start < min_start:
        raise RuntimeError(
            f"Track too short for safe random slice: "
            f"duration={duration:.3f}s, needed >= {slice_length + 2*margin:.3f}s"
        )

    start = random.uniform(min_start, max_start)
    log_detail(
        f"[{NODE_NAME}] Random slice start={start:.3f}s "
        f"(window {min_start:.3f}–{max_start:.3f}s)"
    )
    return start


def _extract_slice(
    source: Path,
    start: float,
    length: float,
    dest: Path,
) -> None:
    """
    Use ffmpeg to extract a 12-second, lightly-normalized, softly-faded slice.

    - 12.0 seconds exactly (requested)
    - loudnorm for gentle loudness control
    - 0.25s fade-in at start
    - 0.25s fade-out at end
    """

    dest.parent.mkdir(parents=True, exist_ok=True)

    slice_length = length
    fade_dur = 0.25
    fade_out_start = slice_length - fade_dur  # 11.75 for 12s

    audio_filter = (
        # light loudness normalization (keeps things sane but not crushed)
        "loudnorm=I=-16:LRA=11:TP=-1.5,"
        # fade in from 0 → 0.25s
        f"afade=t=in:ss=0:d={fade_dur},"
        # fade out from 11.75 → 12.0s
        f"afade=t=out:st={fade_out_start}:d={fade_dur}"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{start:.3f}",
        "-t", f"{slice_length:.3f}",
        "-i", str(source),
        "-af", audio_filter,
        "-acodec", "libmp3lame",
        "-b:a", "192k",
        str(dest),
    ]

    # REDACTED — command arguments include production filesystem paths.
    log_detail(f"[{NODE_NAME}] Running ffmpeg slice command.")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg slice failed: exit code {result.returncode}"
        )

    if not dest.exists():
        raise RuntimeError("Slice output missing.")

    log_detail(f"[{NODE_NAME}] Slice written to [REDACTED]")


# ---------------------------------------------------------
# MASTER ENTRYPOINT
# ---------------------------------------------------------

def select_music_track(slug: Optional[str] = None) -> Dict[str, Any]:
    """
    MUSIC NODE v2 — SUNO SLICE MODE

    Behavior:
      1. Clear music/pending.
      2. Resolve slug from newest metadata JSON in metadata/pending.
      3. Randomly select a track from music/pool (never moved or deleted).
      4. Probe duration with ffprobe.
      5. Choose random start time in [3s, duration-3s-12s].
      6. Extract a 12.0-second slice with ffmpeg:
           - light loudnorm
           - 0.25s fade in and out
      7. Save slice to music/pending/<slug>.mp3
      8. Copy slice to music/archive/<slug>.mp3
      9. On ANY failure: return success=False, so pipeline aborts BEFORE Sora.
    """

    start_ts = time.time()
    log_overview(f"[{NODE_NAME}] Music node started.")

    try:
        # 1. Clear pending
        _clear_music_pending()

        # 2. Get metadata + slug
        meta_file = _get_latest_metadata_file(slug)
        if not meta_file:
            raise RuntimeError("No metadata JSON found in metadata [json]/pending.")
        slug = meta_file.stem
        log_detail(f"[{NODE_NAME}] Resolved slug from metadata: [REDACTED]")

        # 3. Choose track from pool
        pool_tracks = _list_pool_tracks()
        if not pool_tracks:
            raise RuntimeError("No .mp3 files in music [mp3]/pool.")

        source_track = random.choice(pool_tracks)
        log_detail(f"[{NODE_NAME}] Chosen pool track: [REDACTED]")

        # 4. Probe duration
        duration = _probe_duration(source_track)

        # 5. Random start with safe margins
        slice_length = 12.0
        margin = 3.0
        start_time = _pick_random_start(duration, slice_length=slice_length, margin=margin)

        # 6. Extract 12s slice
        pending_path = MUSIC_PENDING_DIR / f"{slug}.mp3"
        if pending_path.exists():
            raise FileExistsError("Music pending output already exists for this slug.")
        _extract_slice(
            source=source_track,
            start=start_time,
            length=slice_length,
            dest=pending_path,
        )

        # 7. Archive the exact slice under slug cohesion
        MUSIC_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archive_path = MUSIC_ARCHIVE_DIR / f"{slug}.mp3"
        if archive_path.exists():
            raise FileExistsError("Music archive output already exists for this slug.")
        archive_created = False
        try:
            with pending_path.open("rb") as source_file, archive_path.open("xb") as archive_file:
                archive_created = True
                shutil.copyfileobj(source_file, archive_file)
                archive_file.flush()
            shutil.copystat(pending_path, archive_path)
        except Exception:
            if archive_created:
                try:
                    archive_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        log_detail(f"[{NODE_NAME}] Archived slice to [REDACTED]")

        # 8. Done
        elapsed = time.time() - start_ts
        log_overview(
            f"[{NODE_NAME}] Music node complete in {elapsed:.2f}s"
        )

        return {
            "success": True,
            "slug": slug,
            "source_track": "[REDACTED]",
            "slice_start": start_time,
            "slice_duration": slice_length,
            "pending_path": "[REDACTED]",
            "archive_path": "[REDACTED]",
        }

    except Exception as e:
        elapsed = time.time() - start_ts
        msg = f"Music node failed after {elapsed:.2f}s: {type(e).__name__}"
        log_error(f"[{NODE_NAME}] {msg}")
        return {
            "success": False,
            "error": type(e).__name__,
        }


__all__ = ["select_music_track"]
