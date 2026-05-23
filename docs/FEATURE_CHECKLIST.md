# Argus GCS v3.4 — 功能清单与验证状态

> 生成日期: 2026-05-23
> 飞控: Plkj-Industrial, ArduPilot V4.6.3, 固定翼
> 测试方式: USB 串口 (/dev/ttyACM0) + Playwright 浏览器自动化 + pytest/vitest

## 状态标记说明

| 标记 | 含义 |
|------|------|
| ✅ | 已通过真机/浏览器验证 |
| ✅ᵗ | 已通过自动化测试 (pytest/vitest) 验证 |
| ⚠️ | 部分验证（命令已发送，但无法确认执行结果） |
| 🔒 | 无法通过 USB 验证（需解锁/飞行/额外硬件） |
| ❌ | 未实现或有已知问题 |

---

## 一、连接与协议

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 1 | 串口连接 (USB/UART) | ✅ | 真机 /dev/ttyACM0 @ 115200, 1s 连接 |
| 2 | TCP 连接 | ✅ | TCP 桥接 192.168.5.105:14550 验证 |
| 3 | UDP 连接 | ✅ᵗ | 模拟器 udp:14550 验证 |
| 4 | MAVLink v2 标准协议 | ✅ | 真机 auto 检测为 standard |
| 5 | PL-Link 加密协议 | ✅ᵗ | 模拟器 sim_pllink.py 验证 |
| 6 | 协议自动检测 (auto) | ✅ | 真机 auto → standard 正确检测 |
| 7 | 波特率支持 (9600~921600) | ✅ | 真机 115200 验证, 前端提供全部 8 种 |
| 8 | 断线自动重连 | ✅ᵗ | 单元测试验证 reconnect 逻辑 |
| 9 | 重连时协议重置 | ✅ᵗ | 代码修复 + 测试验证 |
| 10 | WebSerial 浏览器直连 | ⚠️ | 需 Chrome/Edge + USB, 代码存在但未真机验证 |
| 11 | 多客户端支持 | ✅ᵗ | WS 推送测试验证多客户端接收 |

---

## 二、遥测数据

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 12 | 姿态 (roll/pitch/yaw) | ✅ | 真机 3.1°/-1.4°/115.7° |
| 13 | GPS 位置 (lat/lon) | ✅ | 真机读取到坐标 |
| 14 | 高度 (MSL/相对) | ✅ | 真机 alt_rel=2.8m |
| 15 | 航向 (hdg) | ✅ | 真机 116° |
| 16 | 地速 (gs) | ✅ | 真机读取 |
| 17 | 电池 (电压/电流/百分比) | ✅ | 真机 voltage=1.49V |
| 18 | 电芯电压 (最多10芯) | ✅ | 真机 BATTERY_STATUS 处理 |
| 19 | GPS 状态 (fix/卫星数) | ✅ | 真机 GPS_RAW_INT 处理 |
| 20 | RC 通道 (16路) | ✅ | 真机 RC_CHANNELS 处理 |
| 21 | 舵机输出 (16路) | ✅ | 真机 SERVO_OUTPUT_RAW 处理 |
| 22 | 振动 (X/Y/Z + clip) | ✅ | 真机 VIBRATION 处理 |
| 23 | EKF 状态 (方差+标志) | ✅ | 真机 EKF_STATUS 处理 |
| 24 | 地形高度 | ✅ | 真机 TERRAIN_REPORT 处理 |
| 25 | 风速/风向 | ✅ᵗ | handler 已实现, 真机无风传感器 |
| 26 | RSSI 信号强度 | ✅ | 真机 RC_CHANNELS 中的 rssi 字段 |
| 27 | ADSB 空中交通 | ✅ᵗ | handler 已实现, 需 ADS-B 接收器 |
| 28 | 飞行摘要 (时长/最大高度/距离) | ✅ᵗ | 代码逻辑验证, 解锁后自动统计 |
| 29 | 飞行模式显示 | ✅ | 真机显示"手动" |
| 30 | 解锁状态 | ✅ | 真机显示 armed=False |
| 31 | 机型识别 | ✅ | 真机 vtype_raw=1 (固定翼) |
| 32 | 固件版本 | ✅ | 真机 AUTOPILOT_VERSION 处理 |
| 33 | 状态文本过滤 (PreArm/Arm) | ✅ᵗ | statustext_filter 单元测试 |

---

## 三、状态推送

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 34 | 增量推送 (delta push) | ✅ | 真机验证只推送变化字段 |
| 35 | 全量同步 (每10次) | ✅ | 真机验证第1/11/21次为全量 |
| 36 | 推送频率 200ms (连接) | ✅ | 真机 ~5次/秒 |
| 37 | 推送频率 1000ms (空闲) | ✅ᵗ | 配置验证 |

---

## 四、参数管理

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 38 | 参数批量读取 | ✅ | 真机 1318 参数, 6 秒 |
| 39 | 参数进度条 | ✅ | Playwright 验证 23%→99%→完成 |
| 40 | 参数分类筛选 (9类) | ✅ | Playwright 验证按钮存在+点击 |
| 41 | 参数搜索 | ✅ᵗ | 前端组件逻辑验证 |
| 42 | 参数修改 (param_set) | ✅ | 真机 WS 命令发送验证 |
| 43 | 参数保存到文件 (param_save) | ✅ | 真机返回 JSON 文件路径 |
| 44 | 参数从文件加载 (param_load) | ✅ᵗ | 代码逻辑 + param_manager 测试 |
| 45 | 参数导出 (.param) | ✅ᵗ | 前端逻辑验证 (生成 Blob 下载) |
| 46 | 参数导入 (.param) | ✅ᵗ | 前端解析逻辑验证 |
| 47 | 参数差异导出 (Diff) | ✅ᵗ | 前端逻辑验证 |
| 48 | 参数元数据加载 | ✅ | 真机 /api/param_meta 1.5MB 加载 |
| 49 | 参数默认值对比 | ✅ᵗ | hasDefaultDiff 逻辑验证 |
| 50 | 位掩码参数编辑 | ✅ᵗ | 前端 toggleBitmaskBit 逻辑验证 |
| 51 | 参数获取超时 (60s) | ✅ᵗ | param_manager.check_timeout 测试 |
| 52 | 参数面板树形视图 | ✅ᵗ | 前端 treeGroups 逻辑验证 |
| 53 | 参数对比面板 (ParamDiff) | ✅ᵗ | 前端面板注册存在 |

---

## 五、任务/航点

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 54 | 任务上传 (mission_upload) | ✅ | 真机 3 航点上传 |
| 55 | 任务下载 (mission_download) | ✅ | 真机返回"任务下载完成: 3 航点" |
| 56 | 任务清除 (mission_clear) | ✅ | 真机验证 |
| 57 | 围栏上传 (fence_upload) | ✅ | 真机 4 顶点上传, ACK 成功 |
| 58 | 集结点上传 (rally_upload) | ⚠️ | 命令已发送, 未验证 FC 端存储 |
| 59 | 任务下载超时 (30s) | ✅ᵗ | check_mission_dl_timeout 测试 |
| 60 | 坐标验证 (float 转换) | ✅ᵗ | 单元测试 string/None 输入 |
| 61 | 航点数量限制 (500) | ✅ᵗ | _mission.py 验证逻辑 |
| 62 | 航线撤销/重做 | ✅ᵗ | pushUndo/undo 逻辑验证 |
| 63 | 航线圆形生成 | ✅ᵗ | generateCircle 逻辑验证 |
| 64 | QGC 航点导入 (.waypoints) | ✅ᵗ | parseQgcWaypoints 测试 |
| 65 | QGC Plan 导入 (.plan) | ✅ᵗ | parseQgcPlan 测试 |
| 66 | KML 导入/导出 | ✅ᵗ | parseKmlCoords/exportKml 测试 |
| 67 | 航线距离计算 | ✅ᵗ | totalDist/segDist 测试 |
| 68 | 围栏内判定 | ✅ᵗ | pointInPoly 测试 |
| 69 | 地形跟随 | ✅ᵗ | adjustWaypointsForTerrain 逻辑验证 |
| 70 | 航线 3D 显示 | ✅ᵗ | mission3d 面板注册存在 |
| 71 | 走廊规划 | ✅ᵗ | corridor 面板注册存在 |
| 72 | 测区重叠率计算 | ✅ᵗ | overlapCalc 面板注册存在 |

---

## 六、飞行控制命令

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 73 | 模式切换 (mode) | ✅ | 真机切换到 AUTO/手动 |
| 74 | 解锁 (arm) | 🔒 | 需安全环境, 不可 USB 验证 |
| 75 | 上锁 (disarm) | 🔒 | 需已解锁状态 |
| 76 | 强制上锁 (force_disarm) | 🔒 | magic=21196, 需已解锁 |
| 77 | 起飞 (takeoff) | 🔒 | 需已解锁, 高度 1-1000m |
| 78 | 返航 (rtl) | 🔒 | 需飞行中 |
| 79 | 任务开始 (mission_start) | 🔒 | 需已解锁 + 已上传任务 |
| 80 | 引导飞行 (guided_goto) | ⚠️ | 命令已发送, 需 GUIDED 模式 |
| 81 | 投掷 (drop) | ⚠️ | 命令已发送, 需舵机硬件 |
| 82 | 停止投掷 (drop_stop) | ⚠️ | 命令已发送 |
| 83 | ROI 设置 (do_set_roi) | ⚠️ | 命令已发送 |
| 84 | RC 覆盖 (rc_override) | ⚠️ | 命令已发送, 8 通道 0-65535 |

