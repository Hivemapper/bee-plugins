#!/usr/bin/env python3
"""
Encrypt a .env file and upload the blob to the Hivemapper backend.

Usage:
    python3 util/upload_secrets.py \
        --plugin-name my-plugin \
        --plugin-secret <plugin-api-key> \
        --env-file .env

    # Custom backend URL (default: https://hivemapper.com)
    python3 util/upload_secrets.py \
        --plugin-name my-plugin \
        --plugin-secret <plugin-api-key> \
        --env-file .env \
        --base-url https://hivemapper.com
"""
import argparse
import json
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from beeutil.secrets import encrypt, _parse_dotenv

DEFAULT_BASE_URL = 'https://hivemapper.com'


def get_plugin_id(base_url: str, plugin_name: str, plugin_secret: str) -> str:
    url = f'{base_url}/api/plugins/{plugin_name}?secret={plugin_secret}'
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    plugin_id = data.get('_id') or str(data.get('id', ''))
    if not plugin_id:
        raise ValueError(f"Could not resolve _id for plugin '{plugin_name}' — response: {json.dumps(data)}")
    return plugin_id


def upload_encrypted_secrets(base_url: str, plugin_name: str, plugin_secret: str, encrypted_blob: str):
    url = f'{base_url}/api/plugins/{plugin_name}/secrets?secret={plugin_secret}'
    resp = requests.put(
        url,
        json={'encrypted_secrets': encrypted_blob},
        headers={'Content-Type': 'application/json'},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description='Encrypt and upload plugin secrets to Hivemapper backend.')
    parser.add_argument('--plugin-name', required=True, help='Plugin name as registered in Hivemapper')
    parser.add_argument('--plugin-secret', required=True, help='Plugin API key (the "secret" field in MongoDB)')
    parser.add_argument('--env-file', required=True, help='Path to .env file containing key=value pairs')
    parser.add_argument('--base-url', default=DEFAULT_BASE_URL, help=f'Hivemapper backend URL (default: {DEFAULT_BASE_URL})')
    parser.add_argument('--dry-run', action='store_true', help='Encrypt and print blob without uploading')
    args = parser.parse_args()

    if not os.path.exists(args.env_file):
        print(f'Error: {args.env_file} not found', file=sys.stderr)
        sys.exit(1)

    env = _parse_dotenv(args.env_file)
    if not env:
        print('Error: .env file is empty or has no valid key=value pairs', file=sys.stderr)
        sys.exit(1)

    print(f'Parsed {len(env)} key(s) from {args.env_file}: {", ".join(env.keys())}')

    print(f'Fetching plugin _id for "{args.plugin_name}"...')
    plugin_id = get_plugin_id(args.base_url, args.plugin_name, args.plugin_secret)
    print(f'Plugin _id: {plugin_id}')

    encrypted_blob = encrypt(plugin_id, env)
    print(f'Encrypted blob: {len(encrypted_blob)} chars')

    if args.dry_run:
        print(f'\n--- DRY RUN (not uploading) ---')
        print(encrypted_blob)
        return

    print(f'Uploading to {args.base_url}/api/plugins/{args.plugin_name}/secrets ...')
    result = upload_encrypted_secrets(args.base_url, args.plugin_name, args.plugin_secret, encrypted_blob)
    print(f'Done: {json.dumps(result)}')


if __name__ == '__main__':
    main()
