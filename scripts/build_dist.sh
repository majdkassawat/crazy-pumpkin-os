#!/usr/bin/env bash
set -e
rm -rf dist/
python -m build
ls -la dist/