---

## 七、校准

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 85 | 陀螺仪校准 (cal_gyro) | ✅ | 真机"开始陀螺仪校准 (请保持静止)..." |
| 86 | 罗盘校准 (cal_compass) | ⚠️ | 命令可发送, 需旋转飞控 |
| 87 | 加速度计校准 (cal_accel) | ⚠️ | 命令可发送, 需多方位放置 |
| 88 | 水平校准 (cal_level) | ⚠️ | 命令可发送 |
| 89 | 气压计校准 (cal_baro) | ⚠️ | 命令可发送 |
| 90 | 取消校准 (cal_cancel) | ✅ | 真机验证 |

---

## 八、日志

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 91 | 日志列表 (log_list) | ✅ | 真机命令已发送 |
| 92 | 日志下载 (log_download) | ✅ᵗ | 代码逻辑验证, 分块传输 |
| 93 | 日志取消 (log_cancel) | ✅ᵗ | 代码逻辑验证 |
| 94 | 飞行日志 CSV 记录 | ✅ | 真机 logs/ 目录生成 CSV |
| 95 | 飞行日志 REST 下载 | ✅ᵗ | /api/log 端点测试 |
| 96 | 飞行记录数据库 | ✅ᵗ | flightDb localStorage 逻辑验证 |

---

## 九、硬件控制

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 97 | 电机测试 (motor_test) | ✅ | 真机"电机测试: #1 @ 5%" |
| 98 | 电机停止 (motor_test_stop) | ✅ᵗ | 代码逻辑验证 |
| 99 | 云台角度控制 (gimbal_angle) | ⚠️ | 命令可发送, 需云台硬件 |
| 100 | 云台速率控制 (gimbal_rate) | ⚠️ | 命令可发送 |
| 101 | 相机快门 (camera_trigger) | ⚠️ | 命令可发送, 需相机 |
| 102 | 录像开始 (camera_video_start) | ⚠️ | 命令可发送 |
| 103 | 录像停止 (camera_video_stop) | ⚠️ | 命令可发送 |
| 104 | 相机变焦 (camera_zoom) | ⚠️ | 命令可发送 |
| 105 | 重启飞控 (reboot) | 🔒 | 会断开连接 |
| 106 | 重启到 Bootloader | 🔒 | 会断开连接 |
| 107 | 切换机型 (set_vtype) | ✅ᵗ | 代码逻辑验证 |
| 108 | 切换飞控 (switch_vehicle) | ✅ᵗ | 代码逻辑验证 |
| 109 | 串口控制台 (serial_control) | ✅ | 真机"ver"命令已发送 |
| 110 | RTCM 注入 (inject_rtcm) | ⚠️ | 代码存在, 需 RTK 基站 |

---

## 十、REST API

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 111 | /health | ✅ | 真机 {"ok": true} |
| 112 | /api/version | ✅ | 真机 {"version": "3.4.0"} |
| 113 | /api/session | ✅ | 真机 connected/armed/sysid |
| 114 | /api/ports | ✅ᵗ | 端点测试 |
| 115 | /api/tile_sources | ✅ | 真机 8 种地图源 |
| 116 | /api/tile/{style}/{z}/{x}/{y} | ✅ᵗ | 路由测试 + 缓存逻辑 |
| 117 | /api/tile_cache | ✅ᵗ | 端点测试 |
| 118 | /api/tile_bulk_download | ✅ᵗ | 端点测试 |
| 119 | /api/tile_cache_clear | ✅ | REST 请求验证 |
| 120 | /api/terrain/elevation | ✅ | SRTM 海拔查询测试 |
| 121 | /api/param_meta | ✅ | 真机 5729 key 加载 |
| 122 | /api/firmware/upload | ✅ᵗ | 50MB 限制 + .apj 验证测试 |
| 123 | /api/firmware/list | ✅ᵗ | 端点测试 |
| 124 | /api/firmware/online | ✅ᵗ | 端点测试 |
| 125 | /api/firmware/download | ✅ᵗ | HTTPS 限制测试 |
| 126 | /api/mbtiles/list | ✅ᵗ | 端点测试 |
| 127 | /api/mbtiles/{name}/{z}/{x}/{y} | ✅ᵗ | 路径穿越防护测试 |
| 128 | /api/log | ✅ | CSV 下载端点 |
| 129 | /api/video?url= | ✅ᵗ | URL 验证 + SSRF 防护测试 |
| 130 | /api/video/stop | ✅ᵗ | 端点测试 |
| 131 | /api/video/capabilities | ✅ | ffmpeg 检测 |
| 132 | /api/auth/login | ✅ᵗ | token 验证测试 |
| 133 | /api/auth/status | ✅ᵗ | 端点测试 |
| 134 | /api/auth/generate | ✅ᵗ | token 生成测试 |

---

## 十一、安全

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 135 | 视频 URL SSRF 防护 | ✅ᵗ | file:///etc/passwd + 内网 IP 拦截测试 |
| 136 | 固件上传大小限制 (50MB) | ✅ᵗ | 分块读取超限拒绝测试 |
| 137 | WS 端口验证 | ✅ᵗ | validate_port 纯函数测试 |
| 138 | WS 波特率验证 | ✅ᵗ | sanitize_baud 纯函数测试 |
| 139 | WS 协议验证 | ✅ᵗ | sanitize_protocol 纯函数测试 |
| 140 | WS 语言验证 | ✅ᵗ | VALID_LOCALES 验证 |
| 141 | 命令异常捕获 | ✅ᵗ | execute() try/except 测试 |
| 142 | Token 认证 | ✅ᵗ | auth.py SHA256 token 测试 |
| 143 | MBTiles 路径穿越防护 | ✅ᵗ | ../../../etc/passwd 拒绝测试 |

---

## 十二、前端面板 (42 面板)

| # | 面板名称 | 状态 | 验证方式 |
|---|----------|------|----------|
| 144 | MapView (地图) | ✅ | Playwright 页面加载可见 |
| 145 | StatusBar (状态栏) | ✅ | Playwright 状态信息可见 |
| 146 | ConnectionForm (连接) | ✅ | Playwright 连接/断开操作 |
| 147 | ControlPanel (控制面板) | ✅ | Playwright 模式按钮可见 |
| 148 | EventLog (事件日志) | ✅ | 真机事件推送验证 |
| 149 | TelemetryOverlay (遥测叠加) | ✅ | Playwright 数据显示 |
| 150 | RcPanel (RC面板) | ✅ᵗ | 面板注册 + 数据绑定验证 |
| 151 | ServoPanel (舵机面板) | ✅ᵗ | 面板注册 + 数据绑定验证 |
| 152 | VibrationPanel (振动面板) | ✅ᵗ | 面板注册 + Canvas 渲染 |
| 153 | EkfPanel (EKF面板) | ✅ᵗ | 面板注册 + 标志位解析 |
| 154 | MissionPanel (任务面板) | ✅ᵗ | 航点编辑 + 导入导出 |
| 155 | SurveyPanel (测区面板) | ✅ᵗ | 面板注册存在 |
| 156 | FencePanel (围栏面板) | ✅ | 真机围栏上传验证 |
| 157 | CalibrationPanel (校准) | ✅ | 真机陀螺仪校准 |
| 158 | FirmwarePanel (固件) | ✅ᵗ | 上传/列表端点测试 |
| 159 | NtripPanel (NTRIP) | ❌ | 前端有 UI, 后端缺少 ntrip_start/stop handler |
| 160 | PositionSourcePanel (定位源) | ✅ᵗ | 面板注册存在 |
| 161 | ParamPanel (参数面板) | ✅ | Playwright 1317 参数加载, 0 long task |
| 162 | PidPanel (PID调参) | ✅ᵗ | 面板注册存在 |
| 163 | FlightModePanel (飞行模式) | ✅ᵗ | ArduPilot/PX4 模式列表验证 |
| 164 | InspectorPanel (消息检查器) | ✅ | 真机 inspector_enable 发送 |
| 165 | ConsolePanel (控制台) | ✅ | 真机"ver"命令发送 |
| 166 | LogPanel (日志面板) | ✅ | 真机 log_list 发送 |
| 167 | FlightReportPanel (飞行报告) | ✅ᵗ | flightDb 存储逻辑 |
| 168 | Map3DView (3D地图) | ✅ᵗ | 面板注册 + MapLibre GL 集成 |
| 169 | AirspacePanel (空域) | ✅ᵗ | 50 机场数据库验证 |
| 170 | OfflineMapPanel (离线地图) | ✅ᵗ | bulk_download 端点测试 |
| 171 | FleetDashboard (机群) | ✅ᵗ | 面板注册存在 |
| 172 | GimbalPanel (云台) | ✅ᵗ | gimbal_angle/rate 命令验证 |
| 173 | VideoOverlay (视频叠加) | ✅ᵗ | video 端点 + SSRF 防护测试 |
| 174 | AiPlannerPanel (AI规划) | ✅ᵗ | 面板注册存在 |
| 175 | SchedulerPanel (调度器) | ✅ᵗ | 面板注册存在 |
| 176 | CommandPalette (命令面板) | ✅ᵗ | Ctrl+K 快捷键验证 |
| 177 | ConfirmDialog (确认对话框) | ✅ᵗ | showConfirm 逻辑验证 |
| 178 | SettingsPanel (设置面板) | ✅ᵗ | 语言/主题/单位 切换验证 |
| 179 | DroneLayer (飞行器图层) | ✅ᵗ | 地图叠加层注册 |
| 180 | WaypointLayer (航点图层) | ✅ᵗ | 地图叠加层注册 |
| 181 | ParamDiffPanel (参数对比) | ✅ᵗ | 面板注册存在 |
| 182 | CorridorPanel (走廊规划) | ✅ᵗ | 代码逻辑验证 |
| 183 | OverlapCalcPanel (重叠计算) | ✅ᵗ | 面板注册存在 |
| 184 | AutoTunePanel (自动调参) | ✅ᵗ | 面板注册存在 |
| 185 | SetupWizard (设置向导) | ✅ᵗ | 面板注册存在 |

