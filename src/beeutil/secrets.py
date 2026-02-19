"""
Plugin secrets: simple KV store backed by os.environ.

Two loading paths, same outcome:
  - Local dev:  .env file pushed to device via devtools.py
  - Production: encrypted blob fetched from ODC API, decrypted on device

Usage:
  value = beeutil.secrets.get('my-plugin', 'AWS_BUCKET')

All KV pairs are loaded atomically on first access, then served from cache.
"""

import base64
import json
import logging
import os
import requests

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.backends import default_backend

SALT = b'hivemapper-plugin-secrets'
PBKDF2_ITERATIONS = 100000
KEY_LENGTH = 32
IV_LENGTH = 16
BLOCK_SIZE = 128

PLUGIN_DIR = '/data/plugins'
ODC_API_BASE = 'http://127.0.0.1:5000/api/1'

logger = logging.getLogger(__name__)


class SecretsError(Exception):
    pass

class DecryptionError(SecretsError):
    pass

class SecretsNetworkError(SecretsError):
    pass

class SecretsNotFoundError(SecretsError):
    pass

def _derive_key(plugin_id: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH,
        salt=SALT,
        iterations=PBKDF2_ITERATIONS,
        backend=default_backend()
    )
    return kdf.derive(plugin_id.encode('utf-8'))


def encrypt(plugin_id: str, env: dict) -> str:
    """Encrypt a dict of KV pairs. Used by deploy tooling."""
    key = _derive_key(plugin_id)
    iv = os.urandom(IV_LENGTH)
    plaintext = json.dumps(env).encode('utf-8')

    padder = padding.PKCS7(BLOCK_SIZE).padder()
    padded = padder.update(plaintext) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    blob = {
        'iv': base64.b64encode(iv).decode('ascii'),
        'ciphertext': base64.b64encode(ciphertext).decode('ascii'),
    }
    return base64.b64encode(json.dumps(blob).encode('utf-8')).decode('ascii')


def decrypt(plugin_id: str, encrypted_blob: str) -> dict:
    try:
        blob = json.loads(base64.b64decode(encrypted_blob).decode('utf-8'))
        iv = base64.b64decode(blob['iv'])
        ciphertext = base64.b64decode(blob['ciphertext'])
        key = _derive_key(plugin_id)

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()

        unpadder = padding.PKCS7(BLOCK_SIZE).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()

        return json.loads(plaintext.decode('utf-8'))
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise DecryptionError(f"Malformed encrypted blob: {e}")
    except Exception as e:
        raise DecryptionError(f"Decryption failed: {e}")


def _parse_dotenv(path: str) -> dict:
    env = {}
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            env[key] = value
    return env


def _dotenv_path(plugin_name: str) -> str:
    return os.path.join(PLUGIN_DIR, plugin_name, '.env')


def _fetch_from_odc(plugin_name: str) -> tuple:
    url = f'{ODC_API_BASE}/plugin/secrets/{plugin_name}'
    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException as e:
        raise SecretsNetworkError(f"Failed to reach ODC API: {e}")

    if response.status_code == 404:
        raise SecretsNotFoundError(f"Plugin '{plugin_name}' not found")
    if response.status_code != 200:
        raise SecretsNetworkError(f"ODC API error: {response.status_code}")

    data = response.json()
    plugin_id = data.get('_id')
    encrypted_blob = data.get('encrypted_secrets')

    if not plugin_id or not encrypted_blob:
        raise SecretsNotFoundError("ODC response missing _id or encrypted_secrets")

    return (plugin_id, encrypted_blob)


_cache = None


def _load(plugin_name: str) -> dict:
    global _cache

    if _cache is not None:
        return _cache

    env = None
    dotenv = _dotenv_path(plugin_name)
    if os.path.exists(dotenv):
        try:
            env = _parse_dotenv(dotenv)
        except Exception as e:
            logger.warning(f"Failed to parse {dotenv}: {e}")

    if not env:
        plugin_id, encrypted_blob = _fetch_from_odc(plugin_name)
        env = decrypt(plugin_id, encrypted_blob)

    for k, v in env.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise SecretsError(
                f"Env vars must be str: {type(k).__name__}={type(v).__name__} for '{k}'"
            )

    for k, v in env.items():
        os.environ[k] = v

    _cache = env
    return _cache


def clear_cache() -> None:
    global _cache
    _cache = None


def get(plugin_name: str, key: str) -> str:
    env = _load(plugin_name)
    if key not in env:
        raise KeyError(f"Key '{key}' not found in plugin '{plugin_name}' env")
    return env[key]


def load(plugin_name: str) -> dict:
    return dict(_load(plugin_name))

