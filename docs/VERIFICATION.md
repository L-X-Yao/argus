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
| Commands, backend | 53 | 19 | 28 | 0 | 6 | 0 | 0 |
| Commands, WebSerial | 53 | 12 | 28 | 0 | 3 | 0 | 10 |
| Messages, backend | 35 | 28 | 3 | 0 | 4 | 0 | 0 |
| Messages, WebSerial | 35 | 17 | 13 | 0 | 4 | 0 | 1 |
| REST routes | 28 | 6 | 5 | 17 | 0 | 0 | 0 |
| Panels | 82 | 14 | 34 | 18 | 14 | 2 | 0 |
| Platform | 50 | 8 | 14 | 13 | 10 | 2 | 3 |

## Commands / 飞控命令

| Command | Purpose | 作用 | Backend | WebSerial | Evidence |
| --- | --- | --- | --- | --- | --- |
| `arm` | Arm | 解锁 | SITL | SITL | CI on both links |
| `disarm` | Disarm | 上锁 | Real FC | SITL | Backend 2026-07-16, WebSerial CI |
| `force_disarm` | Force disarm | 强制上锁 | SITL | SITL | CI on both links |
| `mode` | Change mode | 切换模式 | Real FC | Real FC | Both 2026-11-06 on Windows, the command the FC answers: in about 0.3 s, and Stabilize put back. CI on both links |
| `rtl` | Return to launch | 返航 | SITL | SITL | CI on both links |
| `takeoff` | Take off | 起飞 | SITL | SITL | CI on both links |
| `guided_goto` | Fly to a point | 引导飞行 | SITL | SITL | WebSerial CI, backend manual SITL 2026-05 |
| `mission_start` | Start the mission | 开始任务 | SITL | SITL | CI on both links |
| `mission_set_current` | Jump to a waypoint | 跳到指定航点 | SITL | SITL | CI on both links. 2026-11-13: the seq comes from the map a download builds; with a speed insert the old `index + 2` jumped to an earlier waypoint (contract test) |
| `drop` | Release payload | 投放 | SITL | SITL | CI on both links |
| `drop_stop` | Stop release | 停止投放 | SITL | SITL | CI on both links |
| `do_set_roi` | Set region of interest | 设置兴趣点 | SITL | SITL | CI on both links |
| `rc_override` | RC override | 遥控覆盖 | SITL | SITL | CI on both links |
| `motor_test` | Motor test | 电机测试 | Real FC | SITL | Backend 2026-05, WebSerial CI |
| `motor_test_stop` | Stop motor test | 停止电机测试 | SITL | SITL | CI on both links |
| `mission_upload` | Upload mission | 上传航线 | Real FC | Real FC | WebSerial 2026-11-05, backend 2026-05, CI |
| `mission_download` | Download mission | 下载航线 | Real FC | Real FC | Both 2026-11-05. 2026-11-13: the rebuilt list maps every waypoint to its MAVLink seq, and keeps the camera, servo, ROI, yaw and VTOL items and p3/p4, which a download then upload used to delete (contract tests) |
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
| `cal_compass` | Compass calibration | 罗盘校准 | SITL | SITL | CI on both links. On a real FC 2026-11-06 it starts and cancels on both links; a whole run needs the board turned by hand |
| `cal_compass_accept` | Accept compass result | 确认罗盘结果 | SITL | SITL | CI on both links. Backend on a real FC 2026-05, before the link took over accepting: worth a new hardware run |
| `cal_accel` | Accelerometer calibration | 加速度计校准 | Real FC | SITL | Backend 2026-05, WebSerial CI, SITL recording replayed in CI |
| `cal_accel_next` | Next calibration pose | 校准下一姿态 | Real FC | SITL | Backend 2026-05, WebSerial CI, SITL recording replayed in CI |
| `cal_cancel` | Cancel calibration | 取消校准 | Real FC | Real FC | Both 2026-11-06 on Windows, CI on both links |
| `log_list` | List logs | 日志列表 | Real FC | Real FC | Both 2026-11-06 on Windows |
| `log_download` | Download a log | 下载日志 | Real FC | Real FC | Both 2026-11-06 on Windows, same sha256 on both links |
| `log_cancel` | Cancel a download | 取消下载 | SITL | SITL | CI on both links |
| `reboot` | Reboot the FC | 重启飞控 | Real FC | Real FC | Both 2026-11-06 on Windows, disarmed. WebSerial comes back by the USB button, the backend by itself |
| `reboot_bootloader` | Reboot to bootloader | 重启到 Bootloader | SITL | SITL | CI on both links |
| `serial_control` | MAVLink console | MAVLink 控制台 | Real FC | n/a | Backend 2026-05, CI |
| `inspector_toggle` | Message inspector | 消息检查器开关 | SITL | n/a | CI, local state only |
| `set_vtype` | Set vehicle type | 手动设置机型 | SITL | n/a | CI, local state only |
| `switch_vehicle` | Switch vehicle | 切换当前飞机 | SITL | n/a | CI: two vehicles on one link |
| `clear_summary` | Clear flight summary | 清除飞行总结 | SITL | n/a | CI, local state only |
| `ntrip_start` | Start NTRIP | 启动 NTRIP | Tests only | n/a | No real base station |
| `ntrip_stop` | Stop NTRIP | 停止 NTRIP | Tests only | n/a | No real base station |
| `inject_rtcm` | Inject RTCM | 注入 RTCM | Tests only | n/a | No real base station |
| `gimbal_angle` | Gimbal angle | 云台角度 | SITL | SITL | CI on both links with a servo gimbal in SITL |
| `gimbal_pitchyaw` | Gimbal pitch and yaw | 云台俯仰偏航 | SITL | SITL | CI on both links with a servo gimbal in SITL |
| `camera_trigger` | Take a photo | 拍照 | SITL | SITL | CI on both links, no real camera |
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
| `LOG_DATA` | Log download | 日志下载 | Real FC | Real FC | Both 2026-11-06 on Windows |
| `SERIAL_CONTROL` | MAVLink console | MAVLink 控制台 | Real FC | n/a | Backend 2026-05 |
| `TERRAIN_REPORT` | Height above ground | 离地高度 | Real FC | Real FC | Both 2026-11-06 with terrain data: the reading follows altitude less ground. Backend on the same FC: hidden with no terrain and with no position |
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
| `GIMBAL_DEVICE_ATTITUDE_STATUS` | Gimbal attitude | 云台姿态 | SITL | SITL | CI on both links with a servo gimbal in SITL |

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
| `GET /api/video` | Video stream | 视频流 | Simulator | Integration tests. 2026-11-10: real ffmpeg, an HTTP test stream at a private address came out as MJPEG. RTSP by its command line only, no real camera |
| `GET /api/video/stop` | Stop video | 停止视频 | Simulator | Integration tests, no real camera |
| `POST /api/auth/generate` | Generate a token | 生成 Token | Simulator | Integration tests |
| `POST /api/tile_bulk_download` | Download tiles for offline use | 批量下载瓦片 | Simulator | Integration tests: counts tiles, and refuses OpenStreetMap, whose server forbids bulk download. Whether a map server answers is up to it |
| `GET /api/mbtiles/list` | Offline map list | 离线地图列表 | Simulator | Integration tests with a real file |
| `GET /api/mbtiles/{name}/{z}/{x}/{y}` | Offline map tiles | 离线地图瓦片 | Simulator | Integration tests with a real file |
| `GET /api/terrain/elevation` | Terrain height | 地形高度 | Simulator | Integration tests against the real terrain server |
| `GET /api/firmware/list` | Stored firmware | 已保存固件 | Simulator | Integration tests |
| `GET /api/firmware/online` | Firmware browser | 在线固件 | Simulator | Integration tests against firmware.ardupilot.org |
| `POST /api/firmware/download` | Download firmware | 下载固件 | Simulator | Integration tests against firmware.ardupilot.org |
| `GET /api/video/capabilities` | Video support check | 视频能力检测 | Simulator | Integration tests |