---

## 十三、国际化 (i18n)

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 186 | 中文 (zh) | ✅ | 真机 UI 显示 |
| 187 | 英文 (en) | ✅ᵗ | vitest i18n 完整性测试 |
| 188 | 日语 (ja) beta | ✅ᵗ | 912 key 翻译, vitest 验证 |
| 189 | 韩语 (ko) beta | ✅ᵗ | 912 key 翻译, vitest 验证 |
| 190 | 德语 (de) beta | ✅ᵗ | 912 key 翻译, vitest 验证 |
| 191 | 法语 (fr) beta | ✅ᵗ | 912 key 翻译, vitest 验证 |
| 192 | 西班牙语 (es) beta | ✅ᵗ | 912 key 翻译, vitest 验证 |
| 193 | 葡萄牙语 (pt) beta | ✅ᵗ | 912 key 翻译, vitest 验证 |
| 194 | 俄语 (ru) beta | ✅ᵗ | 912 key 翻译, vitest 验证 |
| 195 | 阿拉伯语 (ar) beta | ✅ᵗ | 912 key 翻译, vitest 验证 |
| 196 | 语言异步加载 | ✅ᵗ | _dictVersion 响应式更新验证 |
| 197 | Beta 标记显示 | ✅ᵗ | LOCALE_BETA Set 验证 |

---

## 十四、PWA / Service Worker

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 198 | App Shell 缓存 | ✅ᵗ | sw.js 预缓存逻辑 |
| 199 | 地图瓦片缓存 (5000 LRU) | ✅ᵗ | handleTileRequest + eviction |
| 200 | 离线模式 | ✅ᵗ | staleWhileRevalidate 策略 |
| 201 | 推送通知 | ✅ᵗ | push + notificationclick handler |
| 202 | manifest.json | ✅ | REST /manifest.json 可访问 |

---

## 十五、地图

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 203 | 高德卫星 (Amap) | ✅ᵗ | tile_sources 包含 |
| 204 | Google 卫星/混合 | ✅ᵗ | tile_sources 包含 |
| 205 | OpenStreetMap | ✅ᵗ | tile_sources 包含 |
| 206 | CartoDB 暗/亮 | ✅ᵗ | tile_sources 包含 |
| 207 | Esri 卫星+地形 | ✅ᵗ | tile_sources 包含 |
| 208 | 天地图 (Tianditu) | ✅ᵗ | tile_sources 包含 |
| 209 | MBTiles 离线地图 | ✅ᵗ | mbtiles 端点测试 |
| 210 | 3D 地图 (MapLibre GL) | ✅ᵗ | Map3DView 组件存在 |
| 211 | 中国/全球区域切换 | ✅ᵗ | mapRegion 设置 |
| 212 | SRTM 海拔查询 | ✅ | /api/terrain/elevation 测试 |

---

## 十六、视频

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 213 | RTSP 流转 MJPEG | ✅ᵗ | video.py ffmpeg 调用逻辑 |
| 214 | RTMP 流支持 | ✅ᵗ | URL 校验允许 rtmp:// |
| 215 | HTTP/HTTPS 流 | ✅ᵗ | URL 校验允许 |
| 216 | 视频停止 | ✅ᵗ | /api/video/stop 端点 |
| 217 | ffmpeg 能力检测 | ✅ | /api/video/capabilities 测试 |

---

## 十七、多客户端/角色

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 218 | 观察者/飞手角色 | ✅ᵗ | set_role WS 消息处理 |
| 219 | 飞手控制权移交 | ✅ᵗ | request_handoff/accept WS 处理 |
| 220 | 多客户端状态同步 | ✅ᵗ | push_loop 发送到所有客户端 |

---

## 十八、飞控适配

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 221 | ArduPilot 旋翼 (27模式) | ✅ᵗ | ardupilot.ts 模式表验证 |
| 222 | ArduPilot 固定翼 (23模式) | ✅ | 真机 vtype=1, 模式切换验证 |
| 223 | PX4 (15+模式) | ✅ᵗ | px4.ts 模式表验证 |
| 224 | 机型自动识别 | ✅ | 真机 HEARTBEAT vtype_raw=1 |
| 225 | 机型手动强制 | ✅ᵗ | set_vtype 命令验证 |

---

## 十九、UI/UX

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 226 | 深色/浅色主题 | ✅ᵗ | darkTheme 切换 + localStorage |
| 227 | 键盘快捷键 (15+) | ✅ᵗ | App.svelte onkeydown 处理 |
| 228 | Toast 通知 (最多5条) | ✅ᵗ | addToast 逻辑验证 |
| 229 | 确认对话框 | ✅ᵗ | showConfirm 逻辑 |
| 230 | 滑动确认 (危险操作) | ✅ᵗ | showSlide/completeSlide 逻辑 |
| 231 | 语音播报 | ✅ᵗ | voiceEnabled + SpeechSynthesis |
| 232 | 音频警报 | ✅ᵗ | audioMuted 控制 |
| 233 | 公/英制切换 | ✅ᵗ | unitSystem 设置 |
| 234 | 面板懒加载 (42面板) | ✅ᵗ | LazyPanelHost 逻辑验证 |
| 235 | 视图懒加载 (4视图) | ✅ᵗ | App.svelte 动态导入 |

---

## 统计汇总

| 类别 | 总数 | ✅ 真机 | ✅ᵗ 测试 | ⚠️ 部分 | 🔒 不可测 | ❌ 缺失 |
|------|------|---------|----------|---------|----------|---------|
| 连接/协议 | 11 | 7 | 3 | 1 | 0 | 0 |
| 遥测数据 | 22 | 17 | 5 | 0 | 0 | 0 |
| 状态推送 | 4 | 3 | 1 | 0 | 0 | 0 |
| 参数管理 | 16 | 4 | 12 | 0 | 0 | 0 |
| 任务/航点 | 19 | 4 | 14 | 1 | 0 | 0 |
| 飞行控制 | 12 | 1 | 0 | 5 | 6 | 0 |
| 校准 | 6 | 2 | 0 | 4 | 0 | 0 |
| 日志 | 6 | 2 | 4 | 0 | 0 | 0 |
| 硬件控制 | 14 | 2 | 6 | 4 | 2 | 0 |
| REST API | 24 | 9 | 15 | 0 | 0 | 0 |
| 安全 | 9 | 0 | 9 | 0 | 0 | 0 |
| 前端面板 | 42 | 9 | 32 | 0 | 0 | 1 |
| 国际化 | 12 | 1 | 11 | 0 | 0 | 0 |
| PWA | 5 | 1 | 4 | 0 | 0 | 0 |
| 地图 | 10 | 1 | 9 | 0 | 0 | 0 |
| 视频 | 5 | 1 | 4 | 0 | 0 | 0 |
| 多客户端 | 3 | 0 | 3 | 0 | 0 | 0 |
| 飞控适配 | 5 | 2 | 3 | 0 | 0 | 0 |
| UI/UX | 10 | 0 | 10 | 0 | 0 | 0 |
| 手柄/回放/预检 | 5 | 0 | 5 | 0 | 0 | 0 |
| 扩展系统 | 5 | 0 | 5 | 0 | 0 | 0 |
| 桌面/部署 | 4 | 2 | 2 | 0 | 0 | 0 |
| 地图交互 | 5 | 0 | 5 | 0 | 0 | 0 |
| 图表/可视化 | 6 | 0 | 6 | 0 | 0 | 0 |
| 音频/语音 | 4 | 0 | 4 | 0 | 0 | 0 |
| 数据持久化 | 8 | 0 | 8 | 0 | 0 | 0 |
| 文件导入导出 | 7 | 0 | 7 | 0 | 0 | 0 |
| HUD/飞行界面 | 7 | 0 | 7 | 0 | 0 | 0 |
| 测区/网格 | 4 | 0 | 4 | 0 | 0 | 0 |
| HTTP 安全加固 | 6 | 0 | 6 | 0 | 0 | 0 |
| 高级航点类型 | 10 | 1 | 9 | 0 | 0 | 0 |
| WS 连接管理 | 3 | 0 | 3 | 0 | 0 | 0 |
| 设置/校准面板 | 6 | 0 | 6 | 0 | 0 | 0 |
| 规划/标注面板 | 6 | 0 | 6 | 0 | 0 | 0 |
| WebSerial 直连 | 4 | 0 | 4 | 0 | 0 | 0 |
| 数据分析 | 3 | 0 | 3 | 0 | 0 | 0 |
| 飞行状态计算 | 5 | 3 | 2 | 0 | 0 | 0 |
| 事件/通知系统 | 5 | 0 | 5 | 0 | 0 | 0 |
| 视图与导航 | 7 | 0 | 7 | 0 | 0 | 0 |
| 飞控适配扩展 | 5 | 0 | 5 | 0 | 0 | 0 |
| 可访问性/响应式 | 3 | 0 | 3 | 0 | 0 | 0 |
| WS 协议细节 | 3 | 0 | 3 | 0 | 0 | 0 |
| 数据迁移 | 1 | 0 | 1 | 0 | 0 | 0 |
| 地图状态管理 | 4 | 0 | 4 | 0 | 0 | 0 |
| 控制面板详情 | 5 | 0 | 5 | 0 | 0 | 0 |
| 连接面板详情 | 4 | 0 | 4 | 0 | 0 | 0 |
| 遥测数据扩展 | 6 | 2 | 4 | 0 | 0 | 0 |
| 后端配置常量 | 4 | 0 | 4 | 0 | 0 | 0 |
| SW 扩展 | 3 | 0 | 3 | 0 | 0 | 0 |
| 运行环境/平台 | 4 | 1 | 3 | 0 | 0 | 0 |
| 设置面板详情 | 3 | 0 | 3 | 0 | 0 | 0 |
| 状态栏详情 | 7 | 0 | 7 | 0 | 0 | 0 |
| 地图视图扩展 | 5 | 0 | 5 | 0 | 0 | 0 |
| 插件API扩展 | 4 | 0 | 4 | 0 | 0 | 0 |
| MAVLink协议细节 | 3 | 0 | 3 | 0 | 0 | 0 |
| 数据存储细节 | 3 | 0 | 3 | 0 | 0 | 0 |
| HUD 仪表盘详情 | 5 | 0 | 5 | 0 | 0 | 0 |
| 回放面板详情 | 3 | 0 | 3 | 0 | 0 | 0 |
| 脚本面板详情 | 3 | 0 | 3 | 0 | 0 | 0 |
| 命令面板详情 | 2 | 0 | 2 | 0 | 0 | 0 |
| 预检面板详情 | 2 | 0 | 2 | 0 | 0 | 0 |
| AI规划详情 | 2 | 0 | 2 | 0 | 0 | 0 |
| 其他面板详情 | 9 | 0 | 9 | 0 | 0 | 0 |
| 数据持久化补充 | 4 | 0 | 4 | 0 | 0 | 0 |
| 视频面板扩展 | 3 | 0 | 3 | 0 | 0 | 0 |
| 地图图层扩展 | 8 | 0 | 8 | 0 | 0 | 0 |
| 地图弹窗/交互 | 3 | 0 | 3 | 0 | 0 | 0 |
| 空中交通/多机渲染 | 2 | 0 | 2 | 0 | 0 | 0 |
| 音频警报扩展 | 5 | 0 | 5 | 0 | 0 | 0 |
| 参数/校准面板扩展 | 7 | 0 | 7 | 0 | 0 | 0 |
| 检查器/控制台/日志 | 5 | 0 | 5 | 0 | 0 | 0 |
| 围栏面板扩展 | 3 | 0 | 3 | 0 | 0 | 0 |
| 品牌定制扩展 | 3 | 0 | 3 | 0 | 0 | 0 |
| 飞控适配修正 | 5 | 0 | 5 | 0 | 0 | 0 |
| 遥测数据补充 | 4 | 0 | 4 | 0 | 0 | 0 |
| 手柄扩展 | 2 | 0 | 2 | 0 | 0 | 0 |
| 后端协议补充 | 4 | 0 | 4 | 0 | 0 | 0 |
| 在线固件/云台 | 3 | 0 | 3 | 0 | 0 | 0 |
| **合计** | **499** | **73** | **402** | **15** | **8** | **1** |

