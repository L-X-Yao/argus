# Verification status / 验证状态

What has actually been tested, and how. Updated after every real flight controller session.

本文件说明每项功能实际验证到什么程度，每次真机测试后更新。

**Argus has not been through proper flight testing.** Real FC below means a flight controller on the bench, powered over USB, with no motors running. Do not treat any row here as proof that something is safe in the air.

**Argus 尚未经过正式飞行测试。** 下文的“Real FC”指台架上的真实飞控，USB 供电，电机不转。这里的任何一行都不代表空中使用是安全的。

## Levels / 验证等级

| Level | Meaning | 含义 |
| --- | --- | --- |
| Real FC | Ran on a real flight controller on the bench | 在真实飞控上跑过（台架） |
| SITL | Ran against real ArduPilot firmware in simulation | 在 ArduPilot 真实固件的软件仿真上跑过 |
| Simulator | Ran end to end against Argus's built-in simulator | 只在 Argus 内置模拟器上端到端跑过 |
| Tests only | Only unit or contract tests: the bytes sent or the logic, never real firmware | 只有单元或契约测试，没有接过真实固件 |
| None | No test at all | 没有任何测试 |
| n/a | Not available on this link | 此链路不支持 |

Each row shows the highest level reached. Dates are in the Evidence column; an old date means that code may have changed since.

每行显示达到的最高等级。证据列带日期，日期较早说明之后代码可能有过改动。

## Summary / 总数

| Area | Items | Real FC | SITL | Simulator | Tests only | None | n/a |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Commands, backend | 53 | 19 | 22 | 0 | 12 | 0 | 0 |
| Commands, WebSerial | 53 | 9 | 31 | 0 | 3 | 0 | 10 |
| Messages, backend | 35 | 28 | 2 | 0 | 5 | 0 | 0 |
| Messages, WebSerial | 35 | 16 | 13 | 0 | 5 | 0 | 1 |
| REST routes | 28 | 6 | 5 | 8 | 9 | 0 | 0 |
| Panels | 80 | 13 | 3 | 21 | 41 | 2 | 0 |
| Platform | 40 | 8 | 4 | 7 | 15 | 3 | 3 |

## Commands / 飞控命令

