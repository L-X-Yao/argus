# 故障排查与常见问题

> English: [FAQ.md](FAQ.md)

先看 [VERIFICATION.md](VERIFICATION.md) 了解已验证的内容；把 Argus 暴露到网络前先读 [SECURITY.md](../SECURITY.md)。

## 连接与访问

**找不到需要的串口。**
重新插拔飞控并刷新端口列表。Windows 上看设备管理器；Linux 上看 `ls /dev/ttyACM*`。被其他程序占用的端口仍会列出，但打不开。

**端口被占用。**
关掉占用它的程序：另一个地面站、终端或第二个 Argus 后端。Linux 上用 `fuser /dev/ttyACM0` 查进程。关掉后重新插拔。

**没有 WebSerial。**
WebSerial 需要 Chrome 或 Edge，以及安全上下文：`localhost` 或 `https`。Firefox 和 Safari 没有实现。改用后端 serial/TCP/UDP 链路。

**手机连不上电脑。**
按 [从手机或平板打开](../README.zh.md#从手机或平板打开) 操作。后端必须监听本机以外的地址，必须设置 `GCS_AUTH_TOKEN`，手机打开的地址（电脑的地址，不是手机的）必须在 `ARGUS_CORS_ORIGINS` 里。手机是第二块屏：不能用 WebSerial，纯 HTTP 下也不能用离线功能。

**要换 token。**
token 在程序目录的 `.gcs_token`，或来自 `GCS_AUTH_TOKEN`；两者都有时文件优先。仅在本机时：停止 Argus，删除 `.gcs_token`，启动，然后生成：

```bash
curl -X POST http://127.0.0.1:8100/api/auth/generate
```

网络地址上不能这样做：完全没有 token 时，Argus 拒绝监听回环以外的地址。先设好新的 `GCS_AUTH_TOKEN`（或写入新的 `.gcs_token`）再启动。两者都设过时，删掉文件才能让环境变量生效。之后更新每台手机、浏览器和 AI 客户端。观察者角色不是访问控制：拿到 token 的人都能指挥飞机。

## 地图、地形与视频

**地图空白。**
地图瓦片、地形、参数说明、视频和固件文件都由 Python 后端提供。即使通过 WebSerial 连接飞控，也要运行后端。参数说明随包分发（`param_i18n/`），离线可用；地图瓦片仍需网络或离线 `.mbtiles`。检查地图服务器署名和网络。

**离线地图。**
把 `.mbtiles` 放进 `mbtiles/`，选择离线源。地图仍需要后端来提供文件。

**视频黑屏。**
在 PATH 上安装 `ffmpeg` 并运行后端。摄像头地址必须能从电脑访问。RTSP 通过 TCP 代理。回环地址会被拒绝；私有摄像头地址允许。

**NTRIP 连不上。**
NTRIP 需要飞控通过后端链路连接，不能用 WebSerial。尚未测试真实基站；见 [VERIFICATION.md](VERIFICATION.md)。

## 任务与参数

**读取参数超时。**
链路断了或飞控忙。重试并查看事件日志。链路丢失导致的中断会报超时，不会一直等。

**任务上传被拒绝。**
确认飞机未解锁、任务非空、没有其他页面在编辑。下载后再上传会往返保留航点命令及其 p1 到 p4 字段。

**参数说明被标为机器翻译。**
英文原文来自 ArduPilot 生成的参数元数据。九种语言（zh、ar、de、es、fr、ja、ko、pt、ru）随 GPL-3.0 的 `param_i18n/` 数据包分发，离线可用；除非标记为已审校，九种语言都是机器翻译；缺字段回退英文（带 EN 标记）。“机器翻译”表示没有人审校过这段文字；“已审校”表示有人审校过。展开参数：ArduPilot 原文在译文下方，“隐藏英文原文”可收起。译文是参考，不是飞行程序。

**参数改不动。**
飞控可能对整数参数取整或限制在范围内。回读一次；Argus 显示飞控报告的值。

## 日志

**机载日志列表为空。**
飞控没有日志，或飞机链路未连接。再次向飞控请求列表。

**擦除全部会删掉所有日志。**
ArduPilot 没有单条删除。擦除全部在解锁时或下载进行时会被拒绝，且不可恢复。

**本机哪些文件可以删？**
日志面板的“本机日志”标签列出 `logs/*.tlog`。当前会话和 AI 审计日志会保留。删掉的日志会连同同名 `.csv` 一起删除。

**日志在哪里？**
程序旁边的 `logs/`。`.tlog` 保存 Argus 收到的 MAVLink 帧；`.csv` 是可读摘要。

## 固件

**固件面板在哪里？**
状态栏的闪电按钮，或 `Ctrl+K` 后选“固件升级”。

**飞控没有心跳。**
处于 bootloader 的飞控不发送 MAVLink 心跳。Argus 正是从这个状态刷写，面板接受它。

**刷写因板型不符被拒绝。**
Argus 在擦除前比较 `.apj` 的板 id 和镜像大小与 bootloader 的报告。请使用为该板构建的固件。

**刷写失败。**
见 [RECOVERY.zh.md](RECOVERY.zh.md)。擦除、写入或校验进行时不要拔线。

**再次上传同一个文件。**
同名文件再次上传会替换第一个（自 v3.13.1）。旧版本会以 Windows 错误失败；请更新 Argus。

## AI 助手

**如何连接 AI 客户端？**
见 [AI 助手（MCP）](../README.zh.md#ai-助手mcp)。Argus 有 token 时，客户端也要带 token。

**助手能改什么？**
它可以提议任务、参数修改，或飞行中的返航、悬停、降落。每个提议都在页面等待操作员批准；返航、悬停、降落仍需滑动确认。它不能解锁、起飞、启动任务或切换到其他模式。

**记录在哪里？**
`logs/assistant_audit.jsonl`：每次请求和决定一行 JSON，带客户端自己的名字。超过 5 MB 轮转。

## Windows 发布包

**Windows 提示发布者不明。**
发布包和安装器未签名。运行前用 `SHA256SUMS.txt` 和 release 的 attestation 核对；见 [安装](../README.zh.md#windows-发布包)。

**安装器拒绝了我选的文件夹。**
它只能装进空文件夹或旧的 Argus 文件夹，并在卸载后保留 `logs`、`mbtiles` 和 `firmware`。安装或卸载前关闭其他 Argus。

**程序在哪里？**
开始菜单的“Argus Ground Station”，或安装时选择的文件夹。解压包运行 `Argus地面站.bat`。

## 更新

**如何更新？**
把最新 release 覆盖安装到旧版上。`logs`、`mbtiles` 和 `firmware` 会保留。Argus 版本在设置里；状态栏的固件行是飞控的固件。
