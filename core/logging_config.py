"""Centralized logging configuration using loguru.

Sets up console, file, and UI popup sinks.  Bridges stdlib ``logging``
to loguru via :class:`InterceptHandler` so existing
``logging.getLogger(__name__)`` calls automatically route through loguru
with zero import changes.
"""
import logging
import os
import sys

from loguru import logger

# ---------------------------------------------------------------------------
# Loggers whose ERROR+ messages should be surfaced as UI popups
# ---------------------------------------------------------------------------
_POPUP_LOGGER_PREFIXES: set[str] = {
    "core.sources.whisperlive_manager",
    "core.sources.transcription",
    "core.sources.sound",
    "core.sources.audio_recorder",
    "core.sources.audio_processing",
    "core.sources.ocr",
    "core.llm",
    "core.sinks.audio",
    "core.pipeline",
}


# ---------------------------------------------------------------------------
# InterceptHandler — bridge stdlib logging → loguru
# ---------------------------------------------------------------------------
class InterceptHandler(logging.Handler):
    """A stdlib logging handler that redirects all log records to loguru.

    Install on the root logger to capture output from every library that
    uses ``logging.getLogger()``.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding loguru level
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where the log call actually originated
        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        # Patch the loguru record with the original stdlib logger name so
        # that sinks (especially UIPopupSink) see the correct module name
        # instead of 'logging'.
        logger.patch(lambda r: r.update(name=record.name)).opt(
            depth=depth, exception=record.exc_info
        ).log(level, record.getMessage())


# ---------------------------------------------------------------------------
# UIPopupSink — show ERROR+ from service loggers as popups
# ---------------------------------------------------------------------------
class UIPopupSink:
    """Loguru sink that emits ERROR+ messages from service-critical loggers
    as PyQt6 popup signals.
    """

    def write(self, message) -> None:
        record = message.record
        # Only intercept ERROR (40) and above
        if record["level"].no < 40:
            return

        logger_name = record["name"] or ""
        if not any(logger_name.startswith(prefix) for prefix in _POPUP_LOGGER_PREFIXES):
            return

        try:
            from core.ui.signals import ui_signals

            ui_signals.show_popup.emit(
                {
                    "text": f"⚠️ {record['message']}",
                    "auto_close": 8000,
                    "opacity": 0.9,
                    "is_result": False,
                }
            )
        except Exception:
            # UI not yet initialised — silently ignore
            pass


# ---------------------------------------------------------------------------
# Public setup function
# ---------------------------------------------------------------------------
def setup_logging(config: dict) -> None:
    """Configure loguru sinks based on application config.

    Call once after config is loaded.  Installs:
    1. Colourised **console** sink at the configured level.
    2. **File** sink with rotation/retention/compression.
    3. **UI popup** sink for ERROR+ from service-critical loggers.
    4. ``InterceptHandler`` on the stdlib root logger so every existing
       ``logging.getLogger()`` call routes through loguru.
    """
    # Remove the default loguru stderr sink
    logger.remove()

    # --- Console sink ---
    log_level = config.get("log_level", "INFO").upper()
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # --- File sink ---
    log_file = config.get("log_file", "logs/snapsolve.log")
    log_rotation = config.get("log_rotation", "10 MB")
    log_retention = config.get("log_retention", "7 days")
    if log_file:
        # Ensure directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        logger.add(
            log_file,
            level="DEBUG",  # File always captures everything
            rotation=log_rotation,
            retention=log_retention,
            compression="zip",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
                "{name}:{function}:{line} - {message}"
            ),
            encoding="utf-8",
        )

    # --- UI popup sink ---
    logger.add(UIPopupSink(), level="ERROR")

    # --- Bridge stdlib logging → loguru ---
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # --- Per-logger level overrides for noisy dependencies ---
    default_overrides = {
        "urllib3": "WARNING",
        "PIL": "WARNING",
        "google": "WARNING",
        "httpx": "WARNING",
        "soundcard": "WARNING",
        "matplotlib": "WARNING",
    }
    overrides = {**default_overrides, **config.get("log_levels", {})}
    for logger_name, level_str in overrides.items():
        level = getattr(logging, level_str.upper(), None)
        if level is not None:
            logging.getLogger(logger_name).setLevel(level)

    logger.info("Logging configured — console={}, file={}", log_level, log_file or "disabled")
