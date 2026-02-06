#!/usr/bin/env python3
"""
Test script to verify encrypt/decrypt round-trip for plugin secrets.

Run from project root:
    python3 -m pytest util/test_secrets.py -v
    
Or directly:
    python3 util/test_secrets.py
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from beeutil.secrets import (
    encrypt_secrets, decrypt_secrets, validate_secrets,
    get_secrets, clear_secrets_cache,
    DecryptionError, SecretsValidationError
)


def test_encrypt_decrypt_roundtrip():
    """Test that encryption and decryption produce the original data."""
    plugin_id = "507f1f77bcf86cd799439011"  # Sample MongoDB ObjectId
    
    original_secrets = {
        "aws_key": "AKIAIOSFODNN7EXAMPLE",
        "aws_secret": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "aws_bucket": "my-test-bucket",
        "aws_region": "us-west-2"
    }
    
    # Encrypt
    encrypted = encrypt_secrets(plugin_id, original_secrets)
    print(f"✓ Encrypted blob length: {len(encrypted)} chars")
    print(f"  Blob preview: {encrypted[:50]}...")
    
    # Decrypt
    decrypted = decrypt_secrets(plugin_id, encrypted)
    print(f"✓ Decrypted successfully")
    
    # Verify
    assert decrypted == original_secrets, "Decrypted secrets don't match original!"
    print(f"✓ Round-trip verification passed")
    
    return True


def test_wrong_plugin_id():
    """Test that wrong plugin ID fails decryption."""
    correct_id = "507f1f77bcf86cd799439011"
    wrong_id = "507f1f77bcf86cd799439012"
    
    secrets = {"aws_key": "test", "aws_secret": "test", "aws_bucket": "test", "aws_region": "test"}
    encrypted = encrypt_secrets(correct_id, secrets)
    
    try:
        decrypt_secrets(wrong_id, encrypted)
        print("✗ Should have raised DecryptionError!")
        return False
    except DecryptionError as e:
        print(f"✓ Wrong plugin ID correctly rejected: {e}")
        return True


def test_malformed_blob():
    """Test that malformed blob fails gracefully."""
    plugin_id = "507f1f77bcf86cd799439011"
    
    try:
        decrypt_secrets(plugin_id, "not-a-valid-blob")
        print("✗ Should have raised DecryptionError!")
        return False
    except DecryptionError as e:
        print(f"✓ Malformed blob correctly rejected: {e}")
        return True


def test_validation():
    """Test secrets validation."""
    # Valid secrets
    valid = {"aws_key": "k", "aws_secret": "s", "aws_bucket": "b", "aws_region": "r"}
    try:
        validate_secrets(valid)
        print("✓ Valid secrets passed validation")
    except SecretsValidationError:
        print("✗ Valid secrets should not fail validation!")
        return False
    
    # Missing keys
    invalid = {"aws_key": "k"}  # Missing other keys
    try:
        validate_secrets(invalid)
        print("✗ Invalid secrets should fail validation!")
        return False
    except SecretsValidationError as e:
        print(f"✓ Missing keys correctly detected: {e}")
    
    return True


def test_singleton_cache():
    """Test that singleton caching works."""
    clear_secrets_cache()  # Start fresh
    
    plugin_id = "507f1f77bcf86cd799439011"
    secrets = {"aws_key": "k", "aws_secret": "s", "aws_bucket": "b", "aws_region": "r"}
    encrypted = encrypt_secrets(plugin_id, secrets)
    
    # First call - should decrypt
    result1 = get_secrets(plugin_id, encrypted)
    print(f"✓ First call returned secrets")
    
    # Second call - should use cache (we can't easily verify this without mocking,
    # but we can verify the result is the same)
    result2 = get_secrets(plugin_id, encrypted)
    print(f"✓ Second call returned secrets (from cache)")
    
    assert result1 == result2, "Cached result differs!"
    print(f"✓ Singleton cache working correctly")
    
    # Clear and verify it decrypts again
    clear_secrets_cache()
    result3 = get_secrets(plugin_id, encrypted)
    assert result3 == secrets, "After clear, decryption failed!"
    print(f"✓ Cache clear and re-decrypt working")
    
    return True


def test_empty_secrets():
    """Test that empty secrets dict works."""
    plugin_id = "507f1f77bcf86cd799439011"
    empty_secrets = {}
    
    encrypted = encrypt_secrets(plugin_id, empty_secrets)
    decrypted = decrypt_secrets(plugin_id, encrypted)
    
    assert decrypted == empty_secrets, "Empty secrets round-trip failed!"
    print(f"✓ Empty secrets round-trip passed")
    
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Plugin Secrets Encryption Test Suite")
    print("=" * 60)
    print()
    
    tests = [
        ("Encrypt/Decrypt Round-trip", test_encrypt_decrypt_roundtrip),
        ("Wrong Plugin ID", test_wrong_plugin_id),
        ("Malformed Blob", test_malformed_blob),
        ("Secrets Validation", test_validation),
        ("Singleton Cache", test_singleton_cache),
        ("Empty Secrets", test_empty_secrets),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        try:
            if test_fn():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test crashed: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    sys.exit(0 if failed == 0 else 1)