| Command | Purpose | 作用 | Backend | WebSerial | Evidence |
| --- | --- | --- | --- | --- | --- |
| `arm` | Arm | 解锁 | SITL | SITL | CI on both links |
| `disarm` | Disarm | 上锁 | Real FC | SITL | Backend 2026-07-16, WebSerial CI |
| `force_disarm` | Force disarm | 强制上锁 | SITL | SITL | CI on both links |
| `mode` | Change mode | 切换模式 | SITL | SITL | CI on both links. Real FC 2026-11-05 used the SET_MODE message, since replaced by a command the FC answers |
| `rtl` | Return to launch | 返航 | SITL | SITL | CI on both links |
| `takeoff` | Take off | 起飞 | SITL | SITL | CI on both links |
| `guided_goto` | Fly to a point | 引导飞行 | SITL | SITL | WebSerial CI, backend manual SITL 2026-05 |
| `mission_start` | Start the mission | 开始任务 | SITL | SITL | CI on both links |
| `mission_set_current` | Jump to a waypoint | 跳到指定航点 | Tests only | SITL | WebSerial CI |
| `drop` | Release payload | 投放 | SITL | SITL | CI on both links |
| `drop_stop` | Stop release | 停止投放 | SITL | SITL | CI on both links |
| `do_set_roi` | Set region of interest | 设置兴趣点 | SITL | SITL | CI on both links |
| `rc_override` | RC override | 遥控覆盖 | SITL | SITL | CI on both links |
| `motor_test` | Motor test | 电机测试 | Real FC | SITL | Backend 2026-05, WebSerial CI |
| `motor_test_stop` | Stop motor test | 停止电机测试 | SITL | SITL | CI on both links |
| `mission_upload` | Upload mission | 上传航线 | Real FC | Real FC | WebSerial 2026-11-05, backend 2026-05, CI |
| `mission_download` | Download mission | 下载航线 | Real FC | Real FC | Both 2026-11-05 |
| `mission_clear` | Clear mission | 清除航线 | Real FC | Real FC | WebSerial 2026-11-05, backend 2026-05, CI |
| `fence_upload` | Upload fence | 上传围栏 | Real FC | Real FC | Both 2026-11-05, read back with pymavlink |
| `fence_clear` | Clear fence on the FC | 清除飞控上的围栏 | Real FC | Real FC | Both 2026-11-05, read back with pymavlink |
| `rally_upload` | Upload rally points | 上传备降点 | SITL | SITL | CI on both links. WebSerial reads the coordinates back from the FC |
| `rally_clear` | Clear rally points on the FC | 清除飞控上的备降点 | SITL | SITL | CI on both links. WebSerial reads the count back from the FC |
| `param_request_all` | Read all parameters | 读全部参数 | Real FC | Real FC | Both 2026-11-05, 1028 parameters |
| `param_set` | Write a parameter | 写参数 | Real FC | Real FC | WebSerial 2026-11-05 with 4 types, backend 2026-05, CI |
| `param_save` | Back up to a file | 备份参数到文件 | Real FC | n/a | Backend 2026-05, CI |
| `param_load` | Restore from a file | 从文件恢复参数 | SITL | n/a | CI |
| `cal_gyro` | Gyro calibration | 陀螺仪校准 | Real FC | SITL | Backend 2026-05, CI on both links |
| `cal_level` | Level calibration | 水平校准 | SITL | SITL | CI on both links |
| `cal_baro` | Barometer calibration | 气压计校准 | SITL | SITL | CI on both links |
| `cal_compass` | Compass calibration | 罗盘校准 | Real FC | SITL | Backend 2026-05, WebSerial CI, SITL recording replayed in CI |
| `cal_compass_accept` | Accept compass result | 确认罗盘结果 | Real FC | SITL | Backend 2026-05, WebSerial CI, SITL recording replayed in CI |
| `cal_accel` | Accelerometer calibration | 加速度计校准 | Real FC | SITL | Backend 2026-05, WebSerial CI, SITL recording replayed in CI |
| `cal_accel_next` | Next calibration pose | 校准下一姿态 | Real FC | SITL | Backend 2026-05, WebSerial CI, SITL recording replayed in CI |
| `cal_cancel` | Cancel calibration | 取消校准 | Real FC | SITL | Backend 2026-05, CI on both links |
| `log_list` | List logs | 日志列表 | Real FC | Real FC | Both 2026-11-05 |
| `log_download` | Download a log | 下载日志 | Real FC | Real FC | Both 2026-11-05, same sha256 on both links |
| `log_cancel` | Cancel a download | 取消下载 | SITL | SITL | CI on both links |
| `reboot` | Reboot the FC | 重启飞控 | Tests only | SITL | WebSerial CI |
| `reboot_bootloader` | Reboot to bootloader | 重启到 Bootloader | Tests only | SITL | WebSerial CI |
| `serial_control` | MAVLink console | MAVLink 控制台 | Real FC | n/a | Backend 2026-05, CI |
| `inspector_toggle` | Message inspector | 消息检查器开关 | SITL | n/a | CI, local state only |
| `set_vtype` | Set vehicle type | 手动设置机型 | SITL | n/a | CI, local state only |
| `switch_vehicle` | Switch vehicle | 切换当前飞机 | SITL | n/a | CI, local state only |
| `clear_summary` | Clear flight summary | 清除飞行总结 | SITL | n/a | CI, local state only |
| `ntrip_start` | Start NTRIP | 启动 NTRIP | Tests only | n/a | No real base station |
| `ntrip_stop` | Stop NTRIP | 停止 NTRIP | Tests only | n/a | No real base station |
| `inject_rtcm` | Inject RTCM | 注入 RTCM | Tests only | n/a | No real base station |
| `gimbal_angle` | Gimbal angle | 云台角度 | Tests only | SITL | WebSerial CI with a servo gimbal in SITL |
| `gimbal_pitchyaw` | Gimbal pitch and yaw | 云台俯仰偏航 | Tests only | SITL | WebSerial CI with a servo gimbal in SITL |
| `camera_trigger` | Take a photo | 拍照 | Tests only | SITL | WebSerial CI, no real camera |
| `camera_video_start` | Start recording | 开始录像 | Tests only | Tests only | Bytes checked. SITL answers but refuses: no camera |
| `camera_video_stop` | Stop recording | 停止录像 | Tests only | Tests only | Bytes checked. SITL answers but refuses: no camera |
| `camera_zoom` | Zoom | 相机变焦 | Tests only | Tests only | Bytes checked. SITL answers but refuses: no camera |