## Panels / 界面面板

Four panels have code but no way to open them, marked in the Evidence column. They were never reachable from the UI.

有 4 个面板有代码，但界面上没有入口，在证据列注明。它们从未对用户开放。

| Panel | Area | 作用 | Level | Evidence |
| --- | --- | --- | --- | --- |
| `ChartPanel` | core | 查看实时遥测曲线 | Simulator | e2e: connected-flow, error-boundary |
| `ConnectionForm` | core | 连接或断开飞控 | Real FC | 2026-11-05 on both links |
| `ControlPanel` | core | 解锁起飞切模式 | SITL | CI by clicks on firmware: arm, takeoff, pause, RTL, by FC mode |
| `EventLog` | core | 筛选导出事件日志 | Simulator | e2e: connected-flow, event-log |
| `HudOverlay` | core | 看主飞行姿态仪表 | Real FC | 2026-11-05 on both links |
| `LazyPanelHost` | core | 按需加载弹出面板 | Real FC | 2026-11-05 on both links |
| `MapControls` | core | 放大地图时快捷操控 | SITL | CI by clicks on firmware: pause by FC mode |
| `MapView` | core | 看地图并点选航点 | Real FC | 2026-11-05 on both links |
| `StatusBar` | core | 看链路电池定位状态 | Real FC | 2026-11-06 on both links on Windows. The E: counter stayed at 0 for 75 s on the backend, where a parser fix stopped it counting skipped messages |
| `ToastContainer` | core | 查看操作提示消息 | Real FC | 2026-11-05 on both links |
| `AssistantPreviewLayer` | layers | 地图上看 AI 提议的航线 | Simulator | e2e: assistant: drawn while the proposal waits, gone once it is decided |
| `DroneLayer` | layers | 地图上看飞机位置 | Real FC | 2026-11-05 on both links |
| `FenceLayer` | layers | 地图上看围栏范围 | Tests only | Browser test: a saved fence is drawn |
| `OrthoLayer` | layers | 在地图上显示正射图 | Tests only | Browser test, 2D map only |
| `RallyLayer` | layers | 在地图上显示备降点 | Tests only | Browser test |
| `GuidedLayer` | layers | 地图上看引导目标 | SITL | WebSerial CI: right click, target marked, the vehicle moves off |
| `ReplayLayer` | layers | 地图上看回放位置 | Tests only | Browser test: draws from its state |
| `SurveyLayer` | layers | 地图上看测绘区域 | Tests only | Browser test: draws from its state |
| `WaypointLayer` | layers | 地图上拖改航点 | SITL | CI by clicks on firmware: clicks land where aimed |
| `AirspacePanel` | map | 查看机场限飞区 | Tests only | Logic: units. Demo data |
| `Compass3DPanel` | map | 校准罗盘看磁场球 | SITL | CI by clicks on firmware: three compass offsets saved |
| `Map3DView` | map | 三维地图查看编辑 | Simulator | e2e: map3d |
| `Mission3DPanel` | map | 三维预览航线 | SITL | CI by clicks on firmware: waypoint count matches the FC |
| `OfflineMapPanel` | map | 下载离线地图瓦片 | Tests only | Browser test: opens without an error |
| `OrthoOverlayPanel` | map | 叠加正射图 | Tests only | Browser test: image reaches the map, survives a reload, wrong corners refused |
| `CorridorPanel` | mission | 生成走廊扫描航线 | SITL | CI by clicks on firmware: parallel lines on the FC |
| `RallyPanel` | mission | 添加并上传备降点 | SITL | CI by clicks on firmware: points on the FC, clear works |
| `FencePanel` | mission | 绘制上传地理围栏 | Real FC | 2026-11-05, Clear on FC through the panel on WebSerial |
| `MissionPanel` | mission | 编辑上传任务航点 | SITL | CI by clicks on firmware: upload and download match the FC store. 2026-11-13: contract tests of the download's seq map and of the per-waypoint commands it carries back into the upload |
| `MissionProgress` | mission | 看任务执行进度 | SITL | CI by clicks on firmware: tracks the FC mission sequence |
| `PoiPanel` | mission | 设置相机兴趣点 | SITL | CI by clicks on firmware: the vehicle turns, clear reaches the FC |
| `SurveyPanel` | mission | 生成测绘网格航线 | SITL | CI by clicks on firmware: spacing and heading on the FC, and the grid flown |
| `TerrainProfilePanel` | mission | 查看航线地形剖面 | SITL | CI by clicks on firmware: clearance from home. Skips without the terrain server |
| `AutoTunePanel` | params | 启动自动调参 | SITL | CI by clicks on firmware, on the ground only: refusal, axes written. Not run in the air |
| `FailsafeConfigPanel` | params | 配置失控保护 | SITL | CI by clicks on firmware: every section written and read back |
| `FlightModePanel` | params | 配置六档飞行模式 | SITL | CI by clicks on firmware: six slots read, FLTMODE written |
| `ParamDiffPanel` | params | 对比参数文件差异 | SITL | CI by clicks on firmware: export, compare, apply |
| `ParamPanel` | params | 读取编辑飞控参数 | Real FC | 2026-11-06 on both links on Windows: 1028 parameters in about 4 s. Writes 2026-11-05 used the same dispatch, not the row editor. Unit tests 2026-11-13: a decimal comma ("1,5") reads as 1.5 in the edit box and in an imported file, and a CSV header is skipped |
| `PidPanel` | params | 调节PID参数 | SITL | CI by clicks on firmware: typed and slider gains reach the FC |
| `PowerCalPanel` | params | 校准电压电流 | SITL | CI by clicks on firmware: voltage and current scale on the FC |
| `AiAnnotationPanel` | planning | 标注图像缺陷 | None | No test. Auto-detect is a stub. No way to open it |
| `AiPlannerPanel` | planning | 文字生成航线 | None | No test. Rule-based parser, not an LLM. No way to open it |
| `AnnotationPanel` | planning | 记录地图标注点 | Tests only | Browser test: opens, refuses an entry without a position, and leaves out one that was stored without it |
| `CustomDashboard` | planning | 自定义仪表 | SITL | WebSerial CI, live values |
| `OverlapCalcPanel` | planning | 计算相机重叠率 | Tests only | Browser test: opens without an error |
| `SchedulerPanel` | planning | 定时执行任务 | Tests only | Logic: scheduler. No way to open it |
| `ScriptPanel` | planning | 运行用户脚本 | Tests only | Logic: ws. No way to open it |
| `CalibrationPanel` | setup | 校准传感器 | Real FC | 2026-11-06 on both links: compass start and cancel only, no whole run. e2e: connected-flow |
| `EscCalPanel` | setup | 校准电调 | SITL | CI by clicks on firmware: parameter and undo. The calibration itself needs a power cycle |
| `FirmwarePanel` | setup | 上传固件并重启 | Simulator | e2e: settings, mobile |
| `FrameSelectPanel` | setup | 选择机架类型 | SITL | CI by clicks on firmware: class and type written, layouts match the firmware |
| `MotorTestPanel` | setup | 逐个测试电机 | SITL | CI by clicks on firmware: outputs per motor, stop in real time. Props never involved |
| `NtripPanel` | setup | 接入RTK | Simulator | e2e: command-palette. Opens; no real base station |
| `PositionSourcePanel` | setup | 查看定位源 | SITL | WebSerial CI, GPS and EKF rows |
| `RcCalibPanel` | setup | 校准遥控器行程 | SITL | CI by clicks on firmware: four channels, ends kept |
| `SetupWizard` | setup | 按向导完成初始设置 | SITL | CI by clicks on firmware: six steps, tools reach the FC |
| `AssistantDialog` | shared | 批准或拒绝 AI 助手的请求 | SITL | e2e: assistant: a mission and a parameter approved against the built-in simulator, a decline, a withdrawal. panels-sitl: hold, RTL and land approved and slid on ArduCopter SITL in flight, a slide let go sends nothing, a declined land changes nothing |
| `CommandPalette` | shared | 搜索并执行命令 | Simulator | e2e: command-palette, keyboard |
| `ConfirmDialog` | shared | 确认危险操作 | Real FC | 2026-11-05 |
| `FlightSummary` | shared | 查看飞行总结 | SITL | CI by clicks on firmware: matches the flight the FC reported |
| `LoginDialog` | shared | 输入令牌登录 | Simulator | e2e: auth |
| `PreflightPanel` | shared | 查看起飞前检查 | Real FC | 2026-11-05 on both links |
| `RolePanel` | shared | 切换操作角色 | Tests only | Browser test: opens without an error. Demo, not wired to roles |
| `SettingsPanel` | shared | 修改应用设置 | Simulator | e2e: settings, mobile. 2026-11-13: the footer shows the version `package.json` has, and the test reads that file |
| `SlideConfirm` | shared | 滑动确认关键指令 | SITL | CI by clicks on firmware: an early release arms nothing |
| `EkfPanel` | telemetry | 查看导航滤波状态 | Simulator | e2e: connected-flow, navigation |
| `RcPanel` | telemetry | 查看遥控通道 | Simulator | e2e: connected-flow, navigation |
| `ServoPanel` | telemetry | 查看舵机输出 | Simulator | e2e: connected-flow, navigation |
| `TelemetryOverlay` | telemetry | 飞行中看关键遥测 | Real FC | 2026-11-06 on both links on Windows. Above ground was showing the height of the ground, found and fixed that day |
| `VibrationPanel` | telemetry | 查看振动水平 | Simulator | e2e: connected-flow, navigation |
| `AdvancedCmdPanel` | tools | 给航点加高级指令 | SITL | CI by clicks on firmware: items land on the FC |
| `ConsolePanel` | tools | 发送飞控控制台命令 | Simulator | e2e: memory |
| `FFTPanel` | tools | 分析日志频谱 | SITL | CI on a real .BIN: finds an injected 35 Hz tone |
| `FlightReportPanel` | tools | 填写导出飞行报告 | SITL | CI by clicks on firmware: keeps the flight after the summary closes |
| `InspectorPanel` | tools | 检视实时消息流 | Simulator | e2e: memory |
| `LogPanel` | tools | 下载机载日志 | Real FC | 2026-11-06 on both links on Windows |
| `LogViewerPanel` | tools | 绘图查看日志 | SITL | CI on a real .BIN, compared with pymavlink |
| `RemotePanel` | tools | 查看会话复制链接 | SITL | CI: client count from the backend |
| `ReplayPanel` | tools | 加载并回放飞行日志 | Simulator | e2e: map3d, a file with rows that are not numbers included |
| `FleetDashboard` | vehicle | 查看并切换多机 | Tests only | Logic: ws |
| `GimbalPanel` | vehicle | 控制云台相机 | Simulator | e2e: command-palette. Opens; no gimbal |
| `VideoOverlay` | vehicle | 观看视频流 | Simulator | e2e: memory. No real camera |

