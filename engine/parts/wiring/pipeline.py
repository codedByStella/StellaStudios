# engine/parts/wiring/pipeline.py
import sys
import time
from pathlib import Path

# Ensure root path is visible
sys.path.insert(0, "REDACTED — production application root")

# Logging API
from engine.parts.core.logger import log_overview, log_detail, log_error

# Engine types
from engine.parts.core.types import NodeResult

# Node entrypoints (FULL PACKAGE PATHS)
from engine.parts.music.node import select_music_track as generate_music
from engine.parts.gpt.node import generate_gpt_output
from engine.parts.elevenlab.node import generate_voiceover
from engine.parts.sora.node import generate_sora_video
from engine.parts.subtitler.node import generate_subtitles
from engine.parts.stitcher.node import stitch_video

# Archiver
from engine.parts.wiring.archiver import archive_artifacts

def run_pipeline(mode: str = "auto"):
    """
    Full end-to-end ASMR pipeline (GPT-first architecture):
      1. GPT content generation
      2. Music selection
      3. ElevenLabs voice creation
      4. Subtitler (phrase segmentation → timed ASS subtitles)
      5. Sora video generation
      6. Stitcher video assembly (+ burned-in subtitles)
      7. Archiver renames and files artifacts
      8. (Legacy uploader call — daemon handles real posts)
    """

    log_overview("[PIPELINE] Start", component="pipeline")
    start_time = time.time()

    try:
        # ---------------------------------------------
        # 1. GPT
        # ---------------------------------------------
        log_detail("[PIPELINE] Running GPT node...", component="pipeline")
        gpt_result = generate_gpt_output(mode=mode)
        if not gpt_result["success"]:
            raise RuntimeError(gpt_result["error"])

        slug = gpt_result["slug"]
        log_overview("[PIPELINE] GPT OK", component="pipeline")

        # ---------------------------------------------
        # 2. MUSIC
        # ---------------------------------------------
        log_detail("[PIPELINE] Running MUSIC node...", component="pipeline")
        music_result = generate_music(slug=slug)
        if not music_result["success"]:
            raise RuntimeError(music_result["error"])

        log_overview("[PIPELINE] MUSIC OK", component="pipeline")

        # ---------------------------------------------
        # 3. ELEVENLABS
        # ---------------------------------------------
        log_detail("[PIPELINE] Running ELEVENLABS node...", component="pipeline")
        eleven_result = generate_voiceover(mode=mode, slug=slug)
        if not eleven_result["success"]:
            raise RuntimeError(eleven_result["error"])

        log_overview("[PIPELINE] ELEVENLABS OK", component="pipeline")

        # ---------------------------------------------
        # 4. SUBTITLER (NEW)
        # ---------------------------------------------
        log_detail("[PIPELINE] Running SUBTITLER node...", component="pipeline")
        sub_result = generate_subtitles(slug)
        if not sub_result["success"]:
            raise RuntimeError(sub_result["error"])

        log_overview("[PIPELINE] SUBTITLER OK", component="pipeline")

        # ---------------------------------------------
        # 5. SORA
        # ---------------------------------------------
        log_detail("[PIPELINE] Running SORA node...", component="pipeline")
        sora_result = generate_sora_video(mode=mode, slug=slug)
        if not sora_result["success"]:
            raise RuntimeError(sora_result["error"])

        log_overview("[PIPELINE] SORA OK", component="pipeline")

        # ---------------------------------------------
        # 6. STITCHER
        # ---------------------------------------------
        log_detail("[PIPELINE] Running STITCHER node...", component="pipeline")
        stitch_result = stitch_video({"slug": slug})
        if not stitch_result["success"]:
            raise RuntimeError(stitch_result["error"])

        log_overview("[PIPELINE] STITCHER OK", component="pipeline")

        # ---------------------------------------------
        # 7. ARCHIVER
        # ---------------------------------------------
        log_detail("[PIPELINE] Running ARCHIVER...", component="pipeline")
        archive_result = archive_artifacts(slug)

        if not archive_result["success"]:
            raise RuntimeError(archive_result["error"])

        canonical_title = archive_result["title"]
        log_overview(
            "[PIPELINE] ARCHIVER OK",
            component="pipeline"
        )

        # ---------------------------------------------
        # DONE
        # ---------------------------------------------
        total = time.time() - start_time

        log_overview(
            f"[PIPELINE] COMPLETE (mode={mode}) in {total:.2f}s",
            component="pipeline"
        )

        return NodeResult(
            node="PIPELINE",
            success=True,
            data={"title": canonical_title}
        )

    except Exception as e:
        log_error(
            f"[PIPELINE] FAILED (mode={mode}) — {type(e).__name__}",
            component="pipeline"
        )
        return NodeResult(
            node="PIPELINE",
            success=False,
            error=type(e).__name__
        )
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    result = run_pipeline(mode)
    # optional: print small output to satisfy scheduler's stdout capture
    print(result)
    sys.exit(0 if result.success else 1)
