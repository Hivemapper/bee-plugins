#!/usr/bin/env bash

PLUGIN_NAME="${1:-myplugin.py}"
ENTRY_POINT="${2:-plugin:main}"

python3 -m zipapp src -m $ENTRY_POINT -p "/usr/bin/python3" -o $PLUGIN_NAME