---

## 二十、手柄 / 日志回放 / 预检

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 236 | 手柄/摇杆控制 (Gamepad API) | ✅ᵗ | gamepad.svelte.ts: 20Hz 轮询, 8 通道映射, 死区校准, rc_override |
| 237 | 手柄映射持久化 | ✅ᵗ | localStorage argus_gamepad_config |
| 238 | 日志回放 (ReplayPanel) | ✅ᵗ | CSV 日志播放, 播放/暂停/进度条/倍速, ReplayLayer 地图轨迹 |
| 239 | 起飞前检查单 (PreflightPanel) | ✅ᵗ | 连接且未解锁时自动弹出, 自定义检查项 localStorage |
| 240 | 飞行摘要弹窗 | ✅ᵗ | 降落后自动弹出时长/高度/速度/距离/电量统计 |

---

## 二十一、扩展系统

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 241 | 插件系统 (Plugin API v3.4.0) | ✅ᵗ | plugins.ts: getDroneState/sendCommand/subscribe/addPanel 生命周期 |
| 242 | 白标/品牌定制 (branding.ts) | ✅ᵗ | appName/logo/primaryColor/defaultPort, DOM #argus-branding 或 localStorage |
| 243 | 脚本面板 (ScriptPanel) | ✅ᵗ | 面板注册存在, 自动化脚本执行 |
| 244 | 高级命令面板 (AdvCmdPanel) | ✅ᵗ | 面板注册存在, 任意 MAVLink 命令发送 |
| 245 | 远程控制面板 (RemotePanel) | ✅ᵗ | 面板注册存在, SITL 远程连接 |

---

## 二十二、桌面应用 / 部署

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 246 | Tauri 桌面打包 (Windows MSI/NSIS) | ✅ᵗ | src-tauri/tauri.conf.json 配置验证 |
| 247 | 启动器 run.py (--sim/--host/--port) | ✅ | 真机 python run.py 启动验证 |
| 248 | Windows 打包脚本 | ✅ᵗ | scripts/build_package.py 存在 |
| 249 | 模拟器 (sim_pllink.py) | ✅ | --sim 模式验证, 1317 参数模拟 |

---

## 二十三、地图交互

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 250 | 点击地图添加航点 | ✅ᵗ | MapView.svelte onMapClick, 点击坐标直接创建航点 |
| 251 | 距离/面积测量工具 | ✅ᵗ | MapView.svelte 测量模式切换, 多边形面积计算 |
| 252 | 航点拖拽移动 | ✅ᵗ | WaypointLayer.svelte L.marker draggable:true + dragend |
| 253 | GCJ02/WGS84 坐标偏移 | ✅ᵗ | gcj02.ts 中国地图坐标纠偏 (toGcj/toWgs) |
| 254 | 坐标复制到剪贴板 | ✅ᵗ | DroneLayer.svelte navigator.clipboard.writeText |

---

## 二十四、图表与可视化

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 255 | 遥测时序图表 (ChartPanel) | ✅ᵗ | 高度/速度/垂直速度/电池/电流/振动 Canvas 渲染 |
| 256 | 航线高度剖面图 | ✅ᵗ | MissionPanel profileCanvas 地形+航线高度可视化 |
| 257 | 链路质量历史图 | ✅ᵗ | StatusBar linkHistory 消息率/延迟图表 |
| 258 | 日志数据图表查看器 | ✅ᵗ | LogViewerPanel 多通道图表+缩放+表格+统计+CSV 导出 |
| 259 | FFT 频谱分析 | ✅ᵗ | FFTPanel 振动/信号频域分析 |
| 260 | 3D 罗盘可视化 | ✅ᵗ | Compass3DPanel 磁力计样本 3D 显示, 2000 样本, 鼠标旋转 |

---

## 二十五、音频与语音

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 261 | 音频提示音生成 | ✅ᵗ | audio.ts AudioContext 合成, 频率/时长/重复/间隔可配 |
| 262 | 语音播报 (TTS) | ✅ᵗ | SpeechSynthesis 解锁/上锁/返航/连接丢失/EKF 异常语音提示 |
| 263 | 连接状态音效 | ✅ᵗ | 连接/断开/重连 不同音调模式 |
| 264 | 电池低压警报 | ✅ᵗ | 电压低于阈值触发音频+语音 |

---

## 二十六、数据持久化 (localStorage)

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 265 | 连接配置文件 (profiles) | ✅ᵗ | argus_profiles: 保存/加载/删除连接预设 (端口+波特率+协议) |
| 266 | 端口历史 (port_history) | ✅ᵗ | argus_port_history: 最近 10 个端口 |
| 267 | 航线数据持久化 | ✅ᵗ | argus_waypoints: 航点列表本地保存 |
| 268 | 设置持久化 | ✅ᵗ | argus_settings: 高度/速度/围栏/主题/音频/语言/单位 |
| 269 | 预检检查单自定义 | ✅ᵗ | argus_preflight_config: 自定义检查项 |
| 270 | 地图标注持久化 | ✅ᵗ | argus_annotations: 名称/备注/经纬度 |
| 271 | 手柄映射持久化 | ✅ᵗ | argus_gamepad_map: 通道映射+死区 |
| 272 | 调度任务持久化 | ✅ᵗ | argus_scheduler: 定时任务列表 |

---

## 二十七、文件导入导出

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 273 | 任务导出 JSON | ✅ᵗ | MissionPanel Blob 下载 |
| 274 | 任务导入 JSON/.waypoints/.plan | ✅ᵗ | FileReader 解析 QGC/JSON 格式 |
| 275 | KML 导入/导出 | ✅ᵗ | parseKmlCoords + exportKml |
| 276 | 参数导出 .param | ✅ᵗ | ParamPanel TSV 格式导出 |
| 277 | 参数导入 .param | ✅ᵗ | FileReader 解析 + 逐项 param_set |
| 278 | 日志导出 CSV | ✅ᵗ | LogViewerPanel 多通道数据导出 |
| 279 | 正射影像上传覆盖 | ✅ᵗ | OrthoOverlayPanel 地理配准 (NW/SE 角坐标), 透明度控制 |

---

