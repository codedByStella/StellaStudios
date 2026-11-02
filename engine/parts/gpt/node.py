# engine/parts/gpt/node.py

import json
import random
import re
import unicodedata
from pathlib import Path

from openai import OpenAI

from engine.parts.core.logger import log_overview, log_detail, log_error
from engine.parts.core.secrets import get_secret


# ---------------------------------------------------------
# CONSTANTS & PATHS
# ---------------------------------------------------------

NODE = "GPT"

BASE_DIR = Path(__file__).resolve().parent
PRESETS = BASE_DIR / "presets"
CREATIVE_DIR = PRESETS / "creative"
MODEL_DIR = PRESETS / "model"
SCHEMA_PATH = PRESETS / "schema.json"

# Dropbox authoritative output directory
# REDACTED — production filesystem location.
METADATA_PENDING = Path("REDACTED")
METADATA_PENDING.mkdir(parents=True, exist_ok=True)

# Shared secret resolution keeps OS environment variables authoritative.
OPENAI_KEY = get_secret("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY)


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def load_schema():
    log_detail(f"[{NODE}] Loading output schema.")
    with open(SCHEMA_PATH, "r") as f:
        return json.load(f)


def load_model_preset(mode: str):
    if mode == "auto":
        preset = MODEL_DIR / "defaults.json"
    elif mode == "debug":
        preset = MODEL_DIR / "debugging.json"
    else:
        raise ValueError("Invalid mode for model preset load.")

    log_detail(f"[{NODE}] Loading model preset.")
    with open(preset, "r") as f:
        return json.load(f)


def load_creative_preset():
    presets = list(CREATIVE_DIR.glob("*.json"))
    if not presets:
        raise RuntimeError("No creative presets in presets/creative")

    choice = random.choice(presets)
    log_detail(f"[{NODE}] Loading randomly selected creative preset.")
    with open(choice, "r") as f:
        return json.load(f)


def make_slug(title: str) -> str:
    if not title:
        return "clip"

    parts = title.strip().split()
    base = " ".join(parts[:-1]) if len(parts) > 1 else parts[0]
    base = base.lower().replace(" ", "_")
    safe = "".join(ch for ch in base if ch.isalnum() or ch == "_")
    return safe or "clip"


def validate_output(parsed: dict, schema: dict) -> None:
    """Validate deterministic constraints declared by the output schema.

    Prompt-quality and semantic requirements remain model-guidance; this
    validator enforces machine-checkable structure and literal constraints.
    """
    if not isinstance(parsed, dict):
        raise RuntimeError("Model output must be a JSON object.")

    requirements = schema.get("output_requirements", {})
    fmt = requirements.get("format", {})
    required = fmt.get("required_keys", [])

    if not isinstance(required, list) or not required:
        raise RuntimeError("Schema has no required output keys.")

    missing = [key for key in required if key not in parsed]
    if missing:
        raise RuntimeError("Model output is missing required fields.")

    if fmt.get("no_additional_top_level_keys") and set(parsed) != set(required):
        raise RuntimeError("Model output contains unexpected top-level fields.")

    fields = requirements.get("fields", {})
    for name in required:
        value = parsed.get(name)
        field_schema = fields.get(name, {})
        if field_schema.get("type") == "string" and not isinstance(value, str):
            raise RuntimeError("Model output contains a field with an invalid type.")
        if not isinstance(value, str):
            continue
        if fmt.get("no_escaped_newlines_in_values") and ("\n" in value or "\r" in value):
            raise RuntimeError("Model output contains a newline in a field value.")

        forbidden = list(fmt.get("forbidden_characters_in_values", [])) + list(field_schema.get("forbidden_characters", []))
        if any(char in value for char in forbidden):
            raise RuntimeError("Model output contains a forbidden character.")

        word_range = field_schema.get("word_count_range")
        if word_range:
            count = len(value.split())
            if not word_range[0] <= count <= word_range[1]:
                raise RuntimeError("Model output violates a field word-count constraint.")

        if field_schema.get("ascii_only") and not value.isascii():
            raise RuntimeError(f"Field '{name}' must contain ASCII characters only.")

    title = parsed.get("title", "")
    title_schema = fields.get("title", {})
    if title_schema.get("exact_single_emoji_at_end"):
        if not title or unicodedata.category(title[-1]) != "So":
            raise RuntimeError("Title must end with one emoji.")
        if any(not char.isascii() for char in title[:-1]):
            raise RuntimeError("Title contains non-ASCII characters before its final emoji.")
        if title_schema.get("no_punctuation_except_final_emoji"):
            if re.search(r"[^A-Za-z0-9 ]", title[:-1]):
                raise RuntimeError("Title contains punctuation other than its final emoji.")

    description = parsed.get("description", "")
    description_schema = fields.get("description", {})
    sentence_range = description_schema.get("sentence_count_range")
    if sentence_range:
        sentences = [part for part in re.split(r"[.!?]+(?:\s+|$)", description.strip()) if part.strip()]
        if not sentence_range[0] <= len(sentences) <= sentence_range[1]:
            raise RuntimeError("Description violates its sentence-count constraint.")

    hashtag_range = description_schema.get("required_hashtags_range")
    if hashtag_range:
        hashtag_count = len(re.findall(r"#[A-Za-z0-9_]+", description))
        if not hashtag_range[0] <= hashtag_count <= hashtag_range[1]:
            raise RuntimeError("Model output violates the description hashtag constraint.")

    video = parsed.get("video", "")
    video_schema = fields.get("video", {})
    must_include = video_schema.get("must_include", {})
    required_phrases = {
        "vertical_format": "vertical format 9:16",
        "no_people_or_beings": "no people or beings",
        "continuous_environment": "continuous environment",
        "readable_spatial_structure": "readable spatial structure",
        "unified_lighting": "unified lighting",
        "consistent_motion": "consistent motion",
        "explicit_audio_presence_phrase": must_include.get("explicit_audio_presence_phrase", ""),
        "emotionally_safe_soft_grounded": "emotionally safe and softly grounded",
        "no_scene_transitions": "no scene transitions",
    }
    for key, phrase in required_phrases.items():
        if phrase and must_include.get(key, True) and phrase.casefold() not in video.casefold():
            raise RuntimeError("Video prompt is missing a required schema phrase.")

    palette_options = must_include.get("explicit_palette", [])
    if palette_options and not any(f"{palette} palette" in video.casefold() for palette in palette_options):
        raise RuntimeError("Video prompt must specify an allowed palette.")

    voice = parsed.get("voice", "")
    voice_schema = fields.get("voice", {})
    prefix = voice_schema.get("must_begin_with")
    if prefix and not voice.startswith(prefix):
        raise RuntimeError("Voice text does not begin with its required prefix.")
    if voice_schema.get("fragment_structure") == "1-3 fragments separated by commas or ellipses":
        fragments = [part.strip() for part in re.split(r",|\.\.\.", voice) if part.strip()]
        if not 1 <= len(fragments) <= 3:
            raise RuntimeError("Voice text violates its fragment-count constraint.")


def call_gpt(model_cfg, system_prompt, user_prompt, max_output_tokens):
    """
    Chat Completions API w/ HARD JSON ENFORCEMENT.
    GPT-5.1 requires:
      - response_format={"type":"json_object"}
      - messages MUST contain the word "json"
      - system role MUST explicitly demand pure JSON
    """

    model = model_cfg.get("model", "gpt-4.1")
    gen_cfg = model_cfg.get("generation", {})
    temperature = gen_cfg.get("temperature", 0.9)
    top_p = gen_cfg.get("top_p", 1.0)
    max_completion_tokens = gen_cfg.get("max_completion_tokens", max_output_tokens)

    # FORCE JSON CAGE — THIS IS THE FIX
    enforced_system = (
        "Respond ONLY with valid JSON. No markdown, no commentary, "
        "no whitespace before or after. Begin with '{' and end with '}'. "
        "If you output anything that is not valid JSON, the process fails.\n\n"
        + system_prompt
    )

    enforced_user = (
        "The output MUST be EXACTLY ONE JSON OBJECT. "
        "Do not add text outside the JSON. "
        "Do not explain. Do not comment.\n\n"
        "Return ONLY JSON.\n\n"
        + user_prompt
    )

    log_detail(
        f"[{NODE}] Calling GPT model={model}, temp={temperature}, max={max_completion_tokens}"
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": enforced_system},
            {"role": "user", "content": enforced_user}
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
        top_p=top_p,
        max_completion_tokens=max_completion_tokens
    )

    raw = resp.choices[0].message.content
    log_detail(f"[{NODE}] GPT JSON chars={len(raw)}")
    return raw


# ---------------------------------------------------------
# MAIN ENTRYPOINT
# ---------------------------------------------------------

def generate_gpt_output(mode="auto"):

    log_overview(f"[GPT] Node start (mode={mode})")

    try:
        schema = load_schema()
        required = schema["output_requirements"]["format"]["required_keys"]

        model_cfg = load_model_preset(mode)
        creative = load_creative_preset()

        system_prompt = creative.get("system_prompt", "")
        user_prompt = creative.get("user_prompt", "")

        max_tokens = model_cfg.get("generation", {}).get("max_completion_tokens", 1200)

        raw = call_gpt(model_cfg, system_prompt, user_prompt, max_tokens)

        try:
            parsed = json.loads(raw)
        except Exception:
            raise RuntimeError("Invalid JSON returned.")

        validate_output(parsed, schema)

        slug = make_slug(parsed.get("title", "clip"))
        outfile = METADATA_PENDING / f"{slug}.json"
        if outfile.exists():
            raise RuntimeError("Generated slug already exists; refusing to overwrite metadata.")

        with open(outfile, "x", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2, ensure_ascii=True)

        log_overview("[GPT] Success.")
        return {"success": True, "slug": slug, "output": parsed}

    except Exception as e:
        log_error(f"[GPT] FAILURE: {type(e).__name__}")
        return {"success": False, "error": type(e).__name__}


__all__ = ["generate_gpt_output"]
