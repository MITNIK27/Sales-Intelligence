import logging

from app.core.config import get_settings

# ANSI color codes, kept minimal (no colorama/rich dependency) — supported by Windows Terminal,
# PowerShell 5.1+, and every common Unix terminal. Only the level name is colored; timestamp,
# logger name, and message stay plain so the color doesn't fight with terminal themes.
_LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",  # cyan
    logging.INFO: "\033[32m",  # green
    logging.WARNING: "\033[33m",  # yellow
    logging.ERROR: "\033[31m",  # red
    logging.CRITICAL: "\033[41m",  # red background
}
_RESET = "\033[0m"

# Third-party loggers that are useful when actively debugging that specific layer, but otherwise
# drown out application log lines (job lifecycle, request handling, our own errors) — quieted
# regardless of the configured app log level. SQLAlchemy's query echo is controlled separately by
# Settings.sql_echo; this only covers the case where something else enables it.
_QUIET_LOGGERS = ["sqlalchemy.engine", "sqlalchemy.pool", "httpx", "httpcore"]

# google_genai logs a static "AFC is enabled..." INFO line plus a "not recommended, use
# AsyncChat instead" WARNING on every single call — neither is actionable (we're not switching
# to its chat-session API), so this one is quieted a level further than the others above.
_SILENT_LOGGERS = ["google_genai"]


class _HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _LEVEL_COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname:<8}{_RESET}"
        # Drop the "app." prefix every one of our own loggers shares — the level/message carry
        # the signal, the full dotted module path rarely adds anything at a glance.
        record.name = record.name.removeprefix("app.")
        return super().format(record)


def configure_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler()
    formatter = _HumanFormatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.handlers = [handler]

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in _SILENT_LOGGERS:
        logging.getLogger(name).setLevel(logging.ERROR)
