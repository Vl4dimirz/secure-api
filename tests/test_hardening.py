"""Startup hardening: production must refuse the public repo's default JWT secret."""
import pytest

from app.config import DEFAULT_SECRET, settings
from app.main import _check_production_hardening


async def test_production_refuses_default_secret(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET)
    with pytest.raises(RuntimeError):
        _check_production_hardening()  # forged-JWT risk -> refuse to boot


async def test_production_ok_with_real_secret(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", "a-real-strong-secret-value")
    _check_production_hardening()  # must not raise


async def test_dev_allows_default_secret(monkeypatch):
    monkeypatch.setattr(settings, "environment", "dev")
    monkeypatch.setattr(settings, "secret_key", DEFAULT_SECRET)
    _check_production_hardening()  # dev convenience is fine
