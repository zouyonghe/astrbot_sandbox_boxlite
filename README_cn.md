# astrbot_sandbox_boxlite

<div align="center">

<a href="./README.md">English</a> ｜ 简体中文

</div>

`astrbot_sandbox_boxlite` 是 AstrBot 的 BoxLite 本地沙盒驱动插件，适合只需要 Shell、Python 和文件操作的轻量场景。它不包含浏览器或 GUI 工具，启动和运行都更简单。

## 主要功能

1. 🛡️ 为 AstrBot 提供 `boxlite` 沙盒驱动。
2. 💻 支持 Shell、Python 和文件操作。
3. 📦 沙盒启动时会同步本地 AstrBot Skills。
4. ⚡ 相比远程沙盒服务，本地运行更轻量。

## 快速开始

### 安装插件

把插件克隆到 AstrBot 插件目录：

```bash
git clone https://github.com/zouyonghe/astrbot_sandbox_boxlite.git data/plugins/astrbot_sandbox_boxlite
```

当前实现会复用 Shipyard 插件中的部分代码，因此需要同时保留 Shipyard 插件源码：

```bash
git clone https://github.com/zouyonghe/astrbot_sandbox_shipyard.git data/plugins/astrbot_sandbox_shipyard
```

然后重启 AstrBot，或在插件管理页重新加载插件。

### 启用 BoxLite 沙盒驱动

先在 AstrBot 核心配置中启用沙盒模式，并把沙盒驱动设置为 `boxlite`：

```json
{
  "provider_settings": {
    "computer_use_runtime": "sandbox",
    "sandbox": {
      "booter": "boxlite"
    }
  }
}
```

## 配置项

这个插件当前没有额外的专属配置项。

## 适合场景

- 当你只需要 Shell、Python 和文件操作，并希望运行时更轻量时，可以优先使用这个插件。
- 它不会注册浏览器工具。
- 它不会注册截图、鼠标、键盘等 GUI 工具。

## 依赖与限制

- 需要使用支持外部沙盒驱动插件的 AstrBot 版本。
- 依赖 `requirements.txt` 中的 `boxlite`。
- 需要 Python `shipyard` 包，因为当前 BoxLite 实现复用了兼容 Shipyard 的文件系统包装逻辑。
- 当前实现会复用 Shipyard 插件中的代码，因此 `astrbot_sandbox_shipyard` 需要与它一起存在于同一个 `data/plugins` 目录树中。
- 不包含浏览器自动化能力。
- 不包含 GUI 工具能力。

## 仓库地址

- GitHub: https://github.com/zouyonghe/astrbot_sandbox_boxlite
