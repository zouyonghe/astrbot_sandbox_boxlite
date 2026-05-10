import asyncio
import random
import signal
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from types import FrameType
from typing import Any

import aiohttp
import boxlite
from shipyard import FileSystemComponent as ShipyardFileSystemComponent
from shipyard.python import PythonComponent as ShipyardPythonComponent
from shipyard.shell import ShellComponent as ShipyardShellComponent

from astrbot.api import logger
from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.computer.olayer import (
    FileSystemComponent,
    PythonComponent,
    ShellComponent,
)
from data.plugins.astrbot_sandbox_shipyard.booters.shipyard import (
    ShipyardFileSystemWrapper,
)

_HEALTH_PROBE_TIMEOUT = aiohttp.ClientTimeout(total=5)
_HEALTH_PROBE_INTERVAL = 1
_HEALTH_PROBE_MAX_ATTEMPTS = 60
SignalHandler = Callable[[int, FrameType | None], Any] | int | None


@contextmanager
def capture_signal_handlers() -> Iterator[None]:
    handlers: dict[int, SignalHandler] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        handlers[signum] = signal.getsignal(signum)
    try:
        yield
    finally:
        _restore_signal_handlers(handlers)


def _restore_signal_handlers(handlers: dict[int, SignalHandler]) -> None:
    for signum, handler in handlers.items():
        try:
            signal.signal(signum, handler)
        except (OSError, ValueError):
            # signal.signal() is only valid from the main thread.
            logger.debug(
                "Failed to restore BoxLite signal handler for signum=%s",
                signum,
                exc_info=True,
            )


