import importlib

import pytest


def test_config_rejects_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///bad.db")
    monkeypatch.setenv("JWT_SECRET_KEY", "secret")
    import core.config as config

    config.get_settings.cache_clear()
    with pytest.raises(RuntimeError):
        config.get_settings()


def test_config_requires_jwt_secret(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("JWT_SECRET_KEY", "")
    import core.config as config

    importlib.reload(config)
    with pytest.raises(RuntimeError):
        config.get_settings()
