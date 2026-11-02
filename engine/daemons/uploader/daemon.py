
# engine/daemons/uploader/daemon.py

import os
import time
import csv
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta, timezone

import requests

from engine.parts.core.logger import (
    log_overview,
    log_detail,
    log_error,
)
from engine.parts.core.secrets import get_secret
from engine.daemons.uploader.dropbox_links import create_public_link

NODE_NAME = "UPLOADER-DAEMON"

# --------------------------------------------------------------------
# PATHS
# --------------------------------------------------------------------

FINAL_DIR = Path("REDACTED")
METADATA_ARCHIVE_DIR = Path("REDACTED")
ARCHIVE_VIDEO_DIR = Path("REDACTED")

ARCHIVE_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------
# LATE CONFIG
# --------------------------------------------------------------------

LATE_API_KEY = get_secret("LATE_API_KEY")
LATE_DEFAULT_PROFILES = get_secret("LATE_DEFAULT_PROFILES")
LATE_DEFAULT_TZ = get_secret("LATE_DEFAULT_TZ")  # e.g. "UTC"

LATE_BULK_UPLOAD_URL = "https://getlate.dev/api/v1/posts/bulk-upload"

# --------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------


def schedule_time_tomorrow_noon_utc() -> str:
    """
    Returns an ISO-8601 string for tomorrow at 12:00:00 UTC.
    """
    now = datetime.now(timezone.utc)
    tomorrow = now + timedelta(days=1)
    scheduled = tomorrow.replace(hour=12, minute=0, second=0, microsecond=0)
    return scheduled.isoformat().replace("+00:00", "Z")


def build_late_csv_row(
    profiles: str,
    title: str,
    desc: str,
    media_url: str,
    schedule_time: str,
    tz: str,
) -> Dict[str, Any]:
    """
    Build one row for Late's bulk-upload CSV.
    """
    return {
        "profiles": profiles,
        "platforms": "tiktok,instagram",
        "post_content": desc,
        "title": title,
        "media_urls": media_url,
        "schedule_time": schedule_time,
        "tz": tz,
        "publish_now": "false",
        "use_queue": "false",
        "is_draft": "false",
    }


def send_csv_to_late(csv_path: str) -> Optional[bool]:
    """
    POST the CSV file to Late's bulk-upload endpoint.
    Returns True for confirmed acceptance, False for confirmed rejection,
    and None when the outcome is ambiguous and must not be retried automatically.
    """
    try:
        with open(csv_path, "rb") as f:
            files = {"file": ("bulk.csv", f, "text/csv")}
            headers = {"Authorization": f"Bearer {LATE_API_KEY}"}

            resp = requests.post(
                LATE_BULK_UPLOAD_URL,
                files=files,
                headers=headers,
                timeout=30,
            )

        if resp.status_code not in (200, 207):
            log_error(
                f"[{NODE_NAME}] Late bulk-upload HTTP error {resp.status_code}: REDACTED",
                component=NODE_NAME,
            )
            # Server errors can occur after a provider has committed work;
            # treat them as ambiguous and retain the submission marker.
            return False if 400 <= resp.status_code < 500 else None

        try:
            data = resp.json()
        except (ValueError, json.JSONDecodeError):
            log_error(
                f"[{NODE_NAME}] Late returned a non-JSON success response; acceptance is unverified.",
                component=NODE_NAME,
            )
            return None

        if not isinstance(data, dict):
            log_error(
                f"[{NODE_NAME}] Late returned an unexpected response shape.",
                component=NODE_NAME,
            )
            return None

        total = data.get("total")
        valid = data.get("valid")
        invalid = data.get("invalid")
        if type(total) is not int or total != 1 or type(valid) is not int or type(invalid) is not int:
            log_error(
                f"[{NODE_NAME}] Late response did not confirm exactly one processed row; outcome is ambiguous.",
                component=NODE_NAME,
            )
            return None

        if valid == 0 and invalid == 1:
            log_error(
                f"[{NODE_NAME}] Late confirmed the row was invalid.",
                component=NODE_NAME,
            )
            return False

        if valid != 1 or invalid != 0:
            log_error(
                f"[{NODE_NAME}] Late returned inconsistent row counts; outcome is ambiguous.",
                component=NODE_NAME,
            )
            return None

        results = data.get("results")
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            log_error(
                f"[{NODE_NAME}] Late did not return one verifiable row result; outcome is ambiguous.",
                component=NODE_NAME,
            )
            return None
        if results[0].get("ok") is not True:
            log_error(
                f"[{NODE_NAME}] Late row result did not confirm successful creation.",
                component=NODE_NAME,
            )
            return False
        if not isinstance(results[0].get("createdPostId"), str) or not results[0]["createdPostId"]:
            log_error(
                f"[{NODE_NAME}] Late omitted the created post ID; outcome is ambiguous.",
                component=NODE_NAME,
            )
            return None

        log_overview(
            f"[{NODE_NAME}] Late bulk-upload accepted {total} row(s).",
            component=NODE_NAME,
        )
        return True

    except Exception as e:
        log_error(
            f"[{NODE_NAME}] Exception during Late bulk-upload: {type(e).__name__}",
            component=NODE_NAME,
        )
        return None