CI drives the SITL rows on both links. WebSerial runs through a stand-in for the serial port (`tests/e2e/run-webserial-sitl.sh`), so everything above the port meets real firmware, and the USB layer itself is only covered by the Real FC rows.

CI 在两条链路上都驱动 SITL。WebSerial 用模拟串口接真实固件（`tests/e2e/run-webserial-sitl.sh`），串口以上的代码都跑过真实固件，USB 这一层只有 Real FC 那些行覆盖。

## Messages from the FC / 飞控消息

| Message | Used for | 用途 | Backend | WebSerial | Evidence |
| --- | --- | --- | --- | --- | --- |
| `HEARTBEAT` | Link, mode, armed | 链路、模式、解锁状态 | Real FC | Real FC | Both 2026-11-05 |
| `SYS_STATUS` | Battery | 电池 | Real FC | Real FC | Both 2026-11-05, no battery fitted |
| `PARAM_VALUE` | Parameters | 参数 | Real FC | Real FC | Both 2026-11-05 |
| `GPS_RAW_INT` | GPS fix, satellites | GPS 定位和卫星数 | Real FC | Real FC | Both 2026-11-05 |
| `RAW_IMU` | Compass field | 罗盘磁场 | Real FC | SITL | Backend 2026-11-05, WebSerial CI |
| `ATTITUDE` | Attitude | 姿态 | Real FC | Real FC | Both 2026-11-05 |
| `GLOBAL_POSITION_INT` | Position, heading | 位置和航向 | Real FC | Real FC | Both 2026-11-05 |
| `SERVO_OUTPUT_RAW` | Motor outputs | 电机输出 | Real FC | SITL | Backend 2026-11-05, WebSerial CI |
| `MISSION_REQUEST` | Mission upload | 航线上传 | Tests only | Tests only | The FC used the INT form |
| `MISSION_CURRENT` | Mission progress | 任务进度 | Real FC | SITL | Backend 2026-05, WebSerial CI |
| `MISSION_COUNT` | Mission download | 航线下载 | Real FC | Real FC | Both 2026-11-05 |
| `MISSION_ITEM_REACHED` | Waypoint reached | 到达航点 | SITL | SITL | CI on both links |
| `MISSION_ACK` | Upload result | 上传结果 | Real FC | Real FC | Both 2026-11-05 |
| `MISSION_REQUEST_INT` | Mission upload | 航线上传 | Real FC | Real FC | Both 2026-11-05 |
| `RC_CHANNELS` | RC input | 遥控输入 | Real FC | SITL | Backend 2026-11-05, WebSerial CI, no receiver fitted |
| `MISSION_ITEM_INT` | Mission download | 航线下载 | Real FC | Real FC | Both 2026-11-05 |
| `VFR_HUD` | Airspeed, climb, throttle | 空速、爬升、油门 | Real FC | Real FC | Both 2026-11-05 |
| `COMMAND_ACK` | Command result | 命令结果 | Real FC | SITL | Backend 2026-07-16, both links CI |
| `LOG_ENTRY` | Log list | 日志列表 | Real FC | Real FC | Both 2026-11-05 |
| `LOG_DATA` | Log download | 日志下载 | Real FC | Real FC | Both 2026-11-05 |
| `SERIAL_CONTROL` | MAVLink console | MAVLink 控制台 | Real FC | n/a | Backend 2026-05 |
| `TERRAIN_REPORT` | Terrain height | 地形高度 | Real FC | Tests only | Backend 2026-05, both links compared on the same frame |
| `BATTERY_STATUS` | Cell voltages | 电芯电压 | Real FC | SITL | Backend 2026-05, WebSerial CI |
| `AUTOPILOT_VERSION` | Firmware version | 固件版本 | Real FC | SITL | Backend 2026-11-05, WebSerial CI |
| `MOUNT_STATUS` | Gimbal angles | 云台角度 | Tests only | Tests only | No current firmware sends it: both links compared on the same frame |
| `WIND` | Wind | 风速风向 | Tests only | Tests only | Both links compared on the same frame, the FC sent none |
| `MAG_CAL_PROGRESS` | Compass calibration | 罗盘校准进度 | Real FC | SITL | Backend 2026-05, WebSerial CI |
| `MAG_CAL_REPORT` | Compass calibration | 罗盘校准结果 | Real FC | SITL | Backend 2026-05, WebSerial CI |
| `EKF_STATUS_REPORT` | EKF health | EKF 状态 | Real FC | Real FC | Both 2026-11-05 |
| `VIBRATION` | Vibration | 振动 | Real FC | SITL | Backend 2026-11-05, WebSerial CI |
| `HOME_POSITION` | Home | Home 点 | Real FC | Real FC | Both 2026-11-05 |
| `EXTENDED_SYS_STATE` | Tells a QuadPlane from a plane | 区分 QuadPlane 和固定翼 | SITL | SITL | Backend CI on a QuadPlane. WebSerial CI on Copter, which reports the same field |
| `ADSB_VEHICLE` | Nearby aircraft | 周边飞机 | Tests only | Tests only | No ADS-B receiver |
| `STATUSTEXT` | FC messages | 飞控文字消息 | Real FC | Real FC | Both 2026-11-05 |
| `GIMBAL_DEVICE_ATTITUDE_STATUS` | Gimbal attitude | 云台姿态 | Tests only | SITL | WebSerial CI with a servo gimbal in SITL |