## Platform / 平台与功能

| Feature | 功能 | Level | Evidence |
| --- | --- | --- | --- |
| Serial through the backend | 后端串口 | Real FC | 2026-11-06 on Windows, COM port, on the Python 3.10 the package bundled then; 2026-11-05 on Linux through usbipd. On the Python 3.14 it bundles since v3.7.8: a COM port opened and closed 2026-11-10, no FC on it |
| WebSerial | 浏览器直连 USB | Real FC | 2026-11-06, real Edge on Windows, the port chooser used with the mouse. 2026-11-05, Chromium on Linux through usbipd |
| Log download speed | 日志下载速度 | Real FC | 2026-11-06 on Windows, about 660 KB/s on both links. 2026-11-05 through usbipd, about 700 KB/s |
| Reconnect after a lost link | 断链重连 | Real FC | 2026-11-06, FC reboot on Windows on both links. 2026-11-05, USB pulled on both links. CI: WebSerial keeps the flight through a drop in the air, on SITL |
| PFD and HUD | PFD 和 HUD | Real FC | 2026-11-05 on both links; west heading and RC not checked |
| Preflight checks | 起飞前检查 | Real FC | 2026-11-05 on both links |
| Copter | 多旋翼 | Real FC | Bench 2026-11-05, flight modes in SITL |
| Linux from source | Linux 源码运行 | Real FC | Daily development |
| TCP | TCP 连接 | SITL | CI |
| Plane and VTOL | 固定翼和 VTOL | SITL | CI: a plain plane and a QuadPlane fly a whole mission on SITL, the QuadPlane with VTOL takeoff, transition and VTOL landing. Real telemetry 2026-05 |
| Rover | 地面车 | SITL | CI: drives a whole mission and comes back on SITL |
| Sub | 水下机器人 | SITL | CI: dives, runs a whole mission and surfaces on SITL |
| 2D map | 2D 地图 | Simulator | e2e, and real Edge on Windows 2026-11-06. Every source answered with a real tile 2026-11-06, except Tianditu, which needs a key of your own. e2e 2026-11-11: the credit of the map server shows clear of the events bar, and the street layer of a source without a label layer shows (it was blank through v3.7.9). 2026-11-11 with a map server that cannot be reached, behind a proxy that answers 502 after 5 s: a panel opens 11 s after the first page shows its map and in under a second on later visits, where v3.7.11 took 31 s every time. e2e 2026-11-13: a click in the fly view adds no waypoint, and the same click in the plan view does; guided clicks are the fly view's |
| 3D map | 3D 地图 | Simulator | e2e, and real Edge on Windows with a real GPU 2026-11-06. e2e 2026-11-11: the credit of the map and terrain servers shows unfolded |
| PWA and offline use | PWA 和离线 | Simulator | e2e, and real Edge on Windows 2026-11-06 |
| Several browser clients | 多浏览器客户端 | Simulator | Integration tests |
| A phone or tablet on the network | 局域网里的手机或平板 | Simulator | A phone-sized touch browser on a network address 2026-11-11: token login, live telemetry and a parameter read upright, a mode change on its side. e2e: a page the backend does not list is told so at the login; upright, RTL asks for the slide, hold sends the mode command, the flight controls open and close, and nothing lies over the events bar. No real phone |
| AI assistant (MCP) | AI 助手（MCP） | SITL | Unit tests of the MCP server in both protocol eras, and through the real backend over its websocket. e2e: an MCP client starts the server, the page answers it, and an operator approves a mission and a parameter against the built-in simulator, declines one, and one is withdrawn. panels-sitl: the flight commands on ArduCopter SITL, refused on the ground, then hold, RTL and land in flight, each approved and slid, read back from the firmware's heartbeat. No AI client tried by hand, no real FC |
| Video and AR overlay | 视频和 AR 叠加 | Simulator | Integration tests, and real ffmpeg on an HTTP test stream 2026-11-10. No real camera |
| Token login | Token 登录 | Simulator | e2e, real Windows each release |
| Windows package | Windows 发布包 | Simulator | CI builds and smoke-tests it on every push. The release workflow starts the zip it is about to publish on a Windows runner, and publishes nothing if that fails. Real Windows each release |
| Windows installer | Windows 安装程序 | Simulator | CI builds it from the zip on every push and, on a Windows runner, installs it for the user, runs the package checks on the installed copy against the built-in simulator, uninstalls it, and checks that the program, its caches, token, shortcuts and uninstall entry are gone and the logs and map files kept. The release workflow does the same with the installer it publishes. Since 2026-11-13 the folder can be chosen: an empty one, or an earlier Argus one, which PrepareToInstall checks for. The directory page is GUI and no CI run opens it: it needs a look on real Windows. Not yet on a real Windows machine |
| UDP | UDP 连接 | SITL | CI: a whole session on real firmware |
| Telemetry radio | 数传电台 | SITL | CI through a stand-in: 57600 baud, 3% of frames lost, 1.5% corrupted, a whole session. 2026-11-11 at 38400 baud and 5% lost: all 1369 parameters in 68 s, where v3.7.8 stopped at 1349. No real radio |
| Linux tty | Linux tty | SITL | CI: a whole session through a pty on real firmware, which reads differently from a socket |
| Long sessions | 长时间运行 | SITL | 2026-11-06: 60 minutes at 5x, 189 flights, 900,000 frames: browser heap flat at 7 MB, backend memory not growing. tests/e2e/run-soak.sh, not in CI |
| Several vehicles at once | 多机同屏 | SITL | CI: two vehicles on one link, each flown from the other through the switch |
| Offline mbtiles maps | 离线 mbtiles 地图 | Simulator | e2e: a real file picked in Settings shows on the map |
| Survey and pattern planning | 测绘和图案规划 | SITL | CI: drawn in the panel, read back from the firmware, and the grid flown |
| Mission file formats | 航线文件格式 | Simulator | e2e: .waypoints, .plan and .kml as other ground stations write them. e2e 2026-11-11: a file, or a route kept in the browser, with markup or text where a number belongs is refused whole, and a KML overlay shows the name of a shape as text |
| Content policy of the page | 页面内容安全策略 | Simulator | e2e 2026-11-11: markup put into the page runs no script, and the four tabs and the 3D view stay inside the policy. Real Windows each release |
| Terrain profile | 地形剖面 | SITL | CI: clearance from home on real firmware, heights from the real terrain server |
| Voice and audio alerts | 语音和声音告警 | SITL | CI: the armed message on real firmware, with speech stubbed. Sound itself not checked |
| Gamepad | 手柄 | SITL | CI: a stubbed pad moves channel 1 on real firmware. No real pad. Since 2026-11-13 the status bar names the gamepad while it overrides; the badge itself has no test |
| 10 languages | 10 种语言 | Tests only | Key completeness only, not reviewed by native speakers |
| Plugins and scripts | 插件和脚本 | Tests only | Unit tests |
| RTK through NTRIP | NTRIP RTK | Tests only | No real base station |
| Cross-site request blocking | 跨站请求拦截 | Tests only | Unit tests, real Windows each release |
| No network without a token | 无 Token 不监听外网 | Tests only | Unit tests on both entry points, real Windows each release |
| DNS rebinding blocking | DNS 重绑定拦截 | Tests only | Unit tests, real Windows each release |
| SSRF and path traversal protection | SSRF 和路径穿越防护 | Tests only | Unit tests |
| STATUSTEXT filter | STATUSTEXT 过滤 | Tests only | Unit tests |
| Telemetry that is no number | 非数值遥测（NaN） | Tests only | Unit tests on both links. 2026-11-10, a real browser and a stand-in vehicle sending NaN and infinities: v3.7.7 showed no vehicle and logged 117 parse errors in 23 s, this version showed NaN and kept updating |
| Real flight | 真实飞行 | None | Never properly flown |
| Right-to-left layout | 阿拉伯语从右到左布局 | Tests only | Browser test: page turns around and stays inside the window |
| macOS | macOS | Simulator | CI: unit and contract tests, then the app in a browser on macos-latest. No SITL there |
| Desktop app (Tauri) | 桌面版（Tauri） | None | Not built |
| Firmware flashing | 固件刷写 | n/a | Not implemented |
| PX4 | PX4 | n/a | Refused on connect, not implemented |
| White-label branding | 白标定制 | n/a | Code exists but is not wired in |

