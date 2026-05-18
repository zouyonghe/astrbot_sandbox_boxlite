from types import SimpleNamespace

import pytest

from data.plugins.astrbot_sandbox_boxlite import main as plugin_main
from data.plugins.astrbot_sandbox_boxlite import provider as provider_module
from data.plugins.astrbot_sandbox_boxlite.booters import boxlite as boxlite_booter


@pytest.mark.parametrize(
    ("name", "config", "expected_persistent_name"),
    [
        ("Named", {"persistent_name": "boxlite-1"}, "boxlite-1"),
        ("Named", {}, "Named"),
        ("Named", {"sandbox_id": "boxlite-1"}, "boxlite-1"),
    ],
)
def test_boxlite_provider_connect_info_tracks_persistent_name(
    name, config, expected_persistent_name
):
    provider = provider_module.BoxliteSandboxProvider()

    info = provider.build_connect_info(name, config)

    assert info["name"] == name
    assert info["persistent_name"] == expected_persistent_name
    assert 20000 <= info["host_port"] <= 30000


def test_boxlite_provider_connect_info_preserves_configured_host_port():
    provider = provider_module.BoxliteSandboxProvider()

    info = provider.build_connect_info("Named", {"host_port": 23456})

    assert info["host_port"] == 23456


def test_boxlite_sandbox_provider_supports_persistent_reconnect():
    assert provider_module.BoxliteSandboxProvider.supports_persistent_reconnect is True


def test_boxlite_booter_can_import_without_shipyard_plugin(monkeypatch):
    import builtins
    import importlib

    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("data.plugins.astrbot_sandbox_shipyard"):
            raise ModuleNotFoundError(name)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module = importlib.reload(boxlite_booter)

    assert module.BoxliteBooter is boxlite_booter.BoxliteBooter


def test_boxlite_provider_update_connect_info_populates_legacy_persistent_name():
    provider = provider_module.BoxliteSandboxProvider()

    updated = provider.update_connect_info(
        {"sandbox_id": "boxlite-1", "connect_info": {"name": "Legacy"}},
        sandbox_name="Renamed",
    )

    assert updated["name"] == "Renamed"
    assert updated["persistent_name"] == "boxlite-1"


def test_boxlite_provider_update_connect_info_preserves_host_port():
    provider = provider_module.BoxliteSandboxProvider()

    updated = provider.update_connect_info(
        {
            "sandbox_id": "boxlite-1",
            "connect_info": {"name": "Legacy", "host_port": 23456},
        },
        sandbox_name="Renamed",
    )

    assert updated["host_port"] == 23456


def test_boxlite_provider_updates_host_port_after_boot():
    provider = provider_module.BoxliteSandboxProvider()

    updated = provider.update_connect_info_after_boot(
        {"connect_info": {"name": "Boxlite"}},
        SimpleNamespace(host_port=23456),
    )

    assert updated == {"name": "Boxlite", "host_port": 23456}


def test_boxlite_provider_skips_host_port_update_when_missing():
    provider = provider_module.BoxliteSandboxProvider()

    updated = provider.update_connect_info_after_boot(
        {"connect_info": {"name": "Boxlite"}},
        SimpleNamespace(),
    )

    assert updated is None


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
        config={"host_port": 23456},
    )

    assert recorded["persistent"] is True
    assert recorded["persistent_name"] == "boxlite-1"
    assert recorded["resume"] is False
    assert recorded["sandbox_id"] == "boxlite-1"
    assert recorded["host_port"] == 23456
    assert getattr(booter, "sandbox_id") == "boxlite-1"


def test_boxlite_provider_build_create_config_allocates_host_port():
    provider = provider_module.BoxliteSandboxProvider()

    config = provider.build_create_config(SimpleNamespace(), "dashboard")

    assert 20000 <= config["host_port"] <= 30000


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
        config={
            "resume": True,
            "persistent_name": " boxlite-2 ",
            "host_port": 23456,
        },
    )

    assert recorded["persistent"] is True
    assert recorded["persistent_name"] == "boxlite-2"
    assert recorded["resume"] is True
    assert recorded["sandbox_id"] == "boxlite-1"
    assert recorded["host_port"] == 23456
    assert getattr(booter, "sandbox_id") == "boxlite-1"


