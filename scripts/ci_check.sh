#!/usr/bin/env bash
set -e
python -m pytest tests/ -v --tb=short
