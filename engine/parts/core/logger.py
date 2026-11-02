# engine/parts/core/logger.py
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Resolve the base engine directory dynamically
BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = BASE_DIR / "diagnostics"
LOG_DIR.mkdir(parents=True, exist_ok=True)

OVERVIEW_PATH = LOG_DIR / "engine_overview.log"
DETAIL_PATH = LOG_DIR / "engine_detail.log"


# -------------------------------------------------------------------
# INTERNAL: build rotating handlers
# -------------------------------------------------------------------
def _build_handler(path: Path, level: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path,
        maxBytes=2_000_000,  # 2 MB
        backupCount=3
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


# -------------------------------------------------------------------
# INITIALIZE CORE LOGGERS
# -------------------------------------------------------------------
def init_loggers():
    """
    Sets up:
      engine.overview.* → INFO+
      engine.detail.*   → DEBUG+
    Only initializes one time.
    """
    if getattr(init_loggers, "_initialized", False):
        return

    # Overview: high-level diagnostics
    overview_logger = logging.getLogger("engine.overview")
    overview_logger.setLevel(logging.INFO)
    overview_logger.addHandler(_build_handler(OVERVIEW_PATH, logging.INFO))
    overview_logger.propagate = False

    # Detail: deep dives, node internals
    detail_logger = logging.getLogger("engine.detail")
    detail_logger.setLevel(logging.DEBUG)
    detail_logger.addHandler(_build_handler(DETAIL_PATH, logging.DEBUG))
    detail_logger.propagate = False

    init_loggers._initialized = True


# -------------------------------------------------------------------
# GET COMPONENT-SCOPED LOGGERS
# -------------------------------------------------------------------
def _get_component_loggers(component: str):
    init_loggers()
    overview = logging.getLogger(f"engine.overview.{component}")
    detail = logging.getLogger(f"engine.detail.{component}")
    return overview, detail


# -------------------------------------------------------------------
# PUBLIC LOGGING HELPERS (GLOBAL API)
# These are what scheduler, pipeline, and nodes call.
# -------------------------------------------------------------------
def log_overview(message: str, component: str = "engine"):
    overview, _ = _get_component_loggers(component)
    overview.info(message)


def log_detail(message: str, component: str = "engine"):
    _, detail = _get_component_loggers(component)
    detail.debug(message)


def log_error(message: str, component: str = "engine"):
    overview, detail = _get_component_loggers(component)
    overview.error(message)
    detail.error(message)