@pytest.mark.asyncio
async def test_boxlite_provider_rejects_resume_without_host_port(monkeypatch):
    class FakeBooter:
        def __init__(self, **kwargs):
            raise AssertionError("resume path must fail before booting")

    monkeypatch.setattr(provider_module, "BoxliteBooter", FakeBooter)

    provider = provider_module.BoxliteSandboxProvider()

    with pytest.raises(RuntimeError, match="without a stored host_port"):
        await provider.create_booter(
            context=SimpleNamespace(),
            session_id="dashboard",
            sandbox_id="boxlite-1",
            config={"resume": True, "persistent_name": "boxlite-1"},
        )


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
async def test_boxlite_boot_restores_process_signal_handlers(monkeypatch):
    original = {
        boxlite_booter.signal.SIGINT: object(),
        boxlite_booter.signal.SIGTERM: object(),
    }
    active = dict(original)

    def fake_getsignal(signum):
        return active[signum]

    def fake_signal(signum, handler):
        active[signum] = handler

    class FakeRuntime:
        def get_info(self, name):
            return {"name": name}

    class FakeSimpleBox:
        id = "fake-box"

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def start(self):
            # Simulate BoxLite's native signal hook changing process handlers.
            active[boxlite_booter.signal.SIGINT] = "boxlite-int"
            active[boxlite_booter.signal.SIGTERM] = "boxlite-term"

    async def fake_wait_healthy(self, ship_id):
        return None

    monkeypatch.setattr(boxlite_booter.signal, "getsignal", fake_getsignal)
    monkeypatch.setattr(boxlite_booter.signal, "signal", fake_signal)
    monkeypatch.setattr(
        boxlite_booter.boxlite,
        "Boxlite",
        SimpleNamespace(default=lambda: FakeRuntime()),
    )
    monkeypatch.setattr(boxlite_booter.boxlite, "SimpleBox", FakeSimpleBox)
    monkeypatch.setattr(
        boxlite_booter.MockShipyardSandboxClient,
        "wait_healthy",
        fake_wait_healthy,
    )
    monkeypatch.setattr(boxlite_booter, "ShipyardPythonComponent", lambda **_: object())
    monkeypatch.setattr(boxlite_booter, "ShipyardShellComponent", lambda **_: object())
    monkeypatch.setattr(
        boxlite_booter, "ShipyardFileSystemComponent", lambda **_: object()
    )
    monkeypatch.setattr(
        boxlite_booter, "ShipyardFileSystemWrapper", lambda **_: object()
    )

    booter = boxlite_booter.BoxliteBooter()

    await booter.boot("session-1")

    assert active == original


@pytest.mark.asyncio
async def test_boxlite_restore_does_not_create_when_persistent_box_missing(monkeypatch):
    class FakeRuntime:
        def get_info(self, name):
            return None

    class FakeSimpleBox:
        def __init__(self, **kwargs):
            raise AssertionError("resume path must not create a new box")

    monkeypatch.setattr(
        boxlite_booter.boxlite,
        "Boxlite",
        SimpleNamespace(default=lambda: FakeRuntime()),
    )
    monkeypatch.setattr(boxlite_booter.boxlite, "SimpleBox", FakeSimpleBox)

    booter = boxlite_booter.BoxliteBooter(
        persistent=True,
        persistent_name="boxlite-1",
        resume=True,
    )

    with pytest.raises(RuntimeError, match="could not be resumed"):
        await booter.boot("session-1")


@pytest.mark.asyncio
async def test_boxlite_booter_uses_configured_host_port(monkeypatch):
    recorded = {}

    class FakeRuntime:
        def get_info(self, name):
            return {"name": name}

    class FakeSimpleBox:
        id = "fake-box"

        def __init__(self, **kwargs):
            recorded.update(kwargs)

        async def start(self):
            return None

    async def fake_wait_healthy(self, ship_id):
        recorded["health_url"] = self.sb_url
        recorded["health_ship_id"] = ship_id

    monkeypatch.setattr(
        boxlite_booter.boxlite,
        "Boxlite",
        SimpleNamespace(default=lambda: FakeRuntime()),
    )
    monkeypatch.setattr(boxlite_booter.boxlite, "SimpleBox", FakeSimpleBox)
    monkeypatch.setattr(
        boxlite_booter.MockShipyardSandboxClient,
        "wait_healthy",
        fake_wait_healthy,
    )
    monkeypatch.setattr(boxlite_booter, "ShipyardPythonComponent", lambda **_: object())
    monkeypatch.setattr(boxlite_booter, "ShipyardShellComponent", lambda **_: object())
    monkeypatch.setattr(
        boxlite_booter, "ShipyardFileSystemComponent", lambda **_: object()
    )
    monkeypatch.setattr(
        boxlite_booter, "ShipyardFileSystemWrapper", lambda **_: object()
    )

    booter = boxlite_booter.BoxliteBooter(
        persistent=True,
        persistent_name="boxlite-1",
        resume=True,
        host_port=23456,
    )

    await booter.boot("session-1")

    assert recorded["ports"] == [{"host_port": 23456, "guest_port": 8123}]
    assert recorded["health_url"] == "http://127.0.0.1:23456"
    assert booter.host_port == 23456


