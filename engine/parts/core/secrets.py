# engine/parts/core/secrets.py

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# -----------------------------
# Absolute, systemd-safe paths
# -----------------------------
# REDACTED — production secret-storage locations.
ENV_PATH = Path("REDACTED")
JSON_PATH = Path("REDACTED")

# -----------------------------
# Internal Secret Cache
# -----------------------------
SECRET_CACHE = {}

# -----------------------------
# Load .env (optional)
# -----------------------------
def load_env_file():
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)
        return True
    return False

# -----------------------------
# Load JSON secrets (optional)
# -----------------------------
def load_json_file():
    if JSON_PATH.exists():
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    SECRET_CACHE.update(data)
                    return True
        except Exception:
            pass
    return False

# -----------------------------
# Unified loader
# -----------------------------
def initialize_secrets():
    """
    Loads secrets from:
    1. OS environment
    2. .env (absolute path)
    3. secrets.json (absolute path)
    """
    load_env_file()
    load_json_file()

# Load automatically at import
initialize_secrets()

# -----------------------------
# Get a secret
# -----------------------------
def get_secret(name: str) -> str:
    """
    Priority:
    1. OS environment
    2. .env
    3. secrets.json
    """
    val = os.getenv(name)
    if val and val.strip():
        return val.strip()

    val = SECRET_CACHE.get(name)
    if val and str(val).strip():
        return str(val).strip()

    raise RuntimeError(f"Missing required secret: {name}")

# -----------------------------
# Diagnostics helper
# -----------------------------
def secret_exists(name: str) -> bool:
    val = os.getenv(name)
    if val and val.strip():
        return True
    val = SECRET_CACHE.get(name)
    return bool(val and str(val).strip())
