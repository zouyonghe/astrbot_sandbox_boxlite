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


@pytest.mark.asyncio
async def test_boxlite_booter_available_uses_health_probe(monkeypatch):
    calls = []

    async def fake_probe(self):
        calls.append(self.sb_url)
        return True

    monkeypatch.setattr(
        boxlite_booter.MockShipyardSandboxClient,
        "healthy",
        fake_probe,
        raising=False,
    )

    booter = boxlite_booter.BoxliteBooter()
    booter.box = SimpleNamespace(id="fake-box")
    booter._sandbox_client = boxlite_booter.MockShipyardSandboxClient(
        "http://127.0.0.1:12345"
    )

    assert await booter.available() is True
    assert calls == ["http://127.0.0.1:12345"]


@pytest.mark.asyncio
async def test_boxlite_booter_available_returns_false_before_boot():
    booter = boxlite_booter.BoxliteBooter()

    assert await booter.available() is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_result", "expected_text", "expected_error"),
    [
        ({"output": "hello\n", "error": ""}, "hello\n", ""),
        ({"stdout": "hello\n", "stderr": ""}, "hello\n", ""),
        ({"data": {"output": "hello\n", "error": ""}}, "hello\n", ""),
        (
            {"data": {"output": {"text": "hello\n", "images": []}, "error": ""}},
            "hello\n",
            "",
        ),
        ({"output": "", "error": "boom"}, "", "boom"),
    ],
)
async def test_boxlite_python_wrapper_normalizes_shipyard_results(
    raw_result, expected_text, expected_error
):
    calls = []

    class FakeShipyardPython:
        async def exec(self, code, kernel_id=None, timeout=30, silent=False):
            calls.append((code, kernel_id, timeout, silent))
            return raw_result

    wrapper = boxlite_booter.BoxlitePythonWrapper(FakeShipyardPython())

    result = await wrapper.exec("print('hello')", timeout=5, silent=True)

    assert calls == [("print('hello')", None, 5, True)]
    assert result["data"]["output"]["text"] == expected_text
    assert result["data"]["output"]["images"] == []
    assert result["data"]["error"] == expected_error


def test_normalize_python_result_accepts_tuple_images():
    result = boxlite_booter._normalize_python_result(
        {
            "output": {
                "text": "hello",
                "images": ("a.png", "b.png"),
            },
            "error": "",
        }
    )

    assert result["data"]["output"]["text"] == "hello"
    assert result["data"]["output"]["images"] == ["a.png", "b.png"]


def test_normalize_python_result_drops_string_images():
    result = boxlite_booter._normalize_python_result(
        {
            "output": {
                "text": "hello",
                "images": "not-a-list",
            },
            "error": "",
        }
    )

    assert result["data"]["output"]["images"] == []


@pytest.mark.asyncio
async def test_boxlite_booter_shutdown_closes_sandbox_client():
    close_calls = []

    class FakeBox:
        id = "fake-box"

        async def shutdown(self):
            pass

    class FakeClient:
        async def close(self):
            close_calls.append("close")

    booter = boxlite_booter.BoxliteBooter()
    booter.box = FakeBox()
    booter._sandbox_client = FakeClient()

    await booter.shutdown()

    assert close_calls == ["close"]
    assert booter.box is None
    assert booter._sandbox_client is None


@pytest.mark.asyncio
async def test_boxlite_booter_destroy_closes_sandbox_client():
    close_calls = []

    class FakeBox:
        id = "fake-box"

        async def shutdown(self):
            pass

    class FakeClient:
        async def close(self):
            close_calls.append("close")

    booter = boxlite_booter.BoxliteBooter()
    booter.box = FakeBox()
    booter._sandbox_client = FakeClient()

    await booter.destroy()

    assert close_calls == ["close"]
    assert booter.box is None
    assert booter._sandbox_client is None


@pytest.mark.asyncio
async def test_boxlite_booter_components_unavailable_after_shutdown():
    class FakeBox:
        id = "fake-box"

        async def shutdown(self):
            pass

    class FakeClient:
        async def close(self):
            pass

    booter = boxlite_booter.BoxliteBooter()
    booter.box = FakeBox()
    booter._sandbox_client = FakeClient()
    booter._fs = object()
    booter._python = object()
    booter._shell = object()

    await booter.shutdown()

    assert booter._fs is None
    assert booter._python is None
    assert booter._shell is None
    with pytest.raises(RuntimeError, match="not been booted"):
        booter.fs
    with pytest.raises(RuntimeError, match="not been booted"):
        booter.python
    with pytest.raises(RuntimeError, match="not been booted"):
        booter.shell