@pytest.mark.asyncio
async def test_boxlite_booter_cleans_up_client_when_health_check_fails(monkeypatch):
    calls = []

    class FakeRuntime:
        def get_info(self, name):
            return {"name": name}

    class FakeSimpleBox:
        id = "fake-box"

        def __init__(self, **kwargs):
            pass

        async def start(self):
            calls.append("start")

        async def __aexit__(self, exc_type, exc, tb):
            calls.append("exit")

    async def fake_wait_healthy(self, ship_id):
        calls.append(("wait", ship_id))
        raise RuntimeError("not healthy")

    async def fake_close(self):
        calls.append("close-client")

    monkeypatch.setattr(
        boxlite_booter.boxlite,
        "Boxlite",
        SimpleNamespace(default=lambda: FakeRuntime()),
    )
    monkeypatch.setattr(boxlite_booter.boxlite, "SimpleBox", FakeSimpleBox)
    monkeypatch.setattr(
        boxlite_booter.MockShipyardSandboxClient,
        "wait_healthy",
        fake_wait_healthy,
    )
    monkeypatch.setattr(
        boxlite_booter.MockShipyardSandboxClient,
        "close",
        fake_close,
    )
    monkeypatch.setattr(boxlite_booter, "ShipyardPythonComponent", lambda **_: object())
    monkeypatch.setattr(boxlite_booter, "ShipyardShellComponent", lambda **_: object())
    monkeypatch.setattr(
        boxlite_booter, "ShipyardFileSystemComponent", lambda **_: object()
    )
    monkeypatch.setattr(
        boxlite_booter, "ShipyardFileSystemWrapper", lambda **_: object()
    )

    booter = boxlite_booter.BoxliteBooter(
        persistent=True,
        persistent_name="boxlite-1",
        resume=True,
        host_port=23456,
    )

    with pytest.raises(RuntimeError, match="not healthy"):
        await booter.boot("session-1")

    assert calls == ["start", ("wait", "fake-box"), "close-client", "exit"]
    assert booter.box is None
    assert booter._sandbox_client is None


def test_restore_signal_handlers_logs_failures(monkeypatch):
    calls = []

    def fake_signal(*args, **kwargs):
        raise ValueError("no signal")

    def fake_debug(message, *args, **kwargs):
        calls.append((message, args, kwargs))

    monkeypatch.setattr(boxlite_booter.signal, "signal", fake_signal)
    monkeypatch.setattr(boxlite_booter.logger, "debug", fake_debug)

    boxlite_booter._restore_signal_handlers({boxlite_booter.signal.SIGINT: object()})

    assert calls
    assert "Failed to restore BoxLite signal handler" in calls[0][0]
    assert calls[0][1][0] == boxlite_booter.signal.SIGINT


@pytest.mark.asyncio
async def test_boxlite_terminate_detaches_even_if_cleanup_fails(monkeypatch):
    calls = []

    class FakeProvider:
        provider_id = "boxlite"

    async def fake_cleanup(provider_id):
        calls.append(("cleanup", provider_id))
        raise RuntimeError("cleanup failed")

    def fake_detach(provider_id):
        calls.append(("detach", provider_id))

    monkeypatch.setattr(plugin_main, "cleanup_sandbox_provider", fake_cleanup)
    monkeypatch.setattr(plugin_main, "detach_sandbox_provider", fake_detach)

    plugin = plugin_main.BoxliteSandboxRuntimePlugin.__new__(
        plugin_main.BoxliteSandboxRuntimePlugin
    )
    plugin.provider = FakeProvider()

    with pytest.raises(RuntimeError, match="cleanup failed"):
        await plugin.terminate()

    assert calls == [("cleanup", "boxlite"), ("detach", "boxlite")]


@pytest.mark.asyncio
async def test_boxlite_upload_file_uses_configured_base_url(tmp_path):
    posted = {}

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeSession:
        closed = False

        def post(self, url, *, data, timeout):
            posted["url"] = url
            posted["timeout"] = timeout
            return FakeResponse()

    local_file = tmp_path / "payload.txt"
    local_file.write_text("payload", encoding="utf-8")
    client = boxlite_booter.MockShipyardSandboxClient("http://127.0.0.1:12345")
    await client.close()
    client._session = FakeSession()

    result = await client.upload_file(str(local_file), "/tmp/payload.txt")

    assert result["success"] is True
    assert posted["url"] == "http://127.0.0.1:12345/upload"


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_result", "expected_stdout", "expected_stderr", "expected_exit_code"),
    [
        ({"output": "ok\n", "error": "", "exit_code": 0}, "ok\n", "", 0),
        ({"stdout": "ok\n", "stderr": "", "returncode": 0}, "ok\n", "", 0),
        ({"data": {"output": "ok\n", "error": ""}}, "ok\n", "", 0),
        ({"data": {"output": "", "error": "boom"}}, "", "boom", 1),
    ],
)
async def test_boxlite_shell_wrapper_normalizes_shipyard_results(
    raw_result, expected_stdout, expected_stderr, expected_exit_code
):
    calls = []

    class FakeShipyardShell:
        async def exec(
            self,
            command,
            cwd=None,
            env=None,
            timeout=30,
            shell=True,
            background=False,
        ):
            calls.append((command, cwd, env, timeout, shell, background))
            return raw_result

    wrapper = boxlite_booter.BoxliteShellWrapper(FakeShipyardShell())

    result = await wrapper.exec(
        "pwd",
        cwd="/workspace",
        env={"A": "B"},
        timeout=5,
        shell=True,
        background=False,
    )

    assert calls == [("pwd", "/workspace", {"A": "B"}, 5, True, False)]
    assert result["stdout"] == expected_stdout
    assert result["stderr"] == expected_stderr
    assert result["exit_code"] == expected_exit_code


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
