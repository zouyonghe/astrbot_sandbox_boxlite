from astrbot.api.star import Context, Star, register
from astrbot.core.computer.computer_client import (
    cleanup_sandbox_provider,
    detach_sandbox_provider,
    register_sandbox_provider,
)

from .provider import BoxliteSandboxProvider


@register(
    "astrbot_sandbox_boxlite",
    "AstrBot Team",
    "Boxlite sandbox runtime provider for AstrBot",
    "0.1.0",
)
class BoxliteSandboxRuntimePlugin(Star):
    def __init__(self, context: Context, config=None) -> None:
        super().__init__(context)
        self.provider = BoxliteSandboxProvider(plugin_config=config)
        register_sandbox_provider(self.provider, replace=True)

    async def terminate(self) -> None:
        await cleanup_sandbox_provider(self.provider.provider_id)
        detach_sandbox_provider(self.provider.provider_id)
