import asyncio
import random
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


_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)


class MockShipyardSandboxClient:
    def __init__(
        self,
        sb_url: str,
        *,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.sb_url = sb_url.rstrip("/")
        self._session = session

    @property
    def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=_DEFAULT_TIMEOUT,
            )
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
                raise Exception(
                    f"Failed to exec operation: {response.status} {error_text}"
                )

    async def upload_file(self, path: str, remote_path: str) -> dict:
        """Upload a file to the sandbox"""
        url = f"http://{self.sb_url}/upload"

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

    async def wait_healthy(self, ship_id: str, session_id: str) -> None:
        """Mock wait healthy"""
        loop = 60
        while loop > 0:
            logger.info(f"Checking health for sandbox {ship_id} on {self.sb_url}...")
            if await self.healthy():
                logger.info(f"Sandbox {ship_id} is healthy")
                return
            await asyncio.sleep(1)
            loop -= 1
        raise RuntimeError(f"Sandbox {ship_id} health check timed out")

    async def healthy(self) -> bool:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with self._client.get(
                f"{self.sb_url}/health", timeout=timeout
            ) as response:
                return response.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False


class BoxlitePythonWrapper:
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
        self._python: ShipyardPythonComponent | None = None
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

        await self._sandbox_client.wait_healthy(self.box.id, session_id)

    async def _close_client(self) -> None:
        if self._sandbox_client is not None:
            await self._sandbox_client.close()

    async def shutdown(self) -> None:
        """Gracefully shut down the booter.

        For persistent sandboxes this calls the box's async exit
        hook so state can be preserved.  For temporary sandboxes
        this performs a regular shutdown.
        """
        logger.info(f"Shutting down Boxlite booter for ship: {self.box.id}")
        await self._close_client()
        if self.persistent:
            await self.box.__aexit__(None, None, None)
        else:
            await self.box.shutdown()
        logger.info(f"Boxlite booter for ship: {self.box.id} stopped")

    async def destroy(self) -> None:
        """Forcefully destroy the booter without preserving state."""
        logger.info(f"Destroying Boxlite booter for ship: {self.box.id}")
        await self._close_client()
        await self.box.shutdown()

    async def available(self) -> bool:
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
        if self._sandbox_client is None:
            raise RuntimeError("Boxlite booter has not been booted")
        return await self._sandbox_client.upload_file(path, file_name)
