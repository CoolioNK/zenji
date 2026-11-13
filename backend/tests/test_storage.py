"""Tests: Speicherverwaltung (externe SSD, fehlende SSD, Struktur)."""

from __future__ import annotations

import os
import stat

import pytest

from app.core.config import Settings
from app.core.exceptions import StorageUnavailableError
from app.core.storage import StorageManager


def _settings(tmp_path) -> Settings:
    return Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]


def test_status_meldet_fehlende_ssd_klar(tmp_path):
    manager = StorageManager(_settings(tmp_path / "fehlt"))
    status = manager.status()
    assert status.available is False
    assert "nicht verbunden" in status.message
    assert str(tmp_path / "fehlt") == status.root


def test_ensure_structure_scheitert_mit_verstaendlicher_meldung(tmp_path):
    manager = StorageManager(_settings(tmp_path / "fehlt"))
    with pytest.raises(StorageUnavailableError) as excinfo:
        manager.ensure_structure()
    assert "Es wird kein Ersatzspeicherpfad verwendet" in str(excinfo.value)


def test_ensure_structure_erstellt_spec_ordner(tmp_path):
    ssd = tmp_path / "ssd"
    manager = StorageManager(_settings(ssd))
    ssd.mkdir()
    manager.ensure_structure()
    for name in ("ZENJI", "models", "datasets", "backups", "environments", "logs"):
        assert (ssd / name).is_dir()
    assert (ssd / "ZENJI" / "data").is_dir()
    assert manager.status().available is True


def test_ensure_structure_ist_idempotent_und_behaelt_daten(tmp_path):
    ssd = tmp_path / "ssd"
    ssd.mkdir()
    manager = StorageManager(_settings(ssd))
    manager.ensure_structure()
    marker = manager.data_dir / "wichtig.txt"
    marker.write_text("nicht löschen!")
    manager.ensure_structure()  # zweiter Lauf
    assert marker.read_text() == "nicht löschen!"
    assert (ssd / "ZENJI").is_dir()


def test_schreibgeschuetzte_ssd_wird_erkannt(tmp_path):
    ssd = tmp_path / "ssd"
    ssd.mkdir()
    os.chmod(ssd, stat.S_IREAD | stat.S_IEXEC)
    try:
        manager = StorageManager(_settings(ssd))
        status = manager.status()
        assert status.available is False
        assert "nicht beschreibbar" in status.message
    finally:
        os.chmod(ssd, stat.S_IRWXU)


def test_translate_os_error_erwaehnt_ssd():
    err = StorageManager.translate_os_error(OSError(5, "Input/output error"), "Test")
    assert isinstance(err, StorageUnavailableError)
    assert "SSD" in err.message
    assert err.code == "STORAGE_UNAVAILABLE"
