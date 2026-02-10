from __future__ import annotations

import asyncio
from dataclasses import dataclass

from coworkingbot.services.content_store import (
    get_client_content,
    reset_client_content,
    set_client_content_field,
)


@dataclass(frozen=True)
class _DummySettings:
    pass


@dataclass(frozen=True)
class _DummyContext:
    settings: _DummySettings


def test_content_store_defaults(monkeypatch, tmp_path) -> None:
    path = tmp_path / "content.json"
    monkeypatch.setenv("CONTENT_STORE_PATH", str(path))
    ctx = _DummyContext(settings=_DummySettings())

    content = asyncio.run(get_client_content(ctx))

    assert "Добро пожаловать" in content.welcome
    assert "Правила" in content.rules
    assert "Поддержка" in content.support
    assert content.announcement == ""


def test_content_store_update_and_reset(monkeypatch, tmp_path) -> None:
    path = tmp_path / "content.json"
    monkeypatch.setenv("CONTENT_STORE_PATH", str(path))
    ctx = _DummyContext(settings=_DummySettings())

    updated = asyncio.run(set_client_content_field(ctx, "announcement", "Тестовый баннер"))
    assert updated.announcement == "Тестовый баннер"

    after_update = asyncio.run(get_client_content(ctx))
    assert after_update.announcement == "Тестовый баннер"

    reset = asyncio.run(reset_client_content(ctx))
    assert reset.announcement == ""