## REST routes / REST 接口

Real FC here means the route was in use during a session with a real flight controller.

这里的 Real FC 指该接口在真实飞控的测试中实际用到。

| Route | Purpose | 作用 | Level | Evidence |
| --- | --- | --- | --- | --- |
| `GET /` | The app | 应用页面 | Real FC | 2026-11-05 |
| `GET /health` | Health check | 健康检查 | Real FC | 2026-11-05 |
| `WEBSOCKET /ws` | Live telemetry and commands | 实时遥测和命令 | Real FC | 2026-11-05 |
| `GET /api/auth/status` | Is a token required | 是否需要 Token | Real FC | 2026-11-05 |
| `GET /api/ports` | Serial port list | 串口列表 | Real FC | 2026-11-05 |
| `GET /api/tile/{style}/{z}/{x}/{y}` | Map tiles | 地图瓦片 | Real FC | 2026-11-05, default map only |
| `GET /api/log` | Download the CSV log | 下载 CSV 日志 | SITL | CI |
| `GET /api/param_meta` | Parameter descriptions | 参数说明 | SITL | CI |
| `GET /api/tile_cache` | Tile cache size | 瓦片缓存大小 | SITL | CI |
| `POST /api/tile_cache_clear` | Clear the tile cache | 清除瓦片缓存 | SITL | CI |
| `POST /api/firmware/upload` | Store a firmware file | 保存固件文件 | SITL | CI, stores only, no flashing |
| `GET /sw.js` | Service worker | Service Worker | Simulator | e2e |
| `GET /manifest.json` | PWA manifest | PWA 清单 | Simulator | e2e |
| `POST /api/auth/login` | Log in with a token | Token 登录 | Simulator | e2e, real Windows each release |
| `GET /api/session` | Session info | 会话信息 | Simulator | e2e |
| `GET /api/version` | Version | 版本 | Simulator | e2e, real Windows each release |
| `GET /api/tile_sources` | Map sources | 地图源列表 | Simulator | Integration tests |
| `GET /api/video` | Video stream | 视频流 | Simulator | Integration tests, no real camera |
| `GET /api/video/stop` | Stop video | 停止视频 | Simulator | Integration tests, no real camera |
| `POST /api/auth/generate` | Generate a token | 生成 Token | Tests only | Unit tests |
| `POST /api/tile_bulk_download` | Download tiles for offline use | 批量下载瓦片 | Tests only | Unit tests |
| `GET /api/mbtiles/list` | Offline map list | 离线地图列表 | Tests only | Unit tests |
| `GET /api/mbtiles/{name}/{z}/{x}/{y}` | Offline map tiles | 离线地图瓦片 | Tests only | Unit tests |
| `GET /api/terrain/elevation` | Terrain height | 地形高度 | Tests only | Unit tests |
| `GET /api/firmware/list` | Stored firmware | 已保存固件 | Tests only | Unit tests |
| `GET /api/firmware/online` | Firmware browser | 在线固件 | Tests only | Unit tests |
| `POST /api/firmware/download` | Download firmware | 下载固件 | Tests only | Unit tests |
| `GET /api/video/capabilities` | Video support check | 视频能力检测 | Tests only | Unit tests |