def archive_video(video_path: Path) -> bool:
    """
    Move the successfully-scheduled video into the archive folder.
    """
    ARCHIVE_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    base_name = video_path.name
    dest = ARCHIVE_VIDEO_DIR / base_name

    try:
        if dest.exists():
            log_error(
                f"[{NODE_NAME}] Archive destination already exists; refusing to overwrite.",
                component=NODE_NAME,
            )
            return False

        # Exclusive destination creation avoids POSIX rename() replacing a
        # file created by another process after the collision check.
        created = False
        try:
            with video_path.open("rb") as source_file, dest.open("xb") as dest_file:
                created = True
                shutil.copyfileobj(source_file, dest_file)
                dest_file.flush()
                os.fsync(dest_file.fileno())
            shutil.copystat(video_path, dest)
            video_path.unlink()
        except Exception:
            if created:
                try:
                    dest.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        log_overview(
            f"[{NODE_NAME}] Archived video → REDACTED",
            component=NODE_NAME,
        )
        return True
    except Exception as e:
        # Report failure so the caller does not mark the job archived.
        log_error(
            f"[{NODE_NAME}] Failed to archive video: {type(e).__name__}",
            component=NODE_NAME,
        )
        return False


def local_path_to_dropbox_path(local_path: Path) -> str:
    """
    Convert a local synced path under the configured Dropbox root
    into a Dropbox API path.
    """
    root = "REDACTED"
    s = str(local_path)
    if s.startswith(root):
        rel = s[len(root):]
    else:
        rel = s

    if not rel.startswith("/"):
        rel = "/" + rel

    return rel


def normalize_dropbox_direct_url(url: str) -> str:
    """
    Convert a Dropbox share URL into a direct file URL
    so Late (especially YouTube) sees an actual video, not an HTML page.
    """
    # Typical shared link: https://www.dropbox.com/s/.../file.mp4?dl=0
    # Direct download:    https://www.dropbox.com/s/.../file.mp4?dl=1
    if "dropbox.com" in url:
        if "dl=0" in url:
            url = url.replace("dl=0", "dl=1")
        elif "dl=1" not in url and "?" in url:
            url = url + "&dl=1"
        elif "?" not in url:
            url = url + "?dl=1"
    return url


