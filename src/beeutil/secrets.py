"""
Plugin Secrets encryption and decryption module.

Provides AES-256-CBC encryption/decryption using plugin _id as key derivation input.
Implements singleton pattern for per-session secret caching.

Uses the `cryptography` library (version 2.8 available on devices).
"""

import base64
import json
import os
import requests

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.backends import default_backend

# Constants
SALT = b'hivemapper-plugin-secrets'
PBKDF2_ITERATIONS = 100000
KEY_LENGTH = 32  # 256 bits
IV_LENGTH = 16   # 128 bits for AES
BLOCK_SIZE = 128  # AES block size in bits

# Required keys in the secrets dictionary
REQUIRED_KEYS = ['aws_key', 'aws_secret', 'aws_bucket', 'aws_region']


# =============================================================================
# Custom Exceptions
# =============================================================================

class SecretsError(Exception):
    """Base exception for secrets module."""
    pass


class DecryptionError(SecretsError):
    """Raised when decryption fails."""
    pass


class SecretsValidationError(SecretsError):
    """Raised when secrets dictionary is missing required keys."""
    pass


class SecretsNetworkError(SecretsError):
    """Raised when API call fails due to network issues."""
    pass


class SecretsNotFoundError(SecretsError):
    """Raised when plugin is not found in API."""
    pass


# =============================================================================
# Key Derivation
# =============================================================================