## Panels / 界面面板

Four panels have code but no way to open them, marked in the Evidence column. They were never reachable from the UI.

有 4 个面板有代码，但界面上没有入口，在证据列注明。它们从未对用户开放。

| Panel | Area | 作用 | Level | Evidence |
| --- | --- | --- | --- | --- |
| `ChartPanel` | core | 查看实时遥测曲线 | Simulator | e2e: connected-flow, error-boundary |
| `ConnectionForm` | core | 连接或断开飞控 | Real FC | 2026-11-05 on both links |
| `ControlPanel` | core | 解锁起飞切模式 | Simulator | e2e: connected-flow, drone-control |
| `EventLog` | core | 筛选导出事件日志 | Simulator | e2e: connected-flow, event-log |
| `HudOverlay` | core | 看主飞行姿态仪表 | Real FC | 2026-11-05 on both links |
| `LazyPanelHost` | core | 按需加载弹出面板 | Real FC | 2026-11-05 on both links |
| `MapControls` | core | 放大地图时快捷操控 | Tests only | Logic: transport.dispatch |
| `MapView` | core | 看地图并点选航点 | Real FC | 2026-11-05 on both links |
| `StatusBar` | core | 看链路电池定位状态 | Real FC | 2026-11-05 on both links |
| `ToastContainer` | core | 查看操作提示消息 | Real FC | 2026-11-05 on both links |
| `DroneLayer` | layers | 地图上看飞机位置 | Real FC | 2026-11-05 on both links |
| `FenceLayer` | layers | 地图上看围栏范围 | Tests only | Browser test: a saved fence is drawn |
| `OrthoLayer` | layers | 在地图上显示正射图 | Tests only | Browser test, 2D map only |
| `RallyLayer` | layers | 在地图上显示备降点 | Tests only | Browser test |
| `GuidedLayer` | layers | 地图上看引导目标 | SITL | WebSerial CI: right click, target marked, the vehicle moves off |
| `ReplayLayer` | layers | 地图上看回放位置 | Tests only | Browser test: draws from its state |
| `SurveyLayer` | layers | 地图上看测绘区域 | Tests only | Browser test: draws from its state |
| `WaypointLayer` | layers | 地图上拖改航点 | Simulator | e2e: mission |
| `AirspacePanel` | map | 查看机场限飞区 | Tests only | Logic: units. Demo data |
| `Compass3DPanel` | map | 校准罗盘看磁场球 | Tests only | Logic: transport |
| `Map3DView` | map | 三维地图查看编辑 | Simulator | e2e: map3d |
| `Mission3DPanel` | map | 三维预览航线 | Tests only | Browser test: opens without an error |
| `OfflineMapPanel` | map | 下载离线地图瓦片 | Tests only | Browser test: opens without an error |
| `OrthoOverlayPanel` | map | 叠加正射图 | Tests only | Browser test: image reaches the map, survives a reload, wrong corners refused |
| `CorridorPanel` | mission | 生成走廊扫描航线 | Tests only | Browser test: opens without an error |
| `RallyPanel` | mission | 添加并上传备降点 | Tests only | Browser test. Upload and clear run on SITL through their commands |
| `FencePanel` | mission | 绘制上传地理围栏 | Real FC | 2026-11-05, Clear on FC through the panel on WebSerial |
| `MissionPanel` | mission | 编辑上传任务航点 | Simulator | e2e: mission, connected-flow |
| `MissionProgress` | mission | 看任务执行进度 | Tests only | Logic: units |
| `PoiPanel` | mission | 设置相机兴趣点 | Tests only | Logic: transport.dispatch |
| `SurveyPanel` | mission | 生成测绘网格航线 | Tests only | Logic: survey |
| `TerrainProfilePanel` | mission | 查看航线地形剖面 | Tests only | Logic: terrain |
| `AutoTunePanel` | params | 启动自动调参 | Tests only | Logic: paramStore |
| `FailsafeConfigPanel` | params | 配置失控保护 | Tests only | Logic: paramStore |
| `FlightModePanel` | params | 配置六档飞行模式 | Tests only | Logic: paramStore |
| `ParamDiffPanel` | params | 对比参数文件差异 | Tests only | Logic: paramStore |
| `ParamPanel` | params | 读取编辑飞控参数 | Real FC | 2026-11-05 on both links, reading; writes used the same dispatch, not the row editor |
| `PidPanel` | params | 调节PID参数 | Tests only | Logic: paramStore |
| `PowerCalPanel` | params | 校准电压电流 | Tests only | Logic: paramStore |
| `AiAnnotationPanel` | planning | 标注图像缺陷 | None | No test. Auto-detect is a stub. No way to open it |
| `AiPlannerPanel` | planning | 文字生成航线 | None | No test. Rule-based parser, not an LLM. No way to open it |
| `AnnotationPanel` | planning | 记录地图标注点 | Tests only | Browser test: opens without an error |
| `CustomDashboard` | planning | 自定义仪表 | SITL | WebSerial CI, live values |
| `OverlapCalcPanel` | planning | 计算相机重叠率 | Tests only | Browser test: opens without an error |
| `SchedulerPanel` | planning | 定时执行任务 | Tests only | Logic: scheduler. No way to open it |
| `ScriptPanel` | planning | 运行用户脚本 | Tests only | Logic: ws. No way to open it |
| `CalibrationPanel` | setup | 校准传感器 | Simulator | e2e: connected-flow |
| `EscCalPanel` | setup | 校准电调 | Tests only | Logic: transport.dispatch |
| `FirmwarePanel` | setup | 上传固件并重启 | Simulator | e2e: settings, mobile |
| `FrameSelectPanel` | setup | 选择机架类型 | Tests only | Logic: paramStore |
| `MotorTestPanel` | setup | 逐个测试电机 | Tests only | Logic: transport.dispatch |
| `NtripPanel` | setup | 接入RTK | Simulator | e2e: command-palette. Opens; no real base station |
| `PositionSourcePanel` | setup | 查看定位源 | SITL | WebSerial CI, GPS and EKF rows |
| `RcCalibPanel` | setup | 校准遥控器行程 | Tests only | Logic: transport.parity |
| `SetupWizard` | setup | 按向导完成初始设置 | Tests only | Logic: panels |
| `CommandPalette` | shared | 搜索并执行命令 | Simulator | e2e: command-palette, keyboard |
| `ConfirmDialog` | shared | 确认危险操作 | Real FC | 2026-11-05 |
| `FlightSummary` | shared | 查看飞行总结 | Tests only | Logic: units |
| `LoginDialog` | shared | 输入令牌登录 | Simulator | e2e: auth |
| `PreflightPanel` | shared | 查看起飞前检查 | Real FC | 2026-11-05 on both links |
| `RolePanel` | shared | 切换操作角色 | Tests only | Browser test: opens without an error. Demo, not wired to roles |
| `SettingsPanel` | shared | 修改应用设置 | Simulator | e2e: settings, mobile |
| `SlideConfirm` | shared | 滑动确认关键指令 | Tests only | Logic: stores |
| `EkfPanel` | telemetry | 查看导航滤波状态 | Simulator | e2e: connected-flow, navigation |
| `RcPanel` | telemetry | 查看遥控通道 | Simulator | e2e: connected-flow, navigation |
| `ServoPanel` | telemetry | 查看舵机输出 | Simulator | e2e: connected-flow, navigation |
| `TelemetryOverlay` | telemetry | 飞行中看关键遥测 | Real FC | 2026-11-05 on both links |
| `VibrationPanel` | telemetry | 查看振动水平 | Simulator | e2e: connected-flow, navigation |
| `AdvancedCmdPanel` | tools | 给航点加高级指令 | Tests only | Logic: missionUpload |
| `ConsolePanel` | tools | 发送飞控控制台命令 | Simulator | e2e: memory |
| `FFTPanel` | tools | 分析日志频谱 | Tests only | Logic: dflog |
| `FlightReportPanel` | tools | 填写导出飞行报告 | Tests only | Browser test: opens without an error |
| `InspectorPanel` | tools | 检视实时消息流 | Simulator | e2e: memory |
| `LogPanel` | tools | 下载机载日志 | Real FC | 2026-11-05 on both links |
| `LogViewerPanel` | tools | 绘图查看日志 | Tests only | Logic: dflog |
| `RemotePanel` | tools | 查看会话复制链接 | Tests only | Browser test: opens without an error. Partly wired |
| `ReplayPanel` | tools | 加载并回放飞行日志 | Simulator | e2e: map3d |
| `FleetDashboard` | vehicle | 查看并切换多机 | Tests only | Logic: ws |
| `GimbalPanel` | vehicle | 控制云台相机 | Simulator | e2e: command-palette. Opens; no gimbal |
| `VideoOverlay` | vehicle | 观看视频流 | Simulator | e2e: memory. No real camera |

