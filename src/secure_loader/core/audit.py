"""Persistent audit log for firmware flash events."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import platformdirs

_audit: logging.Logger | None = None
_AUDIT_LOGGER_NAME = "secureloader.audit"


def audit_logger() -> logging.Logger:
    global _audit
    if _audit is None:
        log_dir = Path(platformdirs.user_log_dir("secureloader"))
        log_dir.mkdir(parents=True, exist_ok=True)
        _audit = logging.getLogger(_AUDIT_LOGGER_NAME)
        _audit.propagate = False
        if not _audit.handlers:
            handler = RotatingFileHandler(
                log_dir / "audit.log",
                maxBytes=1_000_000,
                backupCount=5,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            _audit.addHandler(handler)
        _audit.setLevel(logging.INFO)
    return _audit


def log_flash(port: str, fw_version: str, outcome: str) -> None:
    """Record a firmware flash attempt to the rotating audit log."""
    audit_logger().info("FLASH port=%s fw_version=%s outcome=%s", port, fw_version, outcome)
