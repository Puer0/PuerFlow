import importlib.util
import time
from pathlib import Path

import pytest


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakePage:
    async def close(self):
        return None


class _FakeContext:
    async def new_page(self):
        return _FakePage()

    async def close(self):
        return None


class _FakeBrowser:
    async def new_context(self, **kwargs):
        return _FakeContext()


@pytest.mark.asyncio
async def test_session_manager_evicts_expired_sessions_first(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    mod = _load_module(
        "playwright_service_session_manager_expired",
        root / "python" / "playwright-service" / "session_manager.py",
    )

    monkeypatch.setattr(mod, "MAX_SESSIONS", 2)
    monkeypatch.setattr(mod, "SESSION_TTL_SECONDS", 10)

    manager = mod.BrowserSessionManager(_FakeBrowser())
    await manager.get_or_create_session("a")
    await manager.get_or_create_session("b")

    manager.sessions["a"].last_accessed = time.time() - 60
    manager.sessions["b"].last_accessed = time.time()

    await manager.get_or_create_session("c")
    assert sorted(manager.sessions.keys()) == ["b", "c"]


@pytest.mark.asyncio
async def test_session_manager_evicts_oldest_when_none_expired(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    mod = _load_module(
        "playwright_service_session_manager_oldest",
        root / "python" / "playwright-service" / "session_manager.py",
    )

    monkeypatch.setattr(mod, "MAX_SESSIONS", 2)
    monkeypatch.setattr(mod, "SESSION_TTL_SECONDS", 10_000)

    manager = mod.BrowserSessionManager(_FakeBrowser())
    await manager.get_or_create_session("a")
    await manager.get_or_create_session("b")

    manager.sessions["a"].last_accessed = time.time() - 60
    manager.sessions["b"].last_accessed = time.time() - 10

    await manager.get_or_create_session("c")
    assert sorted(manager.sessions.keys()) == ["b", "c"]


@pytest.mark.asyncio
async def test_session_manager_get_stats_is_lock_safe():
    root = Path(__file__).resolve().parents[3]
    mod = _load_module(
        "playwright_service_session_manager_stats",
        root / "python" / "playwright-service" / "session_manager.py",
    )

    manager = mod.BrowserSessionManager(_FakeBrowser())
    await manager.get_or_create_session("a")
    stats = await manager.get_stats()
    assert stats["active_sessions"] == 1
    assert stats["sessions"][0]["session_id"] == "a"