## Not verified yet, by risk / 未验证项（按风险排序）

1. **Real flight.** Nothing has flown. Everything below is a bench or simulation result at best.
2. **Arm, take off, RTL and mission start on a real FC.** These have only run in SITL. They need a battery, so they need a separate, deliberate session.
3. **A whole calibration on a real FC.** Compass start and cancel ran on both links 2026-11-06. A whole run needs the board turned by hand.
4. **RTK, gimbal, camera and ADS-B.** These need hardware that has not been available.
5. **Vehicles other than Copter on real hardware.** Plane, QuadPlane, Rover and Sub run whole missions in SITL in CI through the backend. None has been on a real board since the 2026-05 telemetry check.
6. **Chrome itself on Windows.** Edge on Windows ran through the real port chooser 2026-11-06. Chrome was not on that machine.
7. **Four panels nobody can open.** Scripts, scheduler, AI planner and AI annotation exist in code only.
8. **The backend's serial link on Windows since the package bundles Python 3.14 (v3.7.8).** It ran on a real FC on the Python 3.10 of earlier packages. On 3.14 a COM port was opened and closed 2026-11-10, with no FC on it. WebSerial does not use that Python.
9. **Video from a real camera.** ffmpeg turned an HTTP test stream into frames 2026-11-10. No RTSP camera has been on it, and before v3.7.8 only `rtsp://` addresses could play at all.
10. **A real phone or tablet.** A phone-sized touch browser opened Argus at a network address 2026-11-11. No real phone has, and neither Safari on iOS nor the browser inside a chat app has been tried.
11. **The AI assistant with a real AI client and a real FC.** Its tests use a plain MCP client, the built-in simulator and ArduCopter SITL. Neither Claude Desktop nor Claude Code has driven it yet, and no proposal has reached a real flight controller.