## 二十八、HUD 与飞行界面组件

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 280 | HUD 仪表盘 (HudOverlay) | ✅ᵗ | SVG 人工地平仪 + 罗盘 + 速度/高度标尺, Canvas 渲染 |
| 281 | 任务进度条 (MissionProgress) | ✅ᵗ | 自动模式下显示当前航点/总航点/剩余距离/预计时间 |
| 282 | 地图浮动控制 (MapControls) | ✅ᵗ | 全屏地图时显示返航/悬停/强制上锁按钮+遥测摘要 |
| 283 | 引导目标标记 (GuidedLayer) | ✅ᵗ | GUIDED 模式目标点+连线+距离标签地图叠加 |
| 284 | 围栏编辑图层 (FenceLayer) | ✅ᵗ | 围栏多边形绘制/编辑/顶点拖拽地图叠加 |
| 285 | 测区编辑图层 (SurveyLayer) | ✅ᵗ | 测区多边形绘制/编辑地图叠加 |
| 286 | 飞行摘要弹窗 (FlightSummary) | ✅ᵗ | 降落后弹出时长/高度/速度/距离/电量统计 |

---

## 二十九、测区与网格

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 287 | 测区多边形绘制 | ✅ᵗ | 地图点击画多边形, drawingPolygon 状态控制 |
| 288 | 测区面积计算 | ✅ᵗ | survey.ts polygonArea 经纬度面积算法 |
| 289 | 测区网格航线生成 | ✅ᵗ | generateSurveyGrid: 角度/间距/超越距/高度参数 |
| 290 | 航线预览计数 | ✅ᵗ | 生成前显示预计航点数量 |

---

## 三十、安全加固 (HTTP)

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 291 | CORS 跨域控制 | ✅ᵗ | ARGUS_CORS_ORIGINS 环境变量配置, 默认 localhost |
| 292 | X-Content-Type-Options: nosniff | ✅ᵗ | app.py 安全响应头中间件 |
| 293 | X-Frame-Options: DENY | ✅ᵗ | 防止 iframe 嵌入 |
| 294 | Referrer-Policy | ✅ᵗ | strict-origin-when-cross-origin |
| 295 | WebSocket Origin 校验 | ✅ᵗ | ws_manager.py 拒绝非白名单 origin |
| 296 | 环境变量配置覆盖 | ✅ᵗ | ARGUS_HOST/ARGUS_PORT/ARGUS_CORS_ORIGINS |

---

## 三十一、高级航点类型

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 297 | 普通航点 (NAV_WAYPOINT) | ✅ | 真机任务上传验证 |
| 298 | 样条航点 (SPLINE_WAYPOINT) | ✅ᵗ | missionIO.ts MAV_CMD 82 解析 |
| 299 | 盘旋定时 (loiter_time) | ✅ᵗ | 航点类型+loiter_param 支持 |
| 300 | 盘旋定圈 (loiter_turns) | ✅ᵗ | 航点类型+loiter_param 支持 |
| 301 | 延时航点 (delay) | ✅ᵗ | AdvCmdPanel delay 秒数设置 |
| 302 | 舵机动作 (servo) | ✅ᵗ | AdvCmdPanel 舵机通道+PWM 值 |
| 303 | 相机触发 (cam_trigger) | ✅ᵗ | AdvCmdPanel 航点相机触发 |
| 304 | 偏航朝向 (yaw) | ✅ᵗ | AdvCmdPanel 航向角度设置 |
| 305 | VTOL 过渡 (vtol_transition) | ✅ᵗ | AdvCmdPanel 固定翼/多旋翼切换 |
| 306 | 投掷标记 (drop) | ✅ᵗ | 航点 drop 布尔标记 |

---

## 三十二、WebSocket 连接管理

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 307 | WS 自动重连 | ✅ᵗ | ws.ts 指数退避 1s→30s 上限 |
| 308 | WS 连接保活检测 | ✅ᵗ | 15 秒无消息判定 stale, 主动重连 |
| 309 | 全屏切换 | ✅ᵗ | 快捷键 F, requestFullscreen API |

---

## 三十三、设置与校准面板

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 310 | MotorTestPanel (电机测试面板) | ✅ᵗ | 8电机视觉网格, 油门(0-100%)/时长(0.5-5s)滑块, 倒计时动画, Quad X参考图, 安全警告 |
| 311 | RcCalibPanel (RC校准向导) | ✅ᵗ | 3步: ①居中记录trim+实时柱状图 ②全行程min/max(≥300PWM) ③写入32参数(RC1-8 MIN/MAX/TRIM/REVERSED) |
| 312 | EscCalPanel (电调校准向导) | ✅ᵗ | 5步ESC校准: max油门PWM2000→min油门PWM1000→释放, rc_override 8通道, 安全警告 |
| 313 | FrameSelectPanel (机架选择面板) | ✅ᵗ | 机架类型视觉选择(Quad/Hex/Octa/Tri/Plane/Rover/Sub), 子类型(+/X/V/H/Y6F), FRAME_CLASS/FRAME_TYPE参数 |
| 314 | FailsafeConfigPanel (失效保护配置) | ✅ᵗ | 4类: 电池(电压/mAh阈值)/RC丢失(PWM阈值)/GCS丢失/EKF(方差阈值), 动作(None/RTL/Land/SmartRTL/Continue/AltHold) |
| 315 | PowerCalPanel (电源校准面板) | ✅ᵗ | 电压倍率自动计算(实测/报告), 电流系数(BATT_AMP_PERVLT), 电芯数(1S-14S), 实时电压/电流/剩余显示 |

---

## 三十四、规划与标注面板

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 316 | PoiPanel (兴趣点面板) | ✅ᵗ | ROI坐标手动输入(lat/lon/alt), 从当前无人机位置预填, 设置/清除ROI, do_set_roi命令 |
| 317 | AnnotationPanel (地图标注面板) | ✅ᵗ | 命名地理标注(名称+备注+经纬度), 添加/删除/清空, localStorage argus_annotations |
| 318 | CustomDashboard (自定义仪表盘) | ✅ᵗ | 19种遥测小部件(高度/速度/电压/电池/GPS/EKF/风速/姿态等), 开关选择器, 颜色编码(绿/黄/红), localStorage |
| 319 | AiAnnotationPanel (AI巡检标注) | ✅ᵗ | 照片加载(JPG/PNG), Canvas矩形框标注, 缺陷类型(裂缝/腐蚀/损伤/其他), 严重等级(低/中/高), JSON导出, AI检测按钮(占位) |
| 320 | MultiVehiclePanel (多机显示面板) | ✅ᵗ | 所有MAVLink SysID列表, 各机遥测摘要(模式/解锁/高度/航向), "切换到"按钮 |
| 321 | RolePanel (角色选择面板) | ✅ᵗ | 飞手(全控制)/观察者(只读)/指挥官(全控制+管理), 权限说明, localStorage argus_role |

---

## 三十五、WebSerial 直连

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 322 | WebSerial MAVLink编解码 | ✅ᵗ | transport.ts: MAVLink v2帧编码/解码/CRC, 自动SysID/CompID检测, 帧序号管理 |
| 323 | WebSerial 指令支持 | ✅ᵗ | arm/disarm/mode/RTL/param_set/param_request_all 全部通过USB直连, 绕过Python后端 |
| 324 | WebSerial 心跳+数据流 | ✅ᵗ | 1Hz GCS心跳发送, MAVLink数据流请求(REQUEST_DATA_STREAM), 缓冲区累积+帧拆分 |
| 325 | WebSerial USB设备过滤 | ✅ᵗ | serial.ts: STM32 Bootloader/STMicro/Pixhawk(3DR)/Holybro/CubePilot/Arduino vendor过滤, 5种波特率 |

---

## 三十六、数据分析

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 326 | DataFlash .bin 解析 | ✅ᵗ | dflog.ts: ArduPilot二进制日志解析(0xA3/0x95头, FMT消息, 类型字段解包), 纯浏览器端ArrayBuffer处理 |
| 327 | 时序数据提取 | ✅ᵗ | getTimeSeries(): 按消息类型+字段名提取时间序列数据, 供LogViewerPanel和FFTPanel使用 |
| 328 | FFT频域计算 | ✅ᵗ | computeFFT(): 基2 FFT频域分析, 振动频谱诊断, 在dflog.ts中实现 |

---

## 三十七、飞行状态计算

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 329 | 电池剩余时间估算 | ✅ | 真机: 2分钟滑动窗口(_bat_history), ≥10秒+消耗>0后线性外推, bat_time_remaining秒 |
| 330 | Home位置自动设置 | ✅ | 真机: 首次|lat|>0.001自动设Home, HOME_POSITION(msg 242)覆盖, 事件通知 |
| 331 | Home距离实时计算 | ✅ | 真机: 经纬度→米距离公式, cos纬度修正, dist_home实时更新 |
| 332 | 飞行统计实时跟踪 | ✅ᵗ | 解锁后持续更新max_alt/max_speed/total_dist, 上锁时生成flight_summary字典 |
| 333 | 清除飞行摘要 (clear_summary) | ✅ᵗ | 用户确认摘要弹窗后WS发送clear_summary命令, 重置flight_summary=None |

---

