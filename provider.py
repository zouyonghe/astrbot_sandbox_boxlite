from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from astrbot.core.computer.booters.base import ComputerBooter
from astrbot.core.star.context import Context

from .booters.boxlite import BoxliteBooter

BootHook = Callable[[Context, str, str, dict], Awaitable[ComputerBooter]]


class BoxliteSandboxProvider:
    provider_id = "boxlite"
    capabilities = {"shell", "python", "filesystem"}
    supports_persistent_reconnect = True
    tool_names: set[str] = set()

    def __init__(
        self,
        boot_hook: BootHook | None = None,
        *,
        plugin_config: Mapping[str, Any] | None = None,
    ) -> None:
        self.plugin_config: dict[str, Any] = (
            dict(plugin_config) if plugin_config is not None else {}
        )
        self._boot_hook = boot_hook

    def build_create_config(self, context: Context, session_id: str) -> dict:
        return {}

    def build_connect_info(self, sandbox_name: str, config: dict) -> dict:
        return {
            "name": sandbox_name,
            "persistent_name": config.get("persistent_name") or sandbox_name,
        }

    def update_connect_info(self, record: dict, *, sandbox_name: str) -> dict:
        connect_info = dict(record.get("connect_info") or {})
        connect_info["name"] = sandbox_name
        return connect_info

    def get_idle_timeout(self, context: Context, session_id: str) -> float:
        return 0.0

    async def create_booter(
        self, context: Context, session_id: str, sandbox_id: str, config: dict
    ) -> ComputerBooter:
        if self._boot_hook is not None:
            return await self._boot_hook(context, session_id, sandbox_id, config)
        client = BoxliteBooter(
            persistent=True,
            persistent_name=str(config.get("persistent_name") or sandbox_id).strip(),
            resume=bool(config.get("resume", False)),
        )
        await client.boot(uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex)
        setattr(client, "sandbox_id", sandbox_id)
        return client

    async def destroy_booter(self, booter: ComputerBooter, record: dict) -> None:
        destroy = getattr(booter, "destroy", None)
        if callable(destroy):
            await destroy()
            return
        await booter.shutdown()
