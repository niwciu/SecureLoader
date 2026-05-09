"""Tests for the audit log module."""

from __future__ import annotations

import logging

import pytest

from secure_loader.core.audit import _AUDIT_LOGGER_NAME, log_flash


@pytest.fixture(autouse=True)
def reset_audit_logger():
    import secure_loader.core.audit as _mod

    _mod._audit = None
    logger = logging.getLogger(_AUDIT_LOGGER_NAME)
    logger.handlers.clear()
    yield
    _mod._audit = None
    logger.handlers.clear()


def test_audit_log_file_is_created(tmp_path, monkeypatch):
    monkeypatch.setattr("platformdirs.user_log_dir", lambda *a, **kw: str(tmp_path))
    log_flash("COM3", "0x01020304", "success")
    assert (tmp_path / "audit.log").exists()


def test_flash_entry_appears_in_log(tmp_path, monkeypatch):
    monkeypatch.setattr("platformdirs.user_log_dir", lambda *a, **kw: str(tmp_path))
    log_flash("COM3", "0x01020304", "success")
    content = (tmp_path / "audit.log").read_text()
    assert "FLASH" in content
    assert "COM3" in content
    assert "0x01020304" in content
    assert "success" in content


def test_multiple_entries_are_appended(tmp_path, monkeypatch):
    monkeypatch.setattr("platformdirs.user_log_dir", lambda *a, **kw: str(tmp_path))
    log_flash("COM3", "0x01020304", "success")
    log_flash("COM3", "0x01020305", "error: timeout")
    lines = [line for line in (tmp_path / "audit.log").read_text().splitlines() if line.strip()]
    assert len(lines) == 2
    assert "0x01020305" in lines[1]
    assert "error: timeout" in lines[1]
