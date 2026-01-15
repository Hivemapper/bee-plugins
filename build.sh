#!/usr/bin/env bash

ENTRY_POINT="${1:-plugin:main}"
PLUGIN_NAME="${2:-myplugin.py}"

python3 -m zipapp src -m $ENTRY_POINT -p "/usr/bin/python3" -o $PLUGIN_NAME