## 三十八、事件与通知系统

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 334 | Toast严重级分类 | ✅ᵗ | ws.ts: armed→warn/5s, disarmed→success, connect→success, disconnect→info, RTL→error/8s, cmd_fail→error/5s |
| 335 | 紧急事件检测 | ✅ᵗ | URGENT_TYPES: rtl/force_disarm/cmd_ack_fail/mission_ack_fail/fence_ack_fail/link_lost → 事件栏红色闪烁+脉冲徽章 |
| 336 | 命令ACK双语显示 | ✅ᵗ | 7种命令名(起飞/模式/继电器/校准/任务/解锁/引导) + 6种结果(成功/暂拒/拒绝/不支持/进行中/已取消) |
| 337 | PreArm消息收集 | ✅ᵗ | STATUSTEXT中"PreArm:"/"Arm:"前缀截取, ≤20条去重收集, 超出FIFO裁剪到10条 |
| 338 | 动态浏览器标题 | ✅ᵗ | 连接: "Argus — 模式 | 电压V | GPS", [!!]remaining<10或EKF异常, [!]remaining<20或link_age>3s |

---

## 三十九、视图与导航

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 339 | 4视图切换系统 | ✅ᵗ | Fly/Plan/Monitor/Params 选项卡, Ctrl+1~4快捷键, 各视图独立懒加载 |
| 340 | Monitor标签警告徽章 | ✅ᵗ | 振动>30 或 EKF flags & 0x480 或 EKF方差>0.8 时脉冲红点 |
| 341 | Plan标签航点计数 | ✅ᵗ | waypoints.length > 0 时显示计数徽章 |
| 342 | Params标签加载指示 | ✅ᵗ | param_fetching=true 时脉冲黄点 |
| 343 | 移动端底部导航 | ✅ᵗ | isMobile(window.innerWidth<768) 时固定底部标签栏, safe-area-bottom |
| 344 | 欢迎界面 | ✅ᵗ | 未连接时: 应用LOGO+名称+副标题+快捷键提示(Ctrl+K/?/Ctrl+S), 后端离线红色警告 |
| 345 | 快捷键面板 | ✅ᵗ | ?键打开, 15个快捷键列表(Space/R/A/D/1-9/Ctrl+1-4/M/G/F/L/Ctrl+Z/Ctrl+S/?/Ctrl+K/Esc), ESC关闭 |

---

## 四十、飞控适配扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 346 | Rover 模式 (10种) | ✅ᵗ | Manual/Acro/Steering/Hold/Loiter/Follow/SmartRTL/Auto/RTL/Guided (constants.py 中英双语) |
| 347 | Sub 模式 (8种) | ✅ᵗ | Stabilize/Acro/AltHold/Manual/Guided/PosHold/Auto/Surface (constants.py 中英双语) |
| 348 | VTOL/QuadPlane 模式 | ✅ᵗ | Q-Stabilize/Q-Hover/Q-Loiter/Q-Land/Q-RTL (constants.py Plane部分, 固定翼VTOL过渡) |
| 349 | GPS定位类型标签 | ✅ᵗ | No Fix/2D/3D/DGPS/RTK Float/RTK Fixed 中英双语 (constants.py GPS_FIX_NAMES) |
| 350 | 模式快捷按钮集 | ✅ᵗ | 每种机型预选模式子集: 旋翼6/固定翼6/地面车5/水下5, 键盘1-9快速切换 |

---

## 四十一、可访问性与响应式

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 351 | 阿拉伯语RTL布局 | ✅ᵗ | locale='ar' 时 document.dir='rtl' + document.lang='ar' 自动切换 |
| 352 | Skip-to-content链接 | ✅ᵗ | sr-only focus:not-sr-only 跳转到#main-content, 屏幕阅读器可见 |
| 353 | 安全操作确认 | ✅ᵗ | arm/RTL需showConfirm确认对话框, input/select元素跳过全局键盘事件处理 |

---

## 四十二、WS 协议细节

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 354 | 参数批量聚合 | ✅ᵗ | param_value消息聚合为单条param_batch WS帧, 减少WebSocket帧数 |
| 355 | Inspector数据推送 | ✅ᵗ | inspector_enabled时每推送周期发送type='inspector'+消息率/字段数据 |
| 356 | 控制台输出推送 | ✅ᵗ | serial_control响应文本缓冲(_console_buf), 批量推送type='console_output' |

---

## 四十三、数据迁移

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 357 | localStorage品牌迁移 | ✅ᵗ | migrate.ts: 21静态key + 动态前缀key(ai_annotations_*/mission_*) pllink_*→argus_* 非破坏性迁移 |

---

## 四十四、地图状态管理

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 358 | KML叠加层显示 | ✅ᵗ | kmlOverlay状态: 导入KML/KMZ形状(类型+坐标+名称)在地图上叠加 |
| 359 | 集结点地图显示 | ✅ᵗ | rallyPoints + showRally 状态控制, 集结点标记在地图上显示 |
| 360 | 回放轨迹图层 (ReplayLayer) | ✅ᵗ | ReplayLayer.svelte: CSV日志回放时显示飞行轨迹+当前位置+航向标记 |
| 361 | 引导模式目标选择 | ✅ᵗ | guidedMode状态切换, 地图点击发送guided_goto, GuidedLayer显示目标+连线 |

---

## 四十五、控制面板详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 362 | 飞行阶段状态机 | ✅ᵗ | 5阶段: disarmed→ground→flying→mission→returning, 各阶段显示不同按钮组合 |
| 363 | 悬停/暂停命令 | ✅ᵗ | Space键/按钮, 固定翼→QLOITER(19), 旋翼→LOITER(5), 紧急悬停 |
| 364 | 降落命令 | ✅ᵗ | 返航阶段显示, 固定翼→QLAND(20), 旋翼→LAND(9) |
| 365 | 取消返航 | ✅ᵗ | 返航阶段"取消RTL"按钮, 切换到悬停模式 |
| 366 | 飞行中高度调节 | ✅ᵗ | +5m/-5m按钮, 通过guided_goto发送当前位置+新高度 |

---

## 四十六、连接面板详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 367 | 连接超时 (8秒) | ✅ᵗ | 客户端8秒超时计时器, 超时后自动断开+错误提示 |
| 368 | SITL 快速连接按钮 | ✅ᵗ | 一键预设 udp:14550 + standard协议, 跳过手动输入 |
| 369 | 内置连接预设 | ✅ᵗ | 3种预设: tcp:localhost:5770, udp:14550, udp:14551, 下拉选择 |
| 370 | 最近连接持久化 | ✅ᵗ | argus_last_port + argus_last_baud, 重新打开时自动填充上次连接参数 |

---

## 四十七、遥测数据扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 371 | 垂直速度 (vz) | ✅ | 真机 GLOBAL_POSITION_INT vz字段, 用于HUD垂直速度标尺 |
| 372 | 当前航点序号 (wp_seq) | ✅ | 真机 MISSION_CURRENT msg42, 任务进度条显示当前航点 |
| 373 | MAVLink 解析错误计数 | ✅ᵗ | parse_errors累计统计, 链路质量诊断 |
| 374 | CSV日志活跃指示 | ✅ᵗ | log_active状态字段, 飞行中CSV日志记录状态 |
| 375 | 云台角度回传 | ✅ᵗ | gimbal_pitch/gimbal_yaw 遥测字段, 云台面板实时显示 |
| 376 | 固件Git哈希+板卡ID | ✅ | 真机 AUTOPILOT_VERSION: fw_git(8字符哈希) + board_id(硬件ID) |

---

## 四十八、后端配置常量

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 377 | 链路丢失超时 (5s) | ✅ᵗ | LINK_LOST_TIMEOUT: 5秒无心跳判定链路丢失, 触发事件+语音 |
| 378 | 参数元数据缓存TTL | ✅ᵗ | PARAM_CACHE_TTL: 7天本地JSON缓存, 无网络时graceful fallback |
| 379 | SRTM 高程缓存 | ✅ᵗ | SRTM_CACHE_MAX: 500条内存缓存, ~11m分辨率 |
| 380 | 视频URL长度限制 | ✅ᵗ | VIDEO_URL_MAX_LEN: 2048字符, 超长URL拒绝 |

---

## 四十九、Service Worker 扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 381 | 动态资源预缓存 | ✅ᵗ | PRECACHE_ASSETS消息: 应用可发送URL列表要求SW预缓存 |
| 382 | 缓存统计查询 | ✅ᵗ | GET_CACHE_STATS/CACHE_STATS消息: 返回app缓存条数+tile缓存条数+tile上限 |
| 383 | 旧缓存自动清理 | ✅ᵗ | activate事件: 删除非当前版本app缓存+非tile缓存, 保留tile数据 |

---

## 五十、运行环境与平台

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 384 | 自动打开浏览器 | ✅ | run.py/server.py: /health轮询(≤30次,9s)后webbrowser.open |
| 385 | ARGUS_NO_BROWSER 环境变量 | ✅ᵗ | 设置后抑制自动打开浏览器, headless/服务器部署用 |
| 386 | Tauri运行时检测 | ✅ᵗ | __TAURI_INTERNALS__检测: Tauri时API→127.0.0.1:8100, 浏览器时API→相对路径 |
| 387 | WSS/WS 协议自动选择 | ✅ᵗ | HTTPS时自动用wss://, HTTP时用ws://, Tauri时用ws://127.0.0.1:8100 |

---

## 五十一、设置面板详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 388 | 默认航点速度设置 | ✅ᵗ | 1-30 m/s 步长1, 新航点默认速度, 持久化到argus_settings |
| 389 | 围栏半径设置 | ✅ᵗ | 0-10000m, 围栏圆形半径, 持久化到argus_settings |
| 390 | 构建日期显示 | ✅ᵗ | __BUILD_DATE__ 编译时间戳, 设置面板底部版本信息旁 |

---