## Platform / 平台与功能

| Feature | 功能 | Level | Evidence |
| --- | --- | --- | --- |
| Serial through the backend | 后端串口 | Real FC | 2026-11-05 |
| WebSerial | 浏览器直连 USB | Real FC | 2026-11-05, Chromium on Linux through usbipd |
| Log download speed | 日志下载速度 | Real FC | 2026-11-05, about 700 KB/s on both links |
| Reconnect after a lost link | 断链重连 | Real FC | 2026-11-05, USB pulled on both links. WebSerial keeping the last state through a drop came later: unit tests only |
| PFD and HUD | PFD 和 HUD | Real FC | 2026-11-05 on both links; west heading and RC not checked |
| Preflight checks | 起飞前检查 | Real FC | 2026-11-05 on both links |
| Copter | 多旋翼 | Real FC | Bench 2026-11-05, flight modes in SITL |
| Linux from source | Linux 源码运行 | Real FC | Daily development |
| TCP | TCP 连接 | SITL | CI |
| Plane and VTOL | 固定翼和 VTOL | SITL | CI, a plain plane and a QuadPlane: recognition, mode numbers for Hold and Land. Real telemetry 2026-05. No flight in CI |
| Rover | 地面车 | SITL | CI. No drive in CI |
| 2D map | 2D 地图 | Simulator | e2e; only the default of 8 sources exercised |
| 3D map | 3D 地图 | Simulator | e2e, headless Chromium; Windows browser not checked |
| PWA and offline use | PWA 和离线 | Simulator | e2e, Chromium |
| Several browser clients | 多浏览器客户端 | Simulator | Integration tests |
| Video and AR overlay | 视频和 AR 叠加 | Simulator | Integration tests, no real camera |
| Token login | Token 登录 | Simulator | e2e, real Windows each release |
| Windows package | Windows 发布包 | Simulator | Smoke test on real Windows each release |
| UDP | UDP 连接 | Tests only | Unit tests |
| Submarine | 水下潜航器 | SITL | CI. No dive in CI |
| Several vehicles at once | 多机同屏 | Tests only | Unit tests |
| Offline mbtiles maps | 离线 mbtiles 地图 | Tests only | Unit tests |
| Survey and pattern planning | 测绘和图案规划 | Tests only | Unit tests |
| Mission file formats | 航线文件格式 | Tests only | Unit tests |
| Terrain profile | 地形剖面 | Tests only | Unit tests |
| Voice and audio alerts | 语音和声音告警 | Tests only | Unit tests |
| Gamepad | 手柄 | Tests only | Unit tests |
| 10 languages | 10 种语言 | Tests only | Key completeness only, not reviewed by native speakers |
| Plugins and scripts | 插件和脚本 | Tests only | Unit tests |
| RTK through NTRIP | NTRIP RTK | Tests only | No real base station |
| Cross-site request blocking | 跨站请求拦截 | Tests only | Unit tests, real Windows each release |
| SSRF and path traversal protection | SSRF 和路径穿越防护 | Tests only | Unit tests |
| STATUSTEXT filter | STATUSTEXT 过滤 | Tests only | Unit tests |
| Real flight | 真实飞行 | None | Never properly flown |
| Right-to-left layout | 阿拉伯语从右到左布局 | Tests only | Browser test: page turns around and stays inside the window |
| macOS | macOS | None | Never run |
| Desktop app (Tauri) | 桌面版（Tauri） | None | Not built |
| Firmware flashing | 固件刷写 | n/a | Not implemented |
| PX4 | PX4 | n/a | Refused on connect, not implemented |
| White-label branding | 白标定制 | n/a | Code exists but is not wired in |

