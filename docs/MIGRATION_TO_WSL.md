# Argus 开发环境迁移：VMware → Windows + WSL2 + usbipd-win

迁移目标：解决 VMware USB passthrough 写入死锁，把 hardware-blocked 验证（WebSerial 直连、校准、firmware 上传）解封。

迁移决策见 [docs/audits/sitl_validation_2026-05-24.md](audits/sitl_validation_2026-05-24.md)。

## 总览

```
[Windows 主机]                    [WSL2 Ubuntu]
                                  ├── ~/argus  (代码)
[PLKJ USB FC] ─usbipd→ /dev/ttyACM0
                                  ├── ~/ardupilot (PLKJ fork)
[Chrome] ──→ http://localhost:8100
                                  └── ~/.claude (memory)
```

预估耗时：**首次半天**（含 SITL build），日常用 = 立即生效。

---

## Phase 1 — Windows 主机准备（管理员 PowerShell）

```powershell
# 1. 装 WSL2 + Ubuntu (会自动重启)
wsl --install -d Ubuntu

# 重启后会弹 Ubuntu 终端，设用户名（建议 plkj）+ 密码

# 2. 装 usbipd-win
winget install --interactive --exact dorssel.usbipd-win
# 或: https://github.com/dorssel/usbipd-win/releases 装最新 MSI

# 3. 验证 WSL 跑起来 + USB-IP 内核模块
wsl --list --verbose
# 应该看到 Ubuntu 是 VERSION 2 (不是 1)
```

---

## Phase 2 — WSL 内一次性 bootstrap

进入 Ubuntu 终端，先把代理设好（不然 apt/git/npm 会卡）：

```bash
# 测一下能不能到 Windows 主机的代理
curl -x http://192.168.100.1:7897 -sI https://www.google.com | head -1

# 持久化代理（写进 ~/.bashrc）
cat >> ~/.bashrc <<'EOF'
alias proxy='export http_proxy=http://192.168.100.1:7897; export https_proxy=http://192.168.100.1:7897; export HTTPS_PROXY=$https_proxy; export HTTP_PROXY=$http_proxy'
alias unproxy='unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY'
EOF
source ~/.bashrc
proxy
```

跑 bootstrap 脚本（同步会写到 `scripts/wsl_bootstrap.sh`，但 clone 之前你拿不到，先用下面 inline 版本）：

```bash
# 系统包
sudo apt update && sudo apt install -y \
  git curl build-essential python3.10 python3.10-venv python3-pip \
  python3-dev libssl-dev libffi-dev pkg-config \
  ccache

# Node 20 LTS（NodeSource 源）
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# 检查
python3 --version  # → 3.10.x
node --version     # → v20.x
npm --version      # → 10.x

# SSH key — 从 VMware 拷过来（你手动一次，不让脚本碰）
# 方法 A: 在 VMware 里 cat ~/.ssh/id_ed25519 → 复制到 WSL ~/.ssh/id_ed25519 → chmod 600
# 方法 B: 在 WSL 重新 ssh-keygen -t ed25519 -C 1476907630@qq.com 然后把 .pub 加到 github
mkdir -p ~/.ssh && chmod 700 ~/.ssh
# (粘贴你的私钥)
nano ~/.ssh/id_ed25519
chmod 600 ~/.ssh/id_ed25519
ssh -T git@github.com  # 应该看到 "Hi L-X-Yao!"

# git 全局配置
git config --global user.name "L-X-Yao"
git config --global user.email "1476907630@qq.com"

# Clone 项目
cd ~
git clone git@github.com:L-X-Yao/argus.git
cd ~/argus

# Python venv（隔离 argus 依赖，避免污染系统）
python3 -m venv ~/argus-venv
source ~/argus-venv/bin/activate
echo 'source ~/argus-venv/bin/activate' >> ~/.bashrc
pip install -e ".[dev]"

# 前端
npm install

# Smoke test — 跑一次完整测试门
ruff check backend/ scripts/ tests/
python -m pytest tests/test_unit_*.py tests/test_contract_*.py -q
npx vitest run
npx svelte-check --tsconfig ./tsconfig.json
```

全绿之后再处理 ArduPilot SITL（独立 50GB 工程，按需）：

```bash
cd ~
git clone --recursive git@github.com:penglikeji/ardupilot.git
cd ~/ardupilot
git checkout 179e491c8e  # 跟 VMware 环境对齐；或 git pull 取最新 PLKJ-master

# 装 ArduPilot 编译依赖
Tools/environment_install/install-prereqs-ubuntu.sh -y
. ~/.profile

# 编译 SITL Copter (~10-20 分钟 first build, ccache 后秒级)
./waf configure --board sitl
./waf copter

ls build/sitl/bin/arducopter  # 验证产物
```

---

## Phase 3 — Claude Code memory 迁移

VMware 里这个会话产出的 memory 在 `/home/plkj/.claude/projects/-home-plkj-samba-filght-argus/memory/`。WSL 里项目路径变了（`-home-<wsl-user>-argus`），memory 不会自动跟过来。