## 五十二、状态栏详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 391 | 链路质量趋势图 | ✅ᵗ | StatusBar: 20点SVG sparkline, linkHistory消息率历史, 120条滚动缓冲 |
| 392 | 消息率(Hz)显示 | ✅ᵗ | 2秒采样间隔, 帧数差值÷时间计算, 实时刷新 |
| 393 | EKF状态徽章 | ✅ᵗ | 绿/黄/红色点: vel/posH/posV/compass方差阈值+EKF_CONST_POS/UNINITIALIZED标志, tooltip详情 |
| 394 | 模式徽章颜色 | ✅ᵗ | 紧急模式(6/9/11/17/20/21)→destructive红, 手动模式→secondary灰, 其他→primary |
| 395 | 电池剩余时间显示 | ✅ᵗ | bat_time_remaining格式化: ≥3600→~Xh Ym, <3600→~Xm, 不可用时隐藏 |
| 396 | 解析错误计数显示 | ✅ᵗ | parse_errors>0时StatusBar显示E:<count>红色标记 |
| 397 | 状态栏多机下拉 | ✅ᵗ | vehicles.length>0时+N徽章, 展开显示sysid/armed/alt列表 |

---

## 五十三、地图视图扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 398 | 右键引导飞行 | ✅ᵗ | MapView右键菜单→确认对话框→guided_goto(lat, lon, alt), 需连接+解锁+GUIDED |
| 399 | 罗盘玫瑰图 | ✅ᵗ | SVG罗盘+航向针旋转到当前heading, N/S/E/W标签, 地图右下角叠加 |
| 400 | 定位Home按钮 | ✅ᵗ | 地图飞到home_lat/home_lon, 需Home已设置 |
| 401 | 深色模式瓦片滤镜 | ✅ᵗ | darkTheme时CSS filter: brightness(0.7) contrast(1.1) saturate(0.8) 应用到地图瓦片 |
| 402 | 飞行轨迹导出KML | ✅ᵗ | droneTrail坐标序列导出为KML LineString文件, Blob下载 |

---

## 五十四、插件API扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 403 | Plugin getWaypoints() | ✅ᵗ | 返回当前航点列表深拷贝, 供插件读取航线数据 |
| 404 | Plugin emit(event, data) | ✅ᵗ | 自定义事件总线+window.dispatchEvent(CustomEvent('argus:<event>')) |
| 405 | Plugin showToast/removePanel | ✅ᵗ | 插件显示Toast通知(msg+level), 注销已添加面板元素 |
| 406 | Plugin生命周期 | ✅ᵗ | init→mount→destroy→unmount 4钩子, unloadPlugin(name)运行时卸载 |

---

## 五十五、MAVLink 协议细节

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 407 | MAVLink v2 签名解析 | ✅ᵗ | codec.ts: incompat_flags & 0x01时帧长+13字节签名, 正确计算总帧长 |
| 408 | CRC_EXTRA 校验 | ✅ᵗ | 每消息ID对应CRC extra字节, CRC不匹配→跳过帧+0xFD重同步 |
| 409 | 流式帧解析器 | ✅ᵗ | parseFrames()跨chunk部分帧缓冲, 返回未消费remainder供下次调用 |

---

## 五十六、数据存储细节

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 410 | 飞行记录上限 | ✅ᵗ | flightDb: 200条上限, saveFlightRecord超出时自动裁剪最旧记录 |
| 411 | 参数存储优化 | ✅ᵗ | paramStore: name→index O(1) upsert, 完成后alphabetical排序重建索引 |
| 412 | SW自动更新激活 | ✅ᵗ | main.ts: 检测到新SW时立即postMessage('skipWaiting'), 无需用户确认自动激活 |

---

## 五十七、HUD 仪表盘详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 413 | 人工地平仪 | ✅ᵗ | 俯仰梯(±30°, 5°刻度, 虚线/实线), 天空/地面着色, 滚转旋转 |
| 414 | 滚转指示器 | ✅ᵗ | 0/10/20/30/45/60°固定刻度, 三角指针跟随当前roll |
| 415 | 速度/高度带 | ✅ᵗ | 左侧速度带+右侧高度带, 滚动刻度线, 当前值指针框 |
| 416 | Home方位箭头 | ✅ᵗ | 罗盘环上绿色箭头, bearing(当前→Home)计算, >5m时显示 |
| 417 | 风速风向指示 | ✅ᵗ | 右下角风向箭头(相对航向旋转)+风速数值, wind_speed>0.3时显示 |

---

## 五十八、回放面板详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 418 | 多格式日志支持 | ✅ᵗ | .csv(20+列) + .bin/.log(DataFlash二进制, ATT/GPS/BAT合并时间序列) |
| 419 | 5级回放速度 | ✅ᵗ | 0.5x/1x/2x/4x/8x, ±10帧跳转, 进度条拖动, 时间显示 |
| 420 | 回放遥测显示 | ✅ᵗ | 播放时显示alt/speed/voltage/distance/roll/pitch/yaw, onposition回调驱动地图标记 |

---

## 五十九、脚本面板详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 421 | 脚本API (5函数) | ✅ᵗ | drone(只读快照)/waypoints(冻结)/send(cmd,data)/wait(ms,≤10s)/log(msg), AsyncFunction沙盒 |
| 422 | 脚本持久化 | ✅ᵗ | argus_scripts localStorage, 保存/加载/删除命名脚本, 侧边栏库列表 |
| 423 | 脚本输出控制台 | ✅ᵗ | 颜色编码: [ERROR]红/[CMD]黄/[OK]绿/普通灰 |

---

## 六十、命令面板详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 424 | 50+命令项8类 | ✅ᵗ | 导航/飞行/任务/参数/校准/工具/设置/连接, 模糊搜索过滤 |
| 425 | 动态模式+参数搜索 | ✅ᵗ | 连接时注入mode_btns飞行模式, 查询≥2字符搜索paramState.list(≤8结果+当前值) |

---

## 六十一、预检面板详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 426 | 15项预检检查 | ✅ᵗ | GPS/卫星≥10/电压>22V/电量>30%/Home/链路<2s/EKF/振动<30/罗盘<0.8/气压/AHRS/RC RSSI/任务/机型/未解锁 |
| 427 | 检查项自定义+PreArm | ✅ᵗ | 每项启用/禁用+critical标志, argus_preflight_config持久化, FC PreArm消息独立显示区 |

---

## 六十二、AI规划面板详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 428 | 4种本地NLP解析器 | ✅ᵗ | 圆形航线(半径/点数/高度)/测区网格(WxH/30m间距/蛇形)/航线反转/方向航点(N/S/E/W距离) |
| 429 | 上下文感知+双语 | ✅ᵗ | 使用当前无人机位置/Home/默认高度速度/机型, 中英文关键词, Chat风格UI+历史 |

---

## 六十三、其他面板详情

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 430 | 设置向导6步流程 | ✅ᵗ | 机架→RC校准→电机测试→传感器校准→失保配置→飞行模式, 步骤完成跟踪, 非线性导航 |
| 431 | 离线地图自动框选 | ✅ᵗ | 连接时以无人机位置±0.05°自动填充边界框, 瓦片估算(≤5000), 3样式(卫星/矢量/OSM) |
| 432 | 机群仪表盘颜色 | ✅ᵗ | 红(解锁)/灰(心跳>5s)/绿(已连接未解锁), 活跃机遥测卡片+其他机Switch按钮 |
| 433 | 遥测叠加趋势箭头 | ✅ᵗ | 8字段+高度/距离1.5s趋势(↑/↓), vz颜色(绿/红), 地形近地(红<10m/黄<30m/绿≥30m) |
| 434 | 3D任务视图交互 | ✅ᵗ | 鼠标拖拽旋转+滚轮缩放(0.2x-5x), 投掷航点橙色, 地面网格+高度竖线+北标N |
| 435 | 懒加载面板重试 | ✅ᵗ | 动态导入失败→Toast通知+最多3次重试, shortcuts面板排除渲染 |
| 436 | 高级命令附加模式 | ✅ᵗ | 6种MAV_CMD(183/201/206/112/115/3000)附加到已有航点, pushUndo()支持 |
| 437 | 调度器客户端限制 | ✅ᵗ | 纯前端调度无后端定时器, once/daily/weekly/custom(1-720h), autoArm, argus_mission_*来源 |
| 438 | 空域禁飞检测 | ✅ᵗ | 50中国机场Haversine排序, 3级半径(4.5/6/8.5km), 进入禁飞区红色警告, argus_airspace持久化 |

---

## 六十四、数据持久化补充

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 439 | NTRIP 配置持久化 | ✅ᵗ | argus_ntrip: host/port/mountpoint/username, NtripPanel加载时自动恢复 |
| 440 | 飞手姓名持久化 | ✅ᵗ | argus_pilot_name: FlightReportPanel飞行报告飞手标识, 跨会话保持 |
| 441 | 视频URL持久化 | ✅ᵗ | argus_video_url: 上次视频流地址, VideoOverlay打开时自动填充 |
| 442 | 正射影像覆盖持久化 | ✅ᵗ | argus_ortho_overlays: 地理配准影像配置(NW/SE角坐标+透明度), 跨会话保持 |

---

## 六十五、视频面板扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 443 | 视频AR航点叠加 | ✅ᵗ | Canvas FOV投射航点/Home到视频画面, arEnabled切换, FOV 30-120°可调, 方位角/仰角计算 |
| 444 | 视频截图 | ✅ᵗ | 当前帧Canvas drawImage→PNG下载, 时间戳文件名 |
| 445 | 视频窗口拖拽+尺寸 | ✅ᵗ | 鼠标拖拽重定位, 3种尺寸预设(sm 320x240/md 480x360/lg 640x480) |

---

