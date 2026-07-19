import logging
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler


LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp_utc": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        event_data = getattr(record, "event_data", None)
        if isinstance(event_data, dict):
            payload.update(event_data)

        return json.dumps(payload, ensure_ascii=True)


class IDSLogger:

    _configured = False

    @staticmethod
    def _configure_root_handlers():
        if IDSLogger._configured:
            return

        root_logger = logging.getLogger("smartids")
        root_logger.setLevel(logging.INFO)

        formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%SZ")

        runtime_handler = RotatingFileHandler(
            LOG_DIR / "runtime.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        runtime_handler.setFormatter(formatter)
        root_logger.addHandler(runtime_handler)

        alert_handler = RotatingFileHandler(
            LOG_DIR / "alerts.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        alert_handler.setFormatter(formatter)

        response_handler = RotatingFileHandler(
            LOG_DIR / "response.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        response_handler.setFormatter(formatter)

        class KeywordFilter(logging.Filter):
            def __init__(self, keywords):
                super().__init__()
                self.keywords = keywords

            def filter(self, record):
                message = record.getMessage().lower()
                return any(keyword in message for keyword in self.keywords)

        alert_handler.addFilter(KeywordFilter(["alert", "attack", "heuristic"]))
        response_handler.addFilter(KeywordFilter(["block", "unblock", "response"]))

        root_logger.addHandler(alert_handler)
        root_logger.addHandler(response_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter("[%(asctime)s][%(levelname)s] %(name)s - %(message)s")
        )
        root_logger.addHandler(console_handler)

        IDSLogger._configured = True

    @staticmethod
    def get_logger(name: str):
        IDSLogger._configure_root_handlers()

        logger = logging.getLogger(f"smartids.{name}")

        if logger.handlers:
            return logger

        logger.setLevel(logging.INFO)

        return logger


def log_event(logger, level: str, message: str, event_data: dict):
    extra = {"event_data": event_data}

    if level == "debug":
        logger.debug(message, extra=extra)
    elif level == "warning":
        logger.warning(message, extra=extra)
    elif level == "error":
        logger.error(message, extra=extra)
    else:
        logger.info(message, extra=extra)