```bash
# 在 WSL 内（假设 WSL 用户名 plkj）
mkdir -p ~/.claude/projects/-home-plkj-argus/memory

# 从 VMware 拷过来 — 任选一种：
# A. 通过 \\wsl$\Ubuntu UNC 路径在 Windows 里拖（最简单）
# B. 走 sftp / scp 从 VMware 拉
# C. 在 VMware 里把 memory 目录 tar 起来放 samba share，再到 WSL 解出来
```

如果嫌麻烦也可以全新开始 — memory 只是辅助，下次会话 Claude 会重新积累。但 `feedback_*` 那几条偏好/纪律值得保留。

---

## Phase 4 — USB 验证（关键里程碑）

这是迁移的全部意义所在。

### Windows 主机（管理员 PowerShell）

```powershell
# 列出所有 USB 设备
usbipd list

# 找到 PLKJ FC（应该是 BUSID xxx, VID:PID 1209:5740 "Generic Plkj-Industrial"）

# 第一次绑定（持久化共享给 WSL）
usbipd bind --busid=<BUSID>

# 附给 WSL
usbipd attach --wsl --busid=<BUSID>

# 之后每次插拔后只需要 attach（bind 是一次性的）
```

### WSL 内

```bash
# 看 USB 设备
lsusb  # 应该有 "Bus 00x Device 00x: ID 1209:5740 Generic Plkj-Industrial"

# 看串口
ls -la /dev/ttyACM*  # 应该有 ttyACM0 (+ ttyACM1)

# 权限：把自己加进 dialout
sudo usermod -aG dialout $USER
# 注销 WSL 重进生效：在 PowerShell 里 wsl --shutdown 然后重新打开

# 跑 A.0 baseline（VMware 里这步会 kernel 死锁，WSL 应该正常）
cd ~/argus
python3 - <<'PY'
import sys; sys.path.insert(0, '.')
import time
from backend.drone_link import DroneLink
link = DroneLink()
ok = link.connect('/dev/ttyACM0', baudrate=115200, protocol='auto')
print(f"connect={ok}")
time.sleep(3)
st = link.get_state()
print(f"frames={st['frames']} autopilot={st['autopilot']} mode={st['mode']}")
link.disconnect()
PY
```

**期望输出**：`connect=True frames>30 autopilot=1 mode=...`。如果 `frames=0` — 同样的死锁症状，那就是 usbipd 也搞不定，要考虑 dual-boot 方案（极少见但可能）。

---

## Phase 5 — 完成验证

USB 通了之后立刻把之前 hardware-blocked 的清单跑掉：

```bash
# 在 WSL 内
cd ~/argus

# A.1: WebSerial 直连 — Windows Chrome 打开 http://localhost:8100，点 USB 按钮
python run.py  # 然后浏览器操作

# A.2: 校准全套 — 在 UI 里依次跑 compass / gyro / level / baro / accel
# (这步是手动操作 + 真传感器扭动)

# Firmware 上传 — 只在你打算给自家 PLKJ FC 烧自家固件时跑，不要拿 ArduPilot APJ 测
```

跑完更新 `docs/audits/sitl_validation_2026-05-24.md` 把 A.1/A.2 状态从 ⚠️ 改成 ✅。

---

## Phase 6 — VMware 退役

**不要立刻删 VM** — 保留至少一周作为 fallback。

```
✓ WSL 跑通 npm install + pytest + vitest + svelte-check + ruff 全绿
✓ WSL 跑通 USB telemetry 不死锁
✓ WSL 跑通 SITL ArduCopter
✓ 一周日常开发无回退
   ↓
关闭 VMware VM（保留磁盘镜像）
   ↓
一个月稳定后才删
```

---

## 回退预案

迁过去如果 WSL 出意外问题（usbipd 不稳、性能不及预期、其他兼容性），原 VMware VM 还在，直接切回继续 SITL 工作。代码已经全部 push 到 GitHub，两边随时 sync。

最坏情况：USB 在 WSL 也死锁 → 这时基本可以确认是 PLKJ FC 的 USB CDC 栈对某些 host write 不健壮（不是 hypervisor 问题），要在 FC 固件侧排查 USB 中断处理。

---

## 关键提醒

- ⚠️ **代码不要放 `/mnt/c/...`** — NTFS 跨边界访问慢 10 倍。一定放 WSL ext4（`~/argus`）。
- ⚠️ **ArduPilot 不要从 samba 拷过来** — 50GB 大部分是 build artifacts，重新 clone 1-2GB + 重编 SITL 才是干净的。
- ⚠️ **proxy 别忘** — npm / pip / git clone 默认不走 FlClash TUN，需要手动 `proxy` 别名（除非你把 FlClash 配成 TUN 模式接管 WSL 流量）。
- ⚠️ **usbipd `bind` 一次性，`attach` 每次重启都要重做** — 写个 PowerShell 启动脚本省事。