def _derive_key(plugin_id: str) -> bytes:
    """
    Derive a 256-bit AES key from plugin_id using PBKDF2-HMAC-SHA256.
    
    Args:
        plugin_id: The plugin's MongoDB _id string
        
    Returns:
        32-byte key suitable for AES-256
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH,
        salt=SALT,
        iterations=PBKDF2_ITERATIONS,
        backend=default_backend()
    )
    return kdf.derive(plugin_id.encode('utf-8'))


# =============================================================================
# Encryption / Decryption
# =============================================================================

def encrypt_secrets(plugin_id: str, secrets: dict) -> str:
    """
    Encrypt a secrets dictionary using AES-256-CBC.
    
    Args:
        plugin_id: The plugin's MongoDB _id (used for key derivation)
        secrets: Dictionary containing AWS credentials
        
    Returns:
        Base64-encoded JSON string: {"iv": "<b64>", "ciphertext": "<b64>"}
    """
    # Derive key from plugin_id
    key = _derive_key(plugin_id)
    
    # Generate random IV
    iv = os.urandom(IV_LENGTH)
    
    # Serialize secrets to JSON bytes
    plaintext = json.dumps(secrets).encode('utf-8')
    
    # Apply PKCS7 padding
    padder = padding.PKCS7(BLOCK_SIZE).padder()
    padded_data = padder.update(plaintext) + padder.finalize()
    
    # Encrypt with AES-256-CBC
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    
    # Package as base64 JSON
    blob = {
        'iv': base64.b64encode(iv).decode('ascii'),
        'ciphertext': base64.b64encode(ciphertext).decode('ascii')
    }
    return base64.b64encode(json.dumps(blob).encode('utf-8')).decode('ascii')


def decrypt_secrets(plugin_id: str, encrypted_blob: str) -> dict:
    """
    Decrypt an encrypted blob using AES-256-CBC.
    
    Args:
        plugin_id: The plugin's MongoDB _id (used for key derivation)
        encrypted_blob: Base64-encoded JSON string from encrypt_secrets()
        
    Returns:
        Decrypted secrets dictionary
        
    Raises:
        DecryptionError: If decryption fails (wrong key, malformed blob, etc.)
    """
    try:
        # Decode outer base64 and parse JSON
        blob_json = base64.b64decode(encrypted_blob).decode('utf-8')
        blob = json.loads(blob_json)
        
        # Extract IV and ciphertext
        iv = base64.b64decode(blob['iv'])
        ciphertext = base64.b64decode(blob['ciphertext'])
        
        # Derive key from plugin_id
        key = _derive_key(plugin_id)
        
        # Decrypt with AES-256-CBC
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(ciphertext) + decryptor.finalize()
        
        # Remove PKCS7 padding
        unpadder = padding.PKCS7(BLOCK_SIZE).unpadder()
        plaintext = unpadder.update(padded_data) + unpadder.finalize()
        
        # Parse JSON
        return json.loads(plaintext.decode('utf-8'))
        
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise DecryptionError(f"Malformed encrypted blob: {e}")
    except Exception as e:
        raise DecryptionError(f"Decryption failed: {e}")


def validate_secrets(secrets: dict) -> None:
    """
    Validate that secrets dictionary contains all required AWS keys.
    
    Args:
        secrets: Dictionary to validate
        
    Raises:
        SecretsValidationError: If any required keys are missing
    """
    missing = [key for key in REQUIRED_KEYS if key not in secrets]
    if missing:
        raise SecretsValidationError(f"Missing required keys: {missing}")


# =============================================================================
# Singleton Cache
# =============================================================================

_secrets_cache = None


def clear_secrets_cache() -> None:
    """Clear the cached secrets, forcing re-fetch/decrypt on next access."""
    global _secrets_cache
    _secrets_cache = None


def get_secrets(plugin_id: str, encrypted_blob: str) -> dict:
    """
    Get decrypted secrets with singleton caching.
    
    First call decrypts and caches; subsequent calls return cached value.
    
    Args:
        plugin_id: The plugin's MongoDB _id
        encrypted_blob: Base64-encoded encrypted secrets
        
    Returns:
        Decrypted and validated secrets dictionary
    """
    global _secrets_cache
    
    if _secrets_cache is None:
        _secrets_cache = decrypt_secrets(plugin_id, encrypted_blob)
        validate_secrets(_secrets_cache)
    
    return _secrets_cache


# =============================================================================
# API Integration
# =============================================================================

def fetch_plugin_secrets(plugin_name: str, api_base: str = 'https://beemaps.com') -> tuple:
    """
    Fetch plugin _id and encrypted secrets from Hivemapper API.
    
    Args:
        plugin_name: The plugin's name
        api_base: Base URL for API (default: https://beemaps.com)
        
    Returns:
        Tuple of (plugin_id, encrypted_blob)
        
    Raises:
        SecretsNetworkError: If network request fails
        SecretsNotFoundError: If plugin is not found
    """
    url = f'{api_base}/api/plugins/{plugin_name}'
    
    try:
        response = requests.get(url, timeout=10)
    except requests.RequestException as e:
        raise SecretsNetworkError(f"Failed to fetch plugin secrets: {e}")
    
    if response.status_code == 404:
        raise SecretsNotFoundError(f"Plugin '{plugin_name}' not found")
    
    if response.status_code != 200:
        raise SecretsNetworkError(f"API error: {response.status_code}")
    
    data = response.json()
    
    plugin_id = data.get('_id')
    encrypted_blob = data.get('encrypted_secrets')
    
    if not plugin_id or not encrypted_blob:
        raise SecretsNotFoundError("Plugin response missing _id or encrypted_secrets")
    
    return (plugin_id, encrypted_blob)


def load_secrets(plugin_name: str, api_base: str = 'https://beemaps.com') -> dict:
    """
    Convenience function: fetch from API, decrypt, cache, and return secrets.
    
    First call fetches and decrypts; subsequent calls return cached value.
    
    Args:
        plugin_name: The plugin's name
        api_base: Base URL for API (default: https://beemaps.com)
        
    Returns:
        Decrypted and validated secrets dictionary
    """
    global _secrets_cache
    
    if _secrets_cache is not None:
        return _secrets_cache
    
    plugin_id, encrypted_blob = fetch_plugin_secrets(plugin_name, api_base)
    return get_secrets(plugin_id, encrypted_blob)
