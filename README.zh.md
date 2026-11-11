# Argus

**中文** | [English](README.md)

> ArduPilot 无人机的 Web 地面站。

[![CI](https://github.com/L-X-Yao/argus/actions/workflows/ci.yml/badge.svg)](https://github.com/L-X-Yao/argus/actions/workflows/ci.yml)
![Version](https://img.shields.io/github/v/tag/L-X-Yao/argus?label=version&color=blue)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Tests](https://img.shields.io/badge/tests-3000%2B%20passing-brightgreen.svg)
![i18n](https://img.shields.io/badge/i18n-10%20languages-orange.svg)

<p align="center"><img src="docs/screenshots/hero.png" alt="Argus GCS — 地图、HUD 与遥测面板" width="900"></p>

## 定位

Argus 是面向 ArduPilot 的 **Web 地面站**：一个浏览器界面，支持桌面、平板和手机，内置 10 种语言。没有托管版本：自己运行 Python 后端，或解压 Windows 发布包（已内置 Python），再用浏览器打开。

> **当前状态**：ArduPilot 已通过 CI 中的 ArduCopter SITL 和真实飞控台架验证，尚未经过正式飞行测试。每项功能验证到什么程度，见 [docs/VERIFICATION.md](docs/VERIFICATION.md)。不支持 PX4：Argus 不会向 PX4 飞控发送任何命令。
>
> **2026 年 11 月起仅做维护**：修复缺陷和安全问题，不再计划新功能。见[项目状态](#项目状态)。

为什么还需要一个 GCS：Argus 运行在浏览器标签页里，手上的设备不用安装任何东西，还能通过 USB 直连飞控（WebSerial）。

| 现有 GCS | 区别 |
|---|---|
| [QGroundControl](https://qgroundcontrol.com/) | 原生应用，每台设备都要安装 |
| [Mission Planner](https://ardupilot.org/planner/) | Windows 应用 |
| FlytBase 等云平台 | 闭源，绑定单一厂商 |

现在要执行真实飞行任务，请用 QGroundControl 或 Mission Planner：两者都经过飞行验证并在持续开发，Argus 两样都不具备。

## 功能一览

| 分类 | 功能 |
|---|---|
| **连接** | TCP / UDP / Serial / WebSerial（浏览器直连 USB，遥测和基础控制无需后端） |
| **协议** | MAVLink v2，仅 ArduPilot（已做 SITL 和台架验证，未正式试飞） |
| **机型** | 多旋翼、固定翼、VTOL、地面车、水下潜航器 |
| **地图** | 8 种图源（高德、Google、OSM、Esri、CartoDB；天地图需自备密钥），各自受[其服务条款](#地图数据)约束 + 3D 地形（MapLibre GL）+ 离线 mbtiles |
| **航线** | 航点 / 曲线 / 盘旋 / 测绘网格 / 交叉 / 螺旋 / 环绕 + 地形剖面与净空检查 |
| **格式** | `.waypoints` (MP) / `.plan` (QGC) / `.gpx` / `.kml` 导入导出 |
| **参数** | 元数据驱动 UI（描述/范围/单位/枚举/位掩码），树形视图，差异导出，恢复默认 |
| **校准** | 罗盘、加速度计、陀螺仪、水平、气压计向导，实时进度 |
| **RTK** | NTRIP 客户端，HTTP/1.0 + ICY-200 协商，RTCM 流式注入 |
| **固件** | 在后端保存 `.apj` 文件，在线固件浏览器，重启至 Bootloader（不含刷写功能） |
| **编队** | 多机仪表盘，每架飞机实时遥测 |
| **视频** | 后端经 ffmpeg 转发 RTSP、HTTP 和 RTMP 视频流，AR 航点叠加，截图 |
| **HUD** | PFD（姿态/速度/高度/罗盘/风向），实时图表，EKF 状态 |
| **语音** | 10 语言本地化语音播报（模式、电量、高度、航点） |
| **多语言** | 10 种语言（中/英/日/韩/德/法/西/葡/俄/阿）+ RTL |
| **离线** | PWA + Service Worker，mbtiles 支持，瓦片缓存（5000 条 LRU） |
| **桌面** | `src-tauri/` 里有一份 Tauri v2 配置，从未构建过：没有图标，没有 CI 任务，也不再计划 |
| **安全** | Token 认证，跨站与 DNS 重绑定请求拦截，SSRF + 路径穿越防护，statustext 过滤 |

## 安装

### Windows 发布包

适用于 Windows 10 和 11（x64）。Python 和所有依赖库都在 zip 里，不需要安装任何东西。

1. 从[最新发布](https://github.com/L-X-Yao/argus/releases/latest)下载 `Argus_GCS_vX.Y.Z_amd64.zip` 和 `SHA256SUMS.txt`。
2. 校验下载的文件，因为 zip 没有代码签名：

   ```powershell
   (Get-FileHash Argus_GCS_vX.Y.Z_amd64.zip -Algorithm SHA256).Hash   # 应与 SHA256SUMS.txt 一致
   gh attestation verify Argus_GCS_vX.Y.Z_amd64.zip --repo L-X-Yao/argus   # 可选，需要 GitHub CLI
   ```

3. 解压后双击 `Argus地面站.bat`，浏览器会打开 `http://127.0.0.1:8100`。

`启动仿真器.bat` 启动内置模拟器。zip 里的 `README.txt` 写有同样的步骤。

### 从源码运行

适用于 Linux、macOS 和 Windows。需要 Python 3.10 或更高版本，以及 Node.js。CI 运行在 Node 24 和 Python 3.14 上，Windows 发布包内置的也是 Python 3.14。视频功能需要 PATH 里有 `ffmpeg`。

```bash
git clone https://github.com/L-X-Yao/argus && cd argus
npm install && npm run build   # 构建 Web 界面到 dist/
pip install -e .               # 后端及其依赖
python run.py                  # 在 http://127.0.0.1:8100 提供全部服务
```

## 连接

Argus 只监听本机。要从其他设备访问，先读 [SECURITY.md](SECURITY.md)：那需要设置令牌。

### 真实硬件

插上飞控，打开 `http://127.0.0.1:8100`，从下拉框选择串口。网络链路则填地址，例如 `tcp:192.168.1.10:5760` 或 `udp:14550`。

### ArduPilot SITL

```bash
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550
python run.py
# 打开 UI，点击 "SITL" 快速连接按钮
```

### 内置 MAVLink 模拟器（无需飞控、无需 SITL）

```bash
python run.py --sim            # 同时启动后端 + simulator.py
# 连接到 "tcp:localhost:5770"
```

模拟器（`scripts/simulator.py`）发送仿真遥测数据（GPS、姿态、电量消耗、心跳），响应解锁/锁定/模式切换命令。

### WebSerial（USB 直连）

用 Chrome/Edge 打开 Argus，点击 **USB** 按钮，选择飞控。遥测、解锁/锁定/模式/RTL、参数读写、航线上传/下载/清除、围栏上传、日志列表/下载、全部 5 种校准类型均通过 WebSerial 和内置 TypeScript MAVLink v2 编解码器直连。地图瓦片、地形剖面、参数说明、视频和固件文件存储仍依赖 Python 后端，没有后端时新的地图瓦片无法加载。RTK（NTRIP）和 MAVLink 控制台需要飞控通过后端连接，WebSerial 直连时不可用。

### 地图数据

地图瓦片、地形高程以及 ArduPilot 的固件和参数列表都不属于 Argus。使用相应功能时，后端从第三方服务器获取这些数据，并受各服务器条款约束，清单见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

- 地图上会显示图源的署名，Argus 向每个服务器表明自己的身份（`Argus-GCS/<版本号>`）。
- 默认的高德图源和 Google 图源都不是公开发布的 API，而是这两家公司自己的网页地图读取的地址。介意的话请在设置里换用其他图源。
- OpenStreetMap 禁止从它的瓦片服务器批量下载，所以离线地图面板不提供这一项。自备的地图文件（放在 `mbtiles/` 下的 `.mbtiles`）不依赖任何服务器。

## 架构

```
+------------------------------------------+
|  浏览器 (Svelte 5 + TypeScript 6)        |
|  80 组件, 27K 行                          |
|  MAVLink v2 编解码器 (纯 TS)              |
|  WebSerial 直连 USB                       |
|  41 个懒加载面板 + 视图分割               |
+------------------------------------------+
|          WebSocket (JSON 增量推送)        |
+------------------------------------------+
|  Python 后端 (FastAPI + uvicorn)          |
|  31 模块, 7.1K 行                        |
|  MAVLink 分发 + 35 消息处理器             |
|  53 条命令, 瓦片/视频/固件 API            |
+------------------------------------------+
|          MAVLink v2                       |
|  TCP / UDP / Serial                      |
+------------------------------------------+
|  飞控 (ArduPilot)                         |
+------------------------------------------+
```

### 核心模块

| 模块 | 说明 |
|---|---|
| `src/lib/mavlink/` | 纯 TypeScript MAVLink v2 编解码器，含 CRC 校验 |
| `src/lib/fc/` | 飞控适配器（ArduPilot 已接入；PX4 模式表存在但未在生产代码中引入） |
| `src/lib/transport.ts` | 双模式传输（WebSocket 后端 / WebSerial 直连） |
| `src/lib/serial.ts` | Web Serial API 封装，含飞控 USB 厂商过滤器 |
| `src/lib/terrain.ts` | SRTM 高程查询，用于地形跟随航线 |
| `src/lib/missionIO.ts` | 航线导入导出（`.waypoints` / `.plan` / `.gpx`） |
| `src/lib/survey.ts` | 测绘图案生成（网格、交叉、螺旋、环绕） |
| `src/lib/i18n.svelte.ts` | 10 语言国际化，支持 RTL |
| `backend/drone_link.py` | MAVLink 连接、帧解析、状态管理 |
| `backend/commands/` | 53 条命令处理器（解锁、模式、航线、校准、云台、NTRIP 等） |
| `backend/config.py` | 集中配置（所有超时/端口/速率常量） |

## 开发

用 `pip install -e '.[dev]'` 安装开发工具。`npm run dev` 在 `http://127.0.0.1:5173` 提供带热更新的界面，并把 API 请求转给用 `python run.py` 启动的后端。

> **Windows / 新版 Node 提示**：Node ≥17 可能把 `localhost` 解析为 IPv6 的 `::1`，而后端只绑定 IPv4 的 `127.0.0.1`，开发时请使用 `127.0.0.1`。

```bash
# 后端单元测试 + 契约测试
python -m pytest tests/test_unit_*.py tests/test_contract_*.py -v

# 前端单元测试
npx vitest run

# 类型检查（必须 0 错误 0 警告）
npx svelte-check --tsconfig ./tsconfig.json

# Python 代码检查
ruff check backend/ scripts/ tests/

# 格式检查（用 npm run format 修复）
npm run format:check

# 集成测试（自行启动后端和模拟器）
make test-integration

# 生产构建
npm run build

# E2E 测试（需要先生产构建，自行启动后端）
npm run test:e2e -- --project=chromium
```

**Git 钩子**（每个克隆执行一次 `git config core.hooksPath .githooks` 启用）：
- **pre-commit**：ruff + svelte-check
- **pre-push**：vitest + pytest 单元和契约测试

**深入文档**：

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — 开发规范：CI 门槛、双链路、测试、评审、发布
- [`CLAUDE.md`](CLAUDE.md) — 项目规范、PX4 状态、协议耦合纪律
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md) — 每项功能验证到什么程度
- [`SECURITY.md`](SECURITY.md) — 如何安全地运行，如何报告漏洞
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — 仓库和发布包里的第三方成果，以及 Argus 读取的服务器
- [`docs/FEATURE_CHECKLIST.md`](docs/FEATURE_CHECKLIST.md) — v3.4 功能快照，已冻结
- [`docs/protocol_design.md`](docs/protocol_design.md) — 承重设计决策
- [`docs/audits/`](docs/audits/) — 归档审计报告

## 发布

```bash
bash scripts/make-release.sh X.Y.Z
```

这条命令会同步所有版本号，运行前端、单元和契约测试，然后提交、打 tag、推送。GitHub Actions 随后重复 lint 和这些测试，构建 Windows 安装包，生成 changelog，发布 GitHub Release 并上传产物。Windows 安装包在发布前后还要人工检查，步骤见 [CONTRIBUTING.md](CONTRIBUTING.md#releases)。

本地预览 changelog：

```bash
bash scripts/changelog.sh v3.5.0   # 查看 v3.5.0 以来的变更
```

## 项目状态

Argus 自 2026 年 11 月起进入维护阶段：修复缺陷和安全问题，不再计划新功能。

**已完成**

- 备降点：地图编辑，两条链路都能上传和清除
- 地形剖面面板，净空可视化
- 飞行中航点跳转（MISSION_SET_CURRENT）
- WebSerial 航线上传/下载/清除 + 围栏上传
- WebSerial 日志列表 + 二进制下载
- WebSerial 全部 5 种校准类型（罗盘、加速度计、陀螺仪、水平、气压计）
- 3D 地图航点编辑、围栏绘制、距离/面积测量
- NTRIP RTK 客户端（HTTP/1.0 + ICY-200，RTCM 流式注入）
- 罗盘/加速度计/陀螺仪校准，二进制进度上报
- 多语言 UI（10 种语言 + RTL）
- 双传输互斥锁（WS 后端 / WebSerial）
- 云台俯仰/偏航控制
- Tag 触发的发布流程，自动生成 changelog

**不再计划**

以下各项曾列入路线图，本项目不会再实现：

- 固件刷写（APJ 解析 + Bootloader 协议）
- PX4 端到端支持（后端读取 `HEARTBEAT.autopilot` 并拒绝 PX4；前端只有模式表）
- WebRTC 视频流（替代 ffmpeg 代理）
- MQTT 云端中继，用于编队管理
- MAVLink FTP，用于固件上传和 Lua 脚本管理
- MSP 协议支持（BetaFlight / iNav）

Argus 不做什么、哪些从未测试过，见 [docs/VERIFICATION.md](docs/VERIFICATION.md) 和 [SECURITY.md](SECURITY.md)。

## 贡献

欢迎报告缺陷和提交修复。功能请求大概率不会被采纳，见[项目状态](#项目状态)。提交 PR 前请确保：

1. 本地测试通过：`npx vitest run && python -m pytest tests/test_unit_*.py tests/test_contract_*.py`
2. 类型检查清洁：`npx svelte-check`（0 错误，0 警告）
3. Python 代码检查清洁：`ruff check backend/ scripts/ tests/`
4. 提交规范：`<type>: <祈使句描述>`（type：`feat`、`fix`、`perf`、`refactor`、`test`、`docs`、`ci`、`chore`）
5. 飞控耦合代码（MAVLink 命令、ACK 处理、校准握手）须在注释中引用上游 ArduPilot/PX4 源码 `file:line` —— 详见 `CLAUDE.md ## Protocol Code Discipline`

## 致谢

Argus 建立在以下项目之上：

- [ArduPilot](https://ardupilot.org/) — 定义了本 GCS 所对接协议语义的飞控固件
- [pymavlink](https://github.com/ArduPilot/pymavlink) — 用于验证我们纯 TS 实现的参考 MAVLink 编解码器
- [MAVLink](https://mavlink.io/) — 通信协议本身
- [Svelte](https://svelte.dev/)、[FastAPI](https://fastapi.tiangolo.com/)、[Leaflet](https://leafletjs.com/)、[MapLibre GL](https://maplibre.org/)、[Tauri](https://tauri.app/) — 应用技术栈
- [QGroundControl](https://github.com/mavlink/qgroundcontrol) — 6 张校准示意图来自该项目（Apache-2.0）
- QGroundControl、Mission Planner、MAVProxy — 前辈 GCS，展示了可能性

## 许可

MIT — 见 [LICENSE](LICENSE)。仓库和 Windows 发布包里的第三方成果保留各自的许可，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
