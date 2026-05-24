#!/bin/bash
# Bump version across all files that contain the version string.
# Usage: bash scripts/bump_version.sh 3.5.0
set -e

NEW_VER="$1"
if [ -z "$NEW_VER" ]; then
    echo "Usage: bash scripts/bump_version.sh <new_version>"
    echo "Example: bash scripts/bump_version.sh 3.5.0"
    exit 1
fi

if ! echo "$NEW_VER" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "ERROR: version must be semver (e.g. 3.5.0)"
    exit 1
fi

cd "$(dirname "$0")/.."

# Read current version from config.py (single source of truth)
OLD_VER=$(python3 -c "
import re
text = open('backend/config.py').read()
m = re.search(r\"VERSION = '([^']+)'\", text)
print(m.group(1) if m else '')
")

if [ -z "$OLD_VER" ]; then
    echo "ERROR: cannot read current version from backend/config.py"
    exit 1
fi

if [ "$OLD_VER" = "$NEW_VER" ]; then
    echo "Already at version $NEW_VER"
    exit 0
fi

echo "Bumping $OLD_VER → $NEW_VER"

# 1. backend/config.py (single source of truth)
sed -i "s/VERSION = '$OLD_VER'/VERSION = '$NEW_VER'/" backend/config.py

# 2. pyproject.toml
sed -i "s/^version = \"$OLD_VER\"/version = \"$NEW_VER\"/" pyproject.toml

# 3. package.json
sed -i "s/\"version\": \"$OLD_VER\"/\"version\": \"$NEW_VER\"/" package.json

# 4. public/sw.js cache name
OLD_CACHE=$(echo "$OLD_VER" | sed 's/\.[0-9]*$//')
NEW_CACHE=$(echo "$NEW_VER" | sed 's/\.[0-9]*$//')
if [ "$OLD_CACHE" != "$NEW_CACHE" ]; then
    sed -i "s/argus-gcs-v$OLD_CACHE/argus-gcs-v$NEW_CACHE/" public/sw.js
    echo "  sw.js cache: v$OLD_CACHE → v$NEW_CACHE"
fi

echo "Done. Files updated:"
echo "  backend/config.py"
echo "  pyproject.toml"
echo "  package.json"
grep -n "$NEW_VER" backend/config.py pyproject.toml package.json | sed 's/^/  /'
