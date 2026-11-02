# engine/parts/wiring/archiver.py

import json
import os
import shutil
from pathlib import Path
from engine.parts.core.logger import log_overview, log_detail, log_error

# Directory map
META_PENDING   = Path("REDACTED — production metadata pending directory")
META_ARCHIVE   = Path("REDACTED — production metadata archive directory")

VIDEO_PENDING  = Path("REDACTED — production video pending directory")
VIDEO_ARCHIVE  = Path("REDACTED — production video archive directory")

VOICE_PENDING  = Path("REDACTED — production voiceover pending directory")
VOICE_ARCHIVE  = Path("REDACTED — production voiceover archive directory")

MUSIC_PENDING  = Path("REDACTED — production music pending directory")
MUSIC_ARCHIVE  = Path("REDACTED — production music archive directory")

SUB_PENDING    = Path("REDACTED — production subtitle pending directory")
SUB_ARCHIVE    = Path("REDACTED — production subtitle archive directory")

MERGED_PENDING = Path("REDACTED — production merged-video pending directory")
# Merged archive is handled only by uploader daemon


def _safe_move(src: Path, dst_dir: Path, label: str) -> Path:
    """Move one artifact without overwriting an existing archive entry."""
    if not src.is_file():
        raise FileNotFoundError(f"Required {label} artifact is missing.")

    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists():
        raise FileExistsError(f"Archive destination for {label} already exists.")

    # Hard-link creation is atomic and fails rather than replacing an existing
    # destination. If the filesystem does not support links, use exclusive
    # destination creation and a streamed copy before removing the source.
    try:
        os.link(src, dst)
    except OSError:
        # Cross-filesystem or link-restricted fallback; exclusive creation
        # preserves the no-overwrite guarantee.
        created = False
        try:
            with src.open("rb") as source_file, dst.open("xb") as dest_file:
                created = True
                shutil.copyfileobj(source_file, dest_file)
                dest_file.flush()
                os.fsync(dest_file.fileno())
            shutil.copystat(src, dst)
        except Exception:
            if created:
                try:
                    dst.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

    try:
        src.unlink()
    except OSError:
        # Do not leave a second archive entry if the source could not be
        # removed after linking/copying.
        try:
            dst.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    log_detail(f"[ARCHIVER] Moved {label} to archive.")
    return dst


def archive_artifacts(slug: str) -> dict:
    """Preflight and move the complete intermediate artifact set.

    If a move fails partway through, already-moved artifacts are moved back to
    their original pending locations where possible. Any failed rollback is
    reported explicitly so an operator can reconcile the remaining files.
    """
    moved = []
    try:
        if not slug or Path(slug).name != slug or slug in (".", ".."):
            raise ValueError("Invalid artifact slug.")

        log_overview("[ARCHIVER] Starting artifact archival.")

        metadata_path = META_PENDING / f"{slug}.json"
        with open(metadata_path, "r", encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
        if not isinstance(metadata, dict):
            raise RuntimeError("Metadata must contain a JSON object.")
        canonical_title = metadata.get("title", "")
        if not isinstance(canonical_title, str):
            raise RuntimeError("Metadata title must be a string.")

        moves = (
            (metadata_path, META_ARCHIVE, "metadata"),
            (VIDEO_PENDING / f"{slug}.mp4", VIDEO_ARCHIVE, "raw video"),
            (VOICE_PENDING / f"{slug}.mp3", VOICE_ARCHIVE, "voiceover"),
            (MUSIC_PENDING / f"{slug}.mp3", MUSIC_ARCHIVE, "music snippet"),
            (SUB_PENDING / f"{slug}.ass", SUB_ARCHIVE, "subtitles"),
        )
        merged_path = MERGED_PENDING / f"{slug}.mp4"

        # Complete source and destination preflight before moving anything.
        for src, dst_dir, label in moves:
            if not src.is_file():
                raise FileNotFoundError(f"Required {label} artifact is missing.")
            dst = dst_dir / src.name
            if dst.exists():
                raise FileExistsError(f"Archive destination for {label} already exists.")
        if not merged_path.is_file():
            raise FileNotFoundError("Required merged final video is missing.")

        for src, dst_dir, label in moves:
            dst = _safe_move(src, dst_dir, label)
            moved.append((dst, src))

        log_detail("[ARCHIVER] Final merged video remains in pending.")
        return {"success": True, "title": canonical_title}

    except Exception as e:
        rollback_failures = []
        for archived_path, original_path in reversed(moved):
            try:
                if not archived_path.exists():
                    continue
                if original_path.exists():
                    raise FileExistsError("Original pending path is occupied.")
                original_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(archived_path), str(original_path))
            except Exception:
                rollback_failures.append(archived_path.name)

        if rollback_failures:
            log_error(
                f"[ARCHIVER] Rollback incomplete for {len(rollback_failures)} artifact(s); manual reconciliation required."
            )
        log_error(f"[ARCHIVER] FAILED — {type(e).__name__}")
        return {
            "success": False,
            "title": "",
            "error": type(e).__name__,
            "rollback_incomplete": bool(rollback_failures),
        }
