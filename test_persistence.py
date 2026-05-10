from types import SimpleNamespace

import pytest

from data.plugins.astrbot_sandbox_boxlite import provider as provider_module


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


@pytest.mark.asyncio
async def test_boxlite_provider_passes_persistent_reuse_flags(monkeypatch):
    recorded = {}

    class FakeBooter:
        def __init__(self, **kwargs):
            recorded.update(kwargs)

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
    assert getattr(booter, "sandbox_id") == "boxlite-1"


@pytest.mark.asyncio
async def test_boxlite_provider_strips_explicit_persistent_name(monkeypatch):
    recorded = {}

    class FakeBooter:
        def __init__(self, **kwargs):
            recorded.update(kwargs)

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
    assert getattr(booter, "sandbox_id") == "boxlite-1"