1. **真实飞行。** 没有飞过。下面都只是台架或仿真结果。
2. **真机上的解锁、起飞、返航、开始任务。** 只在 SITL 跑过。这些需要接电池，要单独安排。
3. **真机上的完整校准。** 2026-11-06 两条链路都跑过罗盘的启动和取消，完整校准需要手动翻转板子。
4. **RTK、云台、相机、ADS-B。** 缺硬件。
5. **多旋翼以外机型上真机。** 固定翼、QuadPlane、地面车、水下机器人在 CI 里经后端跑完整任务（SITL）。除 2026-05 的遥测检查外，都没有接过真实飞控。
6. **Windows 上的 Chrome 本身。** 2026-11-06 已用 Windows 上的 Edge 走真实端口弹窗，那台机器没有装 Chrome。
7. **4 个打不开的面板。** 脚本、定时任务、AI 规划、AI 标注只存在于代码中。
8. **发布包改用 Python 3.14（v3.7.8）之后，Windows 上的后端串口。** 之前的发布包内置 Python 3.10，在真实飞控上跑过。3.14 上只在 2026-11-10 打开并关闭过一个 COM 口，没有接飞控。WebSerial 不经过这个 Python。
9. **真实相机的视频。** 2026-11-10 用 ffmpeg 把一路 HTTP 测试流转成了画面。没有接过 RTSP 相机，而且 v3.7.8 之前只有 `rtsp://` 地址能播放。
10. **真实的手机或平板。** 2026-11-11 用手机尺寸的触屏浏览器在局域网地址上打开过 Argus。没有用过真实手机，iOS 上的 Safari 和聊天软件内置的浏览器也都没有试过。
11. **用真实的 AI 客户端和真实飞控运行 AI 助手。** 测试用的是一个最简单的 MCP 客户端、内置模拟器和 ArduCopter SITL。Claude Desktop 和 Claude Code 都还没有驱动过它，也没有提议到达过真实飞控。