class SandboxClientError(Exception):
    """Raised when a sandbox HTTP operation returns a non-2xx status."""

    def __init__(
        self, message: str, *, status: int | None = None, body: str = ""
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class MockShipyardSandboxClient:
    def __init__(self, sb_url: str) -> None:
        self.sb_url = sb_url.rstrip("/")
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        self._session: aiohttp.ClientSession | None = aiohttp.ClientSession(
            connector=connector
        )

    @property
    def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise RuntimeError("Sandbox HTTP client session has been closed")
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _exec_operation(
        self,
        ship_id: str,
        operation_type: str,
        payload: dict[str, Any],
        session_id: str,
    ) -> dict[str, Any]:
        headers = {"X-SESSION-ID": session_id}
        async with self._client.post(
            f"{self.sb_url}/{operation_type}",
            json=payload,
            headers=headers,
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                error_text = await response.text()
                raise SandboxClientError(
                    f"Failed to exec operation: {response.status} {error_text}",
                    status=response.status,
                    body=error_text,
                )

    async def upload_file(self, path: str, remote_path: str) -> dict:
        """Upload a file to the sandbox"""
        url = f"{self.sb_url}/upload"

        try:
            # Read file content
            with open(path, "rb") as f:
                file_content = f.read()

            # Create multipart form data
            data = aiohttp.FormData()
            data.add_field(
                "file",
                file_content,
                filename=remote_path.split("/")[-1],
                content_type="application/octet-stream",
            )
            data.add_field("file_path", remote_path)

            timeout = aiohttp.ClientTimeout(total=120)  # 2 minutes for file upload

            async with self._client.post(url, data=data, timeout=timeout) as response:
                if response.status == 200:
                    logger.info(
                        "[Computer] File uploaded to Boxlite sandbox: %s",
                        remote_path,
                    )
                    return {
                        "success": True,
                        "message": "File uploaded successfully",
                        "file_path": remote_path,
                    }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Server returned {response.status}: {error_text}",
                        "message": "File upload failed",
                    }

        except aiohttp.ClientError as e:
            logger.error(f"Failed to upload file: {e}")
            return {
                "success": False,
                "error": f"Connection error: {str(e)}",
                "message": "File upload failed",
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "File upload timeout",
                "message": "File upload failed",
            }
        except FileNotFoundError:
            logger.error(f"File not found: {path}")
            return {
                "success": False,
                "error": f"File not found: {path}",
                "message": "File upload failed",
            }
        except Exception as e:
            logger.error(f"Unexpected error uploading file: {e}")
            return {
                "success": False,
                "error": f"Internal error: {str(e)}",
                "message": "File upload failed",
            }

    async def wait_healthy(
        self,
        ship_id: str,
        *,
        timeout: aiohttp.ClientTimeout | None = None,
        interval: float | None = None,
        max_attempts: int | None = None,
    ) -> None:
        """Wait until the sandbox health endpoint responds.

        Args:
            ship_id: Identifier used in log messages.
            timeout: Per-request timeout for each probe. Defaults to
                ``_HEALTH_PROBE_TIMEOUT``.
            interval: Seconds to wait between probes. Defaults to
                ``_HEALTH_PROBE_INTERVAL``.
            max_attempts: Maximum probe attempts before giving up. Defaults to
                ``_HEALTH_PROBE_MAX_ATTEMPTS``.
        """
        probe_timeout = timeout or _HEALTH_PROBE_TIMEOUT
        probe_interval = interval if interval is not None else _HEALTH_PROBE_INTERVAL
        probe_attempts = (
            max_attempts if max_attempts is not None else _HEALTH_PROBE_MAX_ATTEMPTS
        )

        for attempt in range(probe_attempts):
            logger.info(f"Checking health for sandbox {ship_id} on {self.sb_url}...")
            if await self.healthy(timeout=probe_timeout):
                logger.info(f"Sandbox {ship_id} is healthy")
                return
            await asyncio.sleep(probe_interval)
        raise RuntimeError(f"Sandbox {ship_id} health check timed out")

    async def healthy(self, *, timeout: aiohttp.ClientTimeout | None = None) -> bool:
        try:
            async with self._client.get(
                f"{self.sb_url}/health", timeout=timeout or _HEALTH_PROBE_TIMEOUT
            ) as response:
                return response.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False


class BoxlitePythonWrapper(PythonComponent):
    def __init__(self, python: ShipyardPythonComponent) -> None:
        self._python = python

    async def exec(
        self,
        code: str,
        kernel_id: str | None = None,
        timeout: int = 30,
        silent: bool = False,
    ) -> dict[str, Any]:
        result = await self._python.exec(
            code, kernel_id=kernel_id, timeout=timeout, silent=silent
        )
        return _normalize_python_result(result)


def _normalize_python_result(result: dict[str, Any]) -> dict[str, Any]:
    data = result.get("data")
    payload = data if isinstance(data, dict) else result
    output = payload.get("output", payload.get("stdout", ""))
    error = payload.get("error", payload.get("stderr", "")) or ""
    images: list[dict[str, Any]] = []

    if isinstance(output, dict):
        images_value = output.get("images", [])
        if isinstance(images_value, list):
            images = images_value
        elif isinstance(images_value, Sequence) and not isinstance(
            images_value, (str, bytes)
        ):
            images = list(images_value)
        text = output.get("text", output.get("stdout", "")) or ""
    else:
        text = output or ""

    return {"data": {"output": {"text": text, "images": images}, "error": error}}


class BoxliteBooter(ComputerBooter):
    def __init__(
        self,
        *,
        persistent: bool = False,
        persistent_name: str | None = None,
        sandbox_id: str | None = None,
    ) -> None:
        self.persistent = persistent
        self.persistent_name = persistent_name
        self.sandbox_id = sandbox_id
        self._sandbox_client: MockShipyardSandboxClient | None = None
        self._python: BoxlitePythonWrapper | None = None
        self._shell: ShipyardShellComponent | None = None
        self._ship_fs: ShipyardFileSystemComponent | None = None
        self._fs: ShipyardFileSystemWrapper | None = None
        self.box: boxlite.SimpleBox | None = None

    @property
    def mocked(self) -> MockShipyardSandboxClient | None:
        """Backward-compatible alias for _sandbox_client."""
        return self._sandbox_client

    @mocked.setter
    def mocked(self, value: MockShipyardSandboxClient | None) -> None:
        """Backward-compatible alias for _sandbox_client."""
        self._sandbox_client = value

    async def boot(self, session_id: str) -> None:
        logger.info(
            f"Booting(Boxlite) for session: {session_id}, this may take a while..."
        )
        random_port = random.randint(20000, 30000)
        box_name = self.persistent_name if self.persistent else None
        with capture_signal_handlers():
            self.box = boxlite.SimpleBox(
                image="soulter/shipyard-ship",
                name=box_name,
                auto_remove=not self.persistent,
                reuse_existing=self.persistent,
                memory_mib=512,
                cpus=1,
                ports=[
                    {
                        "host_port": random_port,
                        "guest_port": 8123,
                    }
                ],
            )
            await self.box.start()
        logger.info(f"Boxlite booter started for session: {session_id}")
        self._sandbox_client = MockShipyardSandboxClient(
            sb_url=f"http://127.0.0.1:{random_port}"
        )
        self._python = BoxlitePythonWrapper(
            ShipyardPythonComponent(
                client=self._sandbox_client,  # type: ignore
                ship_id=self.box.id,
                session_id=session_id,
            )
        )
        self._shell = ShipyardShellComponent(
            client=self._sandbox_client,  # type: ignore
            ship_id=self.box.id,
            session_id=session_id,
        )
        self._ship_fs = ShipyardFileSystemComponent(
            client=self._sandbox_client,  # type: ignore
            ship_id=self.box.id,
            session_id=session_id,
        )
        self._fs = ShipyardFileSystemWrapper(
            _shipyard_fs=self._ship_fs, _shipyard_shell=self._shell
        )

        await self._sandbox_client.wait_healthy(self.box.id)

    async def _close_client(self) -> None:
        if self._sandbox_client is not None:
            try:
                await self._sandbox_client.close()
            finally:
                self._sandbox_client = None
                self._python = None
                self._shell = None
                self._ship_fs = None
                self._fs = None

    async def shutdown(self) -> None:
        """Gracefully shut down the booter.

        For persistent sandboxes this calls the box's async exit
        hook so state can be preserved.  For temporary sandboxes
        this performs a regular shutdown.
        """
        if self.box is None:
            logger.warning("Boxlite booter shutdown called before boot")
            return
        logger.info(f"Shutting down Boxlite booter for ship: {self.box.id}")
        await self._close_client()
        if self.persistent:
            await self.box.__aexit__(None, None, None)
        else:
            await self.box.shutdown()
        self.box = None
        logger.info("Boxlite booter for ship stopped")

    async def destroy(self) -> None:
        """Forcefully destroy the booter without preserving state."""
        if self.box is None:
            logger.warning("Boxlite booter destroy called before boot")
            return
        logger.info(f"Destroying Boxlite booter for ship: {self.box.id}")
        await self._close_client()
        await self.box.shutdown()
        self.box = None

    async def available(self) -> bool:
        if self.box is None:
            return False
        if self._sandbox_client is None:
            return False
        return await self._sandbox_client.healthy()

    @property
    def fs(self) -> FileSystemComponent:
        if self._fs is None:
            raise RuntimeError("Boxlite booter has not been booted")
        return self._fs

    @property
    def python(self) -> PythonComponent:
        if self._python is None:
            raise RuntimeError("Boxlite booter has not been booted")
        return self._python

    @property
    def shell(self) -> ShellComponent:
        if self._shell is None:
            raise RuntimeError("Boxlite booter has not been booted")
        return self._shell

    async def upload_file(self, path: str, file_name: str) -> dict:
        """Upload file to sandbox"""
        if self.box is None:
            raise RuntimeError("Boxlite booter has not been booted")
        if self._sandbox_client is None:
            raise RuntimeError("Boxlite booter has not been booted")
        return await self._sandbox_client.upload_file(path, file_name)
