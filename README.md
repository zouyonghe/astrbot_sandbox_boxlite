# astrbot_sandbox_boxlite

<div align="center">

English ｜ <a href="./README_cn.md">简体中文</a>

</div>

`astrbot_sandbox_boxlite` is the BoxLite local sandbox driver plugin for AstrBot. It is a lightweight choice when you only need shell, Python, and file operations, without browser or GUI-specific tools.

## Key Features

1. 🛡️ Provides the `boxlite` sandbox driver for AstrBot.
2. 💻 Supports shell, Python, and file operations.
3. 📦 Syncs local AstrBot Skills when the sandbox boots.
4. ⚡ Runs lighter than remote sandbox services.

## Quick Start

### Install the Plugin

Clone the plugin into AstrBot's plugin directory:

```bash
git clone https://github.com/zouyonghe/astrbot_sandbox_boxlite.git data/plugins/astrbot_sandbox_boxlite
```

The current implementation reuses code from the Shipyard plugin, so keep the Shipyard plugin source available locally as well:

```bash
git clone https://github.com/zouyonghe/astrbot_sandbox_shipyard.git data/plugins/astrbot_sandbox_shipyard
```

Then restart AstrBot, or reload plugins from the plugin management page.

### Enable the BoxLite Sandbox Driver

In the AstrBot dashboard, enable sandbox mode and select the `boxlite` driver.

Configuration path:

- `provider_settings.computer_use_runtime`: `sandbox`
- `provider_settings.sandbox.booter`: `boxlite`

## Configuration

This plugin does not expose driver-specific configuration fields.

## Best For

- Use this plugin when you want a lighter sandbox runtime and only need shell, Python, and file operations.
- It does not register browser tools.
- It does not register GUI tools such as screenshot, mouse, or keyboard tools.

## Requirements and Limitations

- AstrBot must support external sandbox driver plugins.
- The Python dependency from `requirements.txt`: `boxlite`.
- The Python `shipyard` package is required because the BoxLite implementation reuses Shipyard-compatible filesystem wrappers.
- The current implementation reuses code from the Shipyard plugin, so `astrbot_sandbox_shipyard` should remain present in the same `data/plugins` tree.
- Browser automation is not included.
- GUI-specific tools are not included.

## Troubleshooting

- If BoxLite fails to load, make sure the Shipyard plugin tree is still present locally.
- If file operations behave unexpectedly, verify that the shared Shipyard-compatible dependency is installed in the AstrBot environment.