## Not verified yet, by risk / 未验证项（按风险排序）

1. **Real flight.** Nothing has flown. Everything below is a bench or simulation result at best.
2. **Arm, take off, RTL and mission start on a real FC.** These have only run in SITL. They need a battery, so they need a separate, deliberate session.
3. **Calibration and reboot on a real FC over WebSerial.** SITL only so far, and compass and accelerometer need the board turned by hand.
4. **RTK, gimbal, camera and ADS-B.** These need hardware that has not been available.
5. **Flight on vehicles other than Copter.** Plane, QuadPlane, Rover and Sub run in SITL in CI through the backend: recognition, mode numbers, parameters, missions and arming, not a flight.
6. **WebSerial in Chrome on Windows.** The 2026-11-05 run used Chromium on Linux with the port chooser automated.
7. **Four panels nobody can open.** Scripts, scheduler, AI planner and AI annotation exist in code only.

1. **真实飞行。** 没有飞过。下面都只是台架或仿真结果。
2. **真机上的解锁、起飞、返航、开始任务。** 只在 SITL 跑过。这些需要接电池，要单独安排。
3. **真机上经 WebSerial 的校准和重启。** 目前只在 SITL 跑过，罗盘和加速度计需要手动翻转板子。
4. **RTK、云台、相机、ADS-B。** 缺硬件。
5. **多旋翼以外机型的飞行。** 固定翼、QuadPlane、地面车、水下机器人在 CI 里经后端跑 SITL，覆盖机型识别、模式号、参数、航线和解锁，没有跑飞行。
6. **Windows 上 Chrome 的 WebSerial。** 2026-11-05 的测试用的是 Linux 上的 Chromium，端口选择由脚本代替。
7. **4 个打不开的面板。** 脚本、定时任务、AI 规划、AI 标注只存在于代码中。

## Keeping this file honest / 维护规则

`tests/test_contract_verification_doc.py` fails when a command, message, route or panel is missing here, or when the counts in the summary stop matching the tables. Levels go up only with evidence: a date and how it was checked.

新增命令、消息、接口或面板而没写进本文件，或总数和表格对不上时，`tests/test_contract_verification_doc.py` 会失败。等级只有在有证据时才能提升，要写明日期和验证方式。

`docs/FEATURE_CHECKLIST.md` is a frozen v3.4 snapshot with 499 finer-grained items. This file is the current status.

`docs/FEATURE_CHECKLIST.md` 是冻结在 v3.4 的快照，有 499 条更细的条目。当前状态以本文件为准。