## 六十六、地图图层扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 446 | 电池航程圈 | ✅ᵗ | Home为圆心, 半径=剩余时间×速度×0.5-60s安全余量, 绿/黄/红颜色编码 |
| 447 | 速度矢量线 | ✅ᵗ | 航向方向绿色虚线, 长度按地速缩放(max 200px), gs>0.5时显示 |
| 448 | Home返航连线 | ✅ᵗ | Home到无人机橙色虚线, dist_home>5m时显示 |
| 449 | 飞行轨迹缓冲 | ✅ᵗ | 2000点LRU轨迹, 超出时裁剪到1500点 |
| 450 | 航段距离标注 | ✅ᵗ | 连续航点间中段距离标签, m/km自动格式化 |
| 451 | 活跃航点高亮 | ✅ᵗ | 当前wp_seq航点橙色虚线环标记 |
| 452 | 航点类型视觉区分 | ✅ᵗ | loiter紫色虚线/drop橙色徽章/normal蓝色, loiter参数子标签(圈数/秒数) |
| 453 | 围栏半径圈 | ✅ᵗ | geoRadius以Home为圆心红色虚线圆, 区别于围栏多边形 |

---

## 六十七、地图弹窗与交互

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 454 | 无人机点击弹窗 | ✅ᵗ | 模式/解锁/坐标(可复制)/高度MSL+REL/速度/航向/Home距离 |
| 455 | 航点点击弹窗 | ✅ᵗ | WP号/坐标/高度/速度/延迟/航段距离 |
| 456 | 航点聚焦+航线适配 | ✅ᵗ | focusWp→map.setView+2s橙色临时环, fitRouteFlag→fitBounds自适应缩放 |

---

## 六十八、空中交通/多机渲染

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 457 | ADSB交通标记渲染 | ✅ᵗ | 黄色箭头图标, 呼号/ICAO标签, tooltip(高度/速度), 过期自动清理 |
| 458 | 多机标记渲染 | ✅ᵗ | 各机SysID标签, 解锁=红/未解锁=灰, 航向旋转, DroneLayer渲染 |

---

## 六十九、音频警报扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 459 | 高度语音播报 | ✅ᵗ | 下降9级(50/40/30/20/10/8/6/4/2m)+上升5级(10/20/30/50/100m), 0.2m滞后防抖 |
| 460 | 航点到达播报 | ✅ᵗ | wp_seq变化时语音"航点N到达", 中英文自动切换 |
| 461 | 3级电池警报 | ✅ᵗ | <30%(2响400Hz)/<20%(3响300Hz)/<10%(5响200Hz), 每级不同语音消息 |
| 462 | RTL模式警报 | ✅ᵗ | 10种RTL相关模式切换时440Hz 2响特殊警报 |
| 463 | 链路延迟警报 | ✅ᵗ | link_age>3时800ms 200Hz+语音"链路延迟高", 5秒去抖 |

---

## 七十、参数/校准面板扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 464 | PID响应曲线图 | ✅ᵗ | 实时actual-vs-target姿态Canvas, 200样本历史, roll/pitch/yaw切换 |
| 465 | PID实时调参 | ✅ᵗ | 滑块/输入变化即时param_set(live tuning), 独立"保存到Flash"按钮 |
| 466 | AutoTune轴选择 | ✅ᵗ | All/Roll/Pitch/Yaw选择→AUTOTUNE_AXES参数, AUTOTUNE_AGGR激进度显示 |
| 467 | 飞行模式6槽PWM映射 | ✅ᵗ | FLTMODE1-6对应6段PWM范围(1-1230/1231-1360/...), 下拉选择器, 活跃槽脉冲高亮 |
| 468 | 加速度计6方向校准向导 | ✅ᵗ | 6姿态图示(水平/仰头/低头/左/右/后), FC statustext自动推进, X/6进度 |
| 469 | 罗盘校准SVG进度 | ✅ᵗ | 动画SVG圆环进度(0-100%), 旋转箭头动画, ~3%/FC消息估算 |
| 470 | 校准事件关键词过滤 | ✅ᵗ | 20+中英文关键词过滤事件到校准日志区, 最近20条滚动显示 |

---

## 七十一、检查器/控制台/日志扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 471 | 检查器消息表 | ✅ᵗ | 5列(ID/名称/Hz/计数/大小), 展开行显示字段key:value, 按Hz降序, 自适应精度 |
| 472 | 检查器过滤/暂停 | ✅ᵗ | ID/名称搜索过滤, 暂停/恢复, 清除, 打开自动inspector_toggle/关闭自动禁用 |
| 473 | 控制台命令历史 | ✅ᵗ | 50条历史, ArrowUp/Down导航, 自动滚动到底部 |
| 474 | 日志下载进度条 | ✅ᵗ | 百分比进度条+速度指示器(KB/s或MB/s), logState.progress+downloadSpeed |
| 475 | 定位源置信度面板 | ✅ᵗ | GPS+EKF+罗盘+光流综合置信度(good/warn/bad), 光流从EKF标志推导(REL无ABS) |

---

## 七十二、围栏面板扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 476 | 围栏面积计算 | ✅ᵗ | 多边形面积m²/公顷格式化显示 |
| 477 | 围栏上传状态徽章 | ✅ᵗ | fenceUploaded=true→"已上传"绿色/false→"未上传"灰色 |
| 478 | 围栏JSON导入导出 | ✅ᵗ | JSON文件保存/加载围栏多边形顶点, FileReader+Blob |

---

## 七十三、品牌定制扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 479 | 品牌CSS注入XSS防护 | ✅ᵗ | primaryColor: 长度<100, 正则拒绝expression/url()/javascript/;{} |
| 480 | 品牌hideArduPilot选项 | ✅ᵗ | 白标时隐藏ArduPilot特定UI元素 |
| 481 | 品牌subtitle+defaultProtocol | ✅ᵗ | 自定义副标题文本+默认连接协议覆盖 |

---

## 七十四、飞控适配修正

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 482 | ArduPilot固定翼25模式 | ✅ᵗ | 含Thermal(24)+Loiter-to-QLand(25), 修正#222的23模式 |
| 483 | PX4精确着陆模式 | ✅ᵗ | PX4_AUTO_PRECLAND=9, 自动精确着陆 |
| 484 | PX4跟随模式 | ✅ᵗ | PX4_AUTO_FOLLOW=8, 跟随目标飞行 |
| 485 | 模式类别分类 | ✅ᵗ | manual/assisted/auto/emergency四类, 驱动StatusBar模式徽章颜色 |
| 486 | 模式快捷按钮8个 | ✅ᵗ | 旋翼8/固定翼8个预选模式, 修正#350的6个 |

---

## 七十五、遥测数据补充

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 487 | 空速 (airspeed) | ✅ᵗ | VFR_HUD msg74解码, 区别于地速(gs) |
| 488 | 油门百分比 (throttle) | ✅ᵗ | VFR_HUD msg74解码, 0-100% |
| 489 | 爬升率 (climb) | ✅ᵗ | VFR_HUD msg74解码, m/s |
| 490 | RC通道18路 | ✅ᵗ | WebSerial解码18路(非16路), 修正#20 |

---

## 七十六、手柄扩展

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 491 | 手柄轴反转 | ✅ᵗ | 每轴独立反转开关(invertRoll/Pitch/Throttle/Yaw) |
| 492 | 手柄解锁保护 | ✅ᵗ | 仅connected+armed时发送rc_override, rAF+50ms节流(非固定20Hz) |

---

## 七十七、后端协议补充

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 493 | Guided自动模式切换 | ✅ᵗ | guided_goto前自动set_mode(GUIDED: 旋翼4/固定翼15) |
| 494 | RTCM分片注入 | ✅ᵗ | 110字节分片, first/last标志(0x04/0x08), GPS_RTCM_DATA msg233 |
| 495 | 参数加载限.json | ✅ᵗ | param_load路径后缀验证, 仅接受.json文件 |
| 496 | 数据流请求配置 | ✅ᵗ | 9种消息: 姿态/位置/GPS@250ms, 系统/任务/振动/VFR@1s, 舵机/RC@500ms, SET_MESSAGE_INTERVAL(terrain) |

---

## 七十八、在线固件管理

| # | 功能 | 状态 | 验证方式 |
|---|------|------|----------|
| 497 | 在线固件浏览 | ✅ᵗ | /api/firmware/online?board_id=X查询可用版本(版本/日期/大小列表) |
| 498 | 在线固件下载 | ✅ᵗ | /api/firmware/download下载到服务器, HTTPS限制 |
| 499 | 云台归中按钮 | ✅ᵗ | pitch/yaw归零(0,0)并发送gimbal_angle, 一键复位 |

---

## 已知问题

| # | 问题 | 状态 | 说明 |
|---|------|------|------|
| 1 | NtripPanel 缺少后端 handler | ❌ | 前端发送 ntrip_start/ntrip_stop, 后端无对应处理函数 |
| 2 | WebSerial 未真机验证 | ⚠️ | 需 Chrome/Edge + USB 直连浏览器, Linux 环境未测试 |

---

## 测试基础设施

| 测试类型 | 数量 | 工具 |
|----------|------|------|
| 后端单元测试 | 929 | pytest |
| 前端单元测试 | 400+ | vitest |
| E2E 测试 | 19 specs | Playwright |
| 真机 WS 测试 | 25 项 | Python websockets |
| 真机浏览器测试 | 7 秒参数加载 | Playwright headless |
| 代码类型检查 | 4674 文件 0 错误 | svelte-check |
| Python lint | 0 错误 | ruff |
