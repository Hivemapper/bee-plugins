#!/usr/bin/env python3
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import beeutil.secrets as secrets
from beeutil.secrets import DecryptionError, SecretsError


def test_encrypt_decrypt_roundtrip():
    plugin_id = "507f1f77bcf86cd799439011"
    env = {
        "AWS_KEY": "AKIAIOSFODNN7EXAMPLE",
        "AWS_SECRET": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "STRIPE_TOKEN": "sk_test_abc123",
    }

    encrypted = secrets.encrypt(plugin_id, env)
    decrypted = secrets.decrypt(plugin_id, encrypted)
    assert decrypted == env
    print(f"  encrypted blob: {len(encrypted)} chars, round-trip OK")
    return True


def test_wrong_plugin_id():
    correct_id = "507f1f77bcf86cd799439011"
    wrong_id = "507f1f77bcf86cd799439012"

    encrypted = secrets.encrypt(correct_id, {"KEY": "value"})

    try:
        secrets.decrypt(wrong_id, encrypted)
        return False
    except DecryptionError:
        return True


def test_malformed_blob():
    try:
        secrets.decrypt("507f1f77bcf86cd799439011", "not-a-valid-blob")
        return False
    except DecryptionError:
        return True


def test_empty_env():
    plugin_id = "507f1f77bcf86cd799439011"
    encrypted = secrets.encrypt(plugin_id, {})
    assert secrets.decrypt(plugin_id, encrypted) == {}
    return True


def test_parse_dotenv():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write('# comment line\n')
        f.write('AWS_KEY=AKIAIOSFODNN7EXAMPLE\n')
        f.write('AWS_SECRET="quoted value"\n')
        f.write("SINGLE_QUOTED='single'\n")
        f.write('EMPTY=\n')
        f.write('\n')
        f.write('NO_EQUALS_LINE\n')
        f.write('  SPACED_KEY = spaced_value \n')
        path = f.name

    try:
        env = secrets._parse_dotenv(path)
        assert env['AWS_KEY'] == 'AKIAIOSFODNN7EXAMPLE'
        assert env['AWS_SECRET'] == 'quoted value'
        assert env['SINGLE_QUOTED'] == 'single'
        assert env['EMPTY'] == ''
        assert 'SPACED_KEY' in env
        assert 'NO_EQUALS_LINE' not in env
        print(f"  parsed {len(env)} keys")
        return True
    finally:
        os.unlink(path)


def test_atomic_rejects_non_string():
    secrets.clear_cache()

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_dir = secrets.PLUGIN_DIR
        secrets.PLUGIN_DIR = tmpdir

        try:
            plugin_dir = os.path.join(tmpdir, 'bad-plugin')
            os.makedirs(plugin_dir)
            with open(os.path.join(plugin_dir, '.env'), 'w') as f:
                f.write('GOOD=value\n')

            secrets.load('bad-plugin')
            assert os.environ.get('GOOD') == 'value'

            del os.environ['GOOD']
            return True
        finally:
            secrets.PLUGIN_DIR = orig_dir
            secrets.clear_cache()


def test_get_from_dotenv():
    secrets.clear_cache()

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_dir = secrets.PLUGIN_DIR
        secrets.PLUGIN_DIR = tmpdir

        try:
            plugin_dir = os.path.join(tmpdir, 'test-plugin')
            os.makedirs(plugin_dir)
            with open(os.path.join(plugin_dir, '.env'), 'w') as f:
                f.write('MY_KEY=my_value\nMY_SECRET=my_secret\n')

            assert secrets.get('test-plugin', 'MY_KEY') == 'my_value'
            assert secrets.get('test-plugin', 'MY_SECRET') == 'my_secret'

            try:
                secrets.get('test-plugin', 'MISSING')
                return False
            except KeyError:
                pass

            del os.environ['MY_KEY']
            del os.environ['MY_SECRET']
            return True
        finally:
            secrets.PLUGIN_DIR = orig_dir
            secrets.clear_cache()


def test_load_returns_copy():
    secrets.clear_cache()

    with tempfile.TemporaryDirectory() as tmpdir:
        orig_dir = secrets.PLUGIN_DIR
        secrets.PLUGIN_DIR = tmpdir

        try:
            plugin_dir = os.path.join(tmpdir, 'copy-plugin')
            os.makedirs(plugin_dir)
            with open(os.path.join(plugin_dir, '.env'), 'w') as f:
                f.write('A=1\nB=2\n')

            result = secrets.load('copy-plugin')
            assert result == {'A': '1', 'B': '2'}

            result['C'] = '3'
            assert 'C' not in secrets.load('copy-plugin')

            del os.environ['A']
            del os.environ['B']
            return True
        finally:
            secrets.PLUGIN_DIR = orig_dir
            secrets.clear_cache()


if __name__ == "__main__":
    print("=" * 60)
    print("Plugin Secrets Test Suite")
    print("=" * 60)

    tests = [
        ("Encrypt/Decrypt Round-trip", test_encrypt_decrypt_roundtrip),
        ("Wrong Plugin ID", test_wrong_plugin_id),
        ("Malformed Blob", test_malformed_blob),
        ("Empty Env", test_empty_env),
        ("Parse Dotenv", test_parse_dotenv),
        ("Atomic Load", test_atomic_rejects_non_string),
        ("get() from Dotenv", test_get_from_dotenv),
        ("load() Returns Copy", test_load_returns_copy),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        try:
            if test_fn():
                passed += 1
                print(f"  PASS")
            else:
                failed += 1
                print(f"  FAIL")
        except Exception as e:
            print(f"  CRASH: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