## Known limits / 已知限制

- The mode list comes from tables in Argus, one per vehicle type. A firmware built without a mode still shows it, and refuses it when asked.
- A compass calibration is saved only by the session that started it. After Disconnect and Connect during a run, the result is reported as not saved, and the run has to be repeated.
- Roles are a courtesy between operators, not access control: everyone who holds the token can command the vehicle.
- Arming and fence terms in German, Arabic and Russian have not been checked by a native speaker.
- The AI assistant reads and proposes only. Its tools cannot arm, take off, start a mission or change to a mode other than return, hold and land. A mission or parameter change is refused while the vehicle is armed, and a flight command while it is not. An AI client that can also run commands on the computer, as Claude Code can, is not held to the tools.
- On a screen narrower than 768 px, such as a phone held upright, logs, calibration, the 2D/3D switch and video are not shown. While a vehicle is connected, RTL and hold sit above the tabs, and in the Fly view the button for the flight controls (arming, modes) too. Most phones turned on their side are wider than that and get the desktop layout.

- 模式列表来自 Argus 内置的表，每种机型一张。固件编译时去掉的模式仍会显示，选择时由飞控拒绝。
- 罗盘校准只能由发起它的那次会话保存。校准途中断开再连接，结果会报告为未保存，需要重新校准。
- 角色只是操作员之间的约定，不是访问控制：持有 Token 的人都能指挥飞行器。
- 德语、阿拉伯语和俄语里的解锁与围栏术语没有经过母语者校对。
- AI 助手只能读取和提议，它的工具不能解锁、起飞、开始任务，也不能切换到返航、悬停、降落以外的模式。飞行器解锁时拒绝航线和参数修改，未解锁时拒绝飞行指令。能在本机执行命令的 AI 客户端（例如 Claude Code）不受这些工具的限制。
- 屏幕宽度小于 768 px 时（例如竖着拿的手机），不显示日志、校准、2D/3D 切换和视频。连上飞行器后，返航和悬停按钮在底部标签的上方，飞行视图里还有飞行操控（解锁、切换模式）按钮。多数手机横过来宽于 768 px，会变成电脑版布局。

## Keeping this file honest / 维护规则

`tests/test_contract_verification_doc.py` fails when a command, message, route or panel is missing here, or when the counts in the summary stop matching the tables. Levels go up only with evidence: a date and how it was checked.

新增命令、消息、接口或面板而没写进本文件，或总数和表格对不上时，`tests/test_contract_verification_doc.py` 会失败。等级只有在有证据时才能提升，要写明日期和验证方式。

`docs/FEATURE_CHECKLIST.md` is a frozen v3.4 snapshot with 499 finer-grained items. This file is the current status.

`docs/FEATURE_CHECKLIST.md` 是冻结在 v3.4 的快照，有 499 条更细的条目。当前状态以本文件为准。
