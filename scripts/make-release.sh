#!/bin/bash
# One-click release: bump version -> commit -> tag -> push.
# GitHub Actions release workflow handles build + publish automatically.
#
# Usage: bash scripts/make-release.sh 3.6.0
set -e

NEW_VER="$1"
if [ -z "$NEW_VER" ]; then
    echo "Usage: bash scripts/make-release.sh <version>"
    echo "Example: bash scripts/make-release.sh 3.6.0"
    exit 1
fi

cd "$(dirname "$0")/.."

# Preflight checks
if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: working tree not clean. Commit or stash first."
    exit 1
fi

BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
    echo "ERROR: releases must be from main (currently on $BRANCH)"
    exit 1
fi

# Bump version across all files
bash scripts/bump_version.sh "$NEW_VER"

# Commit version bump if files changed, otherwise tag current commit
if [ -n "$(git status --porcelain)" ]; then
    git add backend/config.py pyproject.toml package.json public/sw.js \
           src-tauri/Cargo.toml src-tauri/tauri.conf.json
    git commit -m "release: v$NEW_VER"
fi

if git rev-parse "v$NEW_VER" >/dev/null 2>&1; then
    echo "ERROR: tag v$NEW_VER already exists"
    exit 1
fi
git tag -a "v$NEW_VER" -m "Release v$NEW_VER"

# Push commit + tag
git push origin main --tags

echo ""
echo "Released v$NEW_VER"
echo "GitHub Actions will build artifacts and create the Release."
echo "Watch: https://github.com/L-X-Yao/argus/actions"