def load_metadata_for_video(slug: str) -> Dict[str, Any]:
    """
    Load metadata JSON from the metadata archive directory
    for the given base slug (no extension, no _final).
    """
    meta_path = METADATA_ARCHIVE_DIR / f"{slug}.json"

    if not meta_path.exists():
        raise FileNotFoundError(
            f"Metadata JSON not found for slug '{slug}'"
        )

    with open(meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


def process_video(video_path: Path) -> bool:
    """
    Core per-video logic:

      1. Derive the base slug from the .mp4 filename
         (strip extension and optional '_final').
      2. Load the matching <slug>.json from metadata archive.
      3. Extract title + description from JSON.
      4. Generate a Dropbox public link for the video.
         -> normalize as a direct-download URL.
      5. Build Late bulk-upload CSV.
      6. Send to Late.
      7. If Late accepts, archive the video.
         If Late fails, leave the video in FINAL_DIR for retry.
    """
    scheduled_marker = video_path.with_name(f".{video_path.name}.scheduled")
    if scheduled_marker.exists():
        log_error(
            f"[{NODE_NAME}] Provider acceptance was recorded but archival remains unresolved; skipping duplicate submission.",
            component=NODE_NAME,
        )
        return False

    log_overview(
        f"[{NODE_NAME}] Processing video: REDACTED",
        component=NODE_NAME,
    )

    # -------------------------------
    # 1. Base slug
    # -------------------------------
    base_name = video_path.stem  # filename without extension
    if base_name.endswith("_final"):
        slug = base_name[:-6]
    else:
        slug = base_name

    # -------------------------------
    # 2. Metadata JSON (NEW-style JSON)
    # -------------------------------
    try:
        metadata = load_metadata_for_video(slug)
    except Exception as e:
        log_error(
            f"[{NODE_NAME}] Metadata load failed for slug '{slug}': {type(e).__name__}",
            component=NODE_NAME,
        )
        return False

    title_text = metadata.get("title", slug)
    desc_text = metadata.get("description", "")

    # -------------------------------
    # 3. Dropbox link (cloud path)
    # -------------------------------
    dbx_path = local_path_to_dropbox_path(video_path)

    try:
        raw_link = create_public_link(dbx_path)
        media_url = normalize_dropbox_direct_url(raw_link)
        log_overview(
            f"[{NODE_NAME}] Dropbox public URL for '{video_path.name}': REDACTED",
            component=NODE_NAME,
        )
    except Exception as e:
        msg = str(e)
        if "path/not_found" in msg:
            log_error(
                f"[{NODE_NAME}] Dropbox path not found; likely sync delay. Will retry on next scan.",
                component=NODE_NAME,
            )
        else:
            log_error(
                f"[{NODE_NAME}] Dropbox link creation failed: {type(e).__name__}",
                component=NODE_NAME,
            )
        return False

    # -------------------------------
    # 4. Late CSV
    # -------------------------------
    schedule_time = schedule_time_tomorrow_noon_utc()
    csv_row = build_late_csv_row(
        profiles=LATE_DEFAULT_PROFILES,
        title=title_text,
        desc=desc_text,
        media_url=media_url,
        schedule_time=schedule_time,
        tz=LATE_DEFAULT_TZ,
    )

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_file:
            tmp_path = tmp_file.name

        fieldnames = list(csv_row.keys())
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(csv_row)

        log_detail(
            f"[{NODE_NAME}] Built Late CSV.",
            component=NODE_NAME,
        )
    except Exception as e:
        log_error(
            f"[{NODE_NAME}] Failed to build CSV: {type(e).__name__}",
            component=NODE_NAME,
        )
        return False

    # -------------------------------
    # 5. Persist submission intent before contacting Late
    # -------------------------------
    try:
        with scheduled_marker.open("x", encoding="utf-8") as marker_file:
            marker_file.write("Submission in progress; outcome not yet confirmed.\n")
            marker_file.flush()
            os.fsync(marker_file.fileno())
    except FileExistsError:
        log_error(
            f"[{NODE_NAME}] Submission marker already exists; automatic retry is blocked.",
            component=NODE_NAME,
        )
        return False
    except OSError as e:
        log_error(
            f"[{NODE_NAME}] Could not persist submission marker: {type(e).__name__}; request not sent.",
            component=NODE_NAME,
        )
        return False

    # -------------------------------
    # 6. Send to Late
    # -------------------------------
    try:
        outcome = send_csv_to_late(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    if outcome is not True:
        if outcome is False:
            try:
                scheduled_marker.unlink(missing_ok=True)
            except OSError:
                log_error(
                    f"[{NODE_NAME}] Confirmed rejection but could not clear submission marker; manual review required.",
                    component=NODE_NAME,
                )
        else:
            log_error(
                f"[{NODE_NAME}] Late submission outcome is ambiguous; automatic retry blocked pending manual review.",
                component=NODE_NAME,
            )
        return False

    # -------------------------------
    # 7. Record confirmed acceptance before archival
    # -------------------------------
    try:
        scheduled_marker.write_text(
            "Provider accepted this submission; archival is pending.\n",
            encoding="utf-8",
        )
    except OSError:
        log_error(
            f"[{NODE_NAME}] Provider accepted submission but acceptance marker update failed; manual review required.",
            component=NODE_NAME,
        )
        return False

    if archive_video(video_path):
        try:
            scheduled_marker.unlink(missing_ok=True)
        except OSError:
            log_error(
                f"[{NODE_NAME}] Archived video but could not remove acceptance marker.",
                component=NODE_NAME,
            )
        return True

    # Keep the marker so the polling loop cannot submit the accepted video twice.
    return False


def main_loop(poll_interval: int = 30) -> None:
    """
    Main daemon loop:
      - Scan FINAL_DIR for .mp4 files.
      - For each, attempt to process.
      - Sleep, repeat.

    Infinite retry behavior:
      - If Dropbox says path/not_found (sync delay), we log it and leave
        the file in FINAL_DIR. Next loop (30s later) we try again.
      - Only once Late succeeds do we archive the video.
    """
    log_overview(
        f"[{NODE_NAME}] Daemon started; watching REDACTED",
        component=NODE_NAME,
    )

    while True:
        try:
            if not FINAL_DIR.exists():
                log_error(
                    f"[{NODE_NAME}] Final directory missing: REDACTED",
                    component=NODE_NAME,
                )
            else:
                videos = [
                    p for p in FINAL_DIR.iterdir()
                    if p.is_file() and p.suffix.lower() == ".mp4"
                ]

                if videos:
                    log_overview(
                        f"[{NODE_NAME}] Found {len(videos)} pending video(s).",
                        component=NODE_NAME,
                    )
                else:
                    log_detail(
                        f"[{NODE_NAME}] No videos found in final; sleeping.",
                        component=NODE_NAME,
                    )

                for video_path in videos:
                    try:
                        process_video(video_path)
                    except Exception as e:
                        log_error(
                            f"[{NODE_NAME}] Unhandled error processing video: {type(e).__name__}",
                            component=NODE_NAME,
                        )

        except Exception as loop_err:
            log_error(
                f"[{NODE_NAME}] Daemon loop error: {type(loop_err).__name__}",
                component=NODE_NAME,
            )

        time.sleep(poll_interval)


if __name__ == "__main__":
    main_loop(poll_interval=30)
