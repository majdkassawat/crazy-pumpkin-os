#!/usr/bin/env bash
set -e
VERSION="$1"
if [ -z "$VERSION" ]; then echo "Usage: ./scripts/release.sh 0.2.0"; exit 1; fi
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "Error: VERSION must be valid semver (e.g. 1.2.3), got: $VERSION"
  exit 1
fi
sed -i "s/__version__ = \".*\"/__version__ = \"${VERSION}\"/" src/crazypumpkin/__init__.py
git add -A
git commit -m "Release v${VERSION}"
git tag "v${VERSION}"
echo "Tagged v${VERSION}. Push with: git push origin main --tags"
