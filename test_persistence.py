from types import SimpleNamespace

import pytest

from data.plugins.astrbot_sandbox_boxlite import provider as provider_module
from data.plugins.astrbot_sandbox_boxlite.booters import boxlite as boxlite_booter


@pytest.mark.parametrize(
    ("name", "config", "expected_persistent_name"),
    [
        ("Named", {"persistent_name": "boxlite-1"}, "boxlite-1"),
        ("Named", {}, "Named"),
    ],
)
def test_boxlite_provider_connect_info_tracks_persistent_name(
    name, config, expected_persistent_name
):
    provider = provider_module.BoxliteSandboxProvider()

    info = provider.build_connect_info(name, config)

    assert info["name"] == name
    assert info["persistent_name"] == expected_persistent_name


def test_boxlite_sandbox_provider_supports_persistent_reconnect():
    assert provider_module.BoxliteSandboxProvider.supports_persistent_reconnect is True


def test_boxlite_provider_update_connect_info_populates_legacy_persistent_name():
    provider = provider_module.BoxliteSandboxProvider()

    updated = provider.update_connect_info(
        {"connect_info": {"name": "Legacy"}},
        sandbox_name="Renamed",
    )

    assert updated["name"] == "Renamed"
    assert updated["persistent_name"] == "Renamed"


@pytest.mark.asyncio
async def test_boxlite_provider_passes_persistent_reuse_flags(monkeypatch):
    recorded = {}

    class FakeBooter:
        def __init__(self, **kwargs):
            recorded.update(kwargs)
            self.sandbox_id = kwargs.get("sandbox_id")

        async def boot(self, session_id: str):
            recorded["boot_session_id"] = session_id

    monkeypatch.setattr(provider_module, "BoxliteBooter", FakeBooter)

    provider = provider_module.BoxliteSandboxProvider()
    booter = await provider.create_booter(
        context=SimpleNamespace(),
        session_id="dashboard",
        sandbox_id="boxlite-1",
        config={},
    )

    assert recorded["persistent"] is True
    assert recorded["persistent_name"] == "boxlite-1"
    assert recorded["sandbox_id"] == "boxlite-1"
    assert getattr(booter, "sandbox_id") == "boxlite-1"


@pytest.mark.asyncio
async def test_boxlite_provider_strips_explicit_persistent_name(monkeypatch):
    recorded = {}

    class FakeBooter:
        def __init__(self, **kwargs):
            recorded.update(kwargs)
            self.sandbox_id = kwargs.get("sandbox_id")

        async def boot(self, session_id: str):
            recorded["boot_session_id"] = session_id

    monkeypatch.setattr(provider_module, "BoxliteBooter", FakeBooter)

    provider = provider_module.BoxliteSandboxProvider()
    booter = await provider.create_booter(
        context=SimpleNamespace(),
        session_id="dashboard",
        sandbox_id="boxlite-1",
        config={"resume": True, "persistent_name": " boxlite-2 "},
    )

    assert recorded["persistent"] is True
    assert recorded["persistent_name"] == "boxlite-2"
    assert recorded["sandbox_id"] == "boxlite-1"
    assert getattr(booter, "sandbox_id") == "boxlite-1"


@pytest.mark.asyncio
async def test_boxlite_provider_destroy_booter_prefers_destroy():
    calls = []

    class FakeBooter:
        async def destroy(self):
            calls.append("destroy")

        async def shutdown(self):
            calls.append("shutdown")

    provider = provider_module.BoxliteSandboxProvider()

    await provider.destroy_booter(FakeBooter(), {"retention_policy": "temporary"})

    assert calls == ["destroy"]


@pytest.mark.asyncio
async def test_boxlite_provider_destroy_booter_falls_back_to_shutdown():
    calls = []

    class FakeBooter:
        async def shutdown(self):
            calls.append("shutdown")

    provider = provider_module.BoxliteSandboxProvider()

    await provider.destroy_booter(FakeBooter(), {"retention_policy": "temporary"})

    assert calls == ["shutdown"]


@pytest.mark.asyncio
async def test_boxlite_provider_reports_persistent_box_exists(monkeypatch):
    calls = []

    class FakeRuntime:
        def get_info(self, name):
            calls.append(name)
            return object()

    monkeypatch.setattr(
        boxlite_booter.boxlite,
        "Boxlite",
        SimpleNamespace(default=lambda: FakeRuntime()),
    )

    provider = provider_module.BoxliteSandboxProvider()

    exists = await provider.check_persistent_sandbox_exists(
        {"connect_info": {"persistent_name": "boxlite-1"}}
    )

    assert exists is True
    assert calls == ["boxlite-1"]


@pytest.mark.asyncio
async def test_boxlite_provider_reports_missing_persistent_box(monkeypatch):
    class FakeRuntime:
        def get_info(self, name):
            return None

    monkeypatch.setattr(
        boxlite_booter.boxlite,
        "Boxlite",
        SimpleNamespace(default=lambda: FakeRuntime()),
    )

    provider = provider_module.BoxliteSandboxProvider()

    exists = await provider.check_persistent_sandbox_exists(
        {"connect_info": {"persistent_name": "boxlite-1"}}
    )

    assert exists is False
