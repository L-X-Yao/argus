#!/usr/bin/env bash
# Argus WSL2 一键 bootstrap — 从干净 Ubuntu 22.04/24.04 起步
# 详细说明见 docs/MIGRATION_TO_WSL.md
#
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/L-X-Yao/argus/main/scripts/wsl_bootstrap.sh | bash
#   # 或 clone 之后:
#   bash scripts/wsl_bootstrap.sh
#
# 这个脚本只装 Argus 自身环境 + 跑测试门。ArduPilot SITL 和 USB 设置请按
# 文档手动操作（涉及独立 50GB clone 和管理员权限）。

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[bootstrap]${NC} $*"; }
warn() { echo -e "${YELLOW}[bootstrap]${NC} $*"; }
die()  { echo -e "${RED}[bootstrap]${NC} $*" >&2; exit 1; }

# === Preflight ===
[[ "$(uname -s)" == "Linux" ]] || die "只能在 Linux/WSL 里跑"

if ! grep -qi "microsoft" /proc/version 2>/dev/null; then
    warn "看起来不是 WSL — 继续不影响，但 USB 部分需要 usbipd-win"
fi

log "== 阶段 1: 系统包 =="
sudo apt update
sudo apt install -y \
    git curl build-essential ccache \
    python3 python3-venv python3-pip python3-dev \
    libssl-dev libffi-dev pkg-config

# Node 20 LTS via NodeSource
if ! command -v node >/dev/null || [[ "$(node --version | cut -d. -f1)" != "v20" ]]; then
    log "== 阶段 2: Node 20 (NodeSource) =="
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
else
    log "Node 已经是 $(node --version)，跳过"
fi

log "== 验证版本 =="
python3 --version
node --version
npm --version

# === SSH key check ===
if [[ ! -f ~/.ssh/id_ed25519 ]]; then
    warn "没找到 ~/.ssh/id_ed25519 — 后续 git clone 会用 https"
    warn "如果要用 SSH: 把 VMware 里的 ~/.ssh/id_ed25519 + .pub 拷过来，chmod 600"
fi

# === git user ===
if ! git config --global user.email >/dev/null; then
    log "== git 全局用户配置 =="
    git config --global user.name "L-X-Yao"
    git config --global user.email "1476907630@qq.com"
fi

# === 项目目录 ===
ARGUS_DIR="${ARGUS_DIR:-$HOME/argus}"
if [[ -d "$ARGUS_DIR/.git" ]]; then
    log "已存在 $ARGUS_DIR，跳过 clone"
    cd "$ARGUS_DIR"
else
    log "== 克隆 Argus 到 $ARGUS_DIR =="
    if [[ -f ~/.ssh/id_ed25519 ]]; then
        git clone git@github.com:L-X-Yao/argus.git "$ARGUS_DIR"
    else
        git clone https://github.com/L-X-Yao/argus.git "$ARGUS_DIR"
    fi
    cd "$ARGUS_DIR"
fi

# === Python venv ===
VENV_DIR="${VENV_DIR:-$HOME/argus-venv}"
if [[ ! -d "$VENV_DIR" ]]; then
    log "== 创建 Python venv =="
    python3 -m venv "$VENV_DIR"
fi
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

log "== 安装 Argus pip 依赖 (含 dev) =="
pip install --upgrade pip
pip install -e ".[dev]"

# === Frontend ===
log "== npm install =="
npm install

# === Test gate ===
log "== 跑测试门 (这步可能 30s-2min) =="
echo "--- ruff ---"
ruff check backend/ scripts/ tests/
echo "--- pytest unit + contract ---"
python -m pytest tests/test_unit_*.py tests/test_contract_*.py -q --no-header
echo "--- vitest ---"
npx vitest run
echo "--- svelte-check ---"
npx svelte-check --tsconfig ./tsconfig.json

log "=== 全部通过！==="
log ""
log "下一步："
log "  1. ArduPilot SITL — 见 docs/MIGRATION_TO_WSL.md Phase 2 后半"
log "  2. usbipd-win + PLKJ FC — 见 docs/MIGRATION_TO_WSL.md Phase 4"
log "  3. 把 venv 激活写进 ~/.bashrc:  echo 'source $VENV_DIR/bin/activate' >> ~/.bashrc"
log ""
log "项目根目录: $ARGUS_DIR"
log "Python venv:  $VENV_DIR"
