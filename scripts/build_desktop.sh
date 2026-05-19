#!/bin/bash
# Build PL-Link GCS desktop application.
#
# Prerequisites:
#   - Node.js, npm (frontend build)
#   - Rust toolchain + cargo (Tauri build)
#   - Python 3 + PyInstaller (backend sidecar)
#
# On Windows, run this from Git Bash or WSL.
set -e
cd "$(dirname "$0")/.."

# Detect host target triple for sidecar naming
TARGET_TRIPLE=$(rustc -vV 2>/dev/null | grep '^host:' | cut -d' ' -f2)
if [ -z "$TARGET_TRIPLE" ]; then
    echo "ERROR: Rust toolchain not found. Install from https://rustup.rs/"
    exit 1
fi
echo "Target: $TARGET_TRIPLE"

# --- Step 1: Build Python backend into a single executable via PyInstaller ---
echo ""
echo "=== [1/3] Building Python backend sidecar ==="
mkdir -p src-tauri/binaries

# PyInstaller creates a single-file executable from backend_server.py.
# The --name must match the externalBin entry in tauri.conf.json (minus
# the target triple suffix that Tauri appends automatically).
python3 -m PyInstaller \
    --onefile \
    --name "python-backend-${TARGET_TRIPLE}" \
    --distpath src-tauri/binaries \
    --specpath build \
    --workpath build/pyinstaller \
    --clean \
    --noconfirm \
    --hidden-import backend \
    --hidden-import backend.app \
    --hidden-import backend.drone_link \
    --hidden-import backend.ws_manager \
    --hidden-import backend.commands \
    --hidden-import backend.mavlink_handlers \
    --hidden-import backend.mavlink_dispatch \
    --hidden-import backend.param_manager \
    --hidden-import backend.statustext_filter \
    --hidden-import backend.models \
    --hidden-import backend.constants \
    --hidden-import uvicorn \
    --hidden-import uvicorn.logging \
    --hidden-import uvicorn.loops \
    --hidden-import uvicorn.loops.auto \
    --hidden-import uvicorn.protocols \
    --hidden-import uvicorn.protocols.http \
    --hidden-import uvicorn.protocols.http.auto \
    --hidden-import uvicorn.protocols.websockets \
    --hidden-import uvicorn.protocols.websockets.auto \
    --hidden-import uvicorn.lifespan \
    --hidden-import uvicorn.lifespan.on \
    backend_server.py

echo "Sidecar built: src-tauri/binaries/python-backend-${TARGET_TRIPLE}"

# --- Step 2: Build frontend ---
echo ""
echo "=== [2/3] Building frontend ==="
node node_modules/vite/bin/vite.js build

# --- Step 3: Build Tauri desktop app ---
echo ""
echo "=== [3/3] Building Tauri desktop app ==="
cd src-tauri
cargo build --release

echo ""
echo "=== Build complete ==="
echo "Executable: src-tauri/target/release/pllink-gcs (or .exe on Windows)"
echo ""
echo "To build MSI/NSIS installers, run:"
echo "  cargo tauri build"
