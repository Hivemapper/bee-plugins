# bee-plugins
Develop realtime mapping and edge AI solutions with the Bee

## Device constraints

Bee devices run **Python 3.8** with pre-installed system packages (numpy 1.17, requests 2.23, cryptography 2.8). All code in `beeutil` must be compatible with Python 3.8 syntax and stdlib. Ruff is configured with `target-version = "py38"` to enforce this.

Plugins are packaged as zipapps and cannot install additional packages on device. Only use dependencies that are already available on the device or bundled into the zipapp.

## Installation
```bash
uv sync --group dev
source .venv/bin/activate
```

The installable Python package in this repo is `beeutil`. The root scripts such as
`devtools.py`, `device.py`, and `deploy.py` remain repo-local tooling.

## Quality Checks
```bash
ruff check .
ruff format .
pytest
mypy
```

To install the local Git hooks:
```bash
pre-commit install
```

## Legacy Setup
The old `requirements.txt` workflow has been replaced by `pyproject.toml`.

## Build
```
bash build.sh [output_name] [entrypoint]
```
will output `myplugin.py` by default, or specify a custom name:
```
bash build.sh hello
```


## Development
Use `src/plugin/example.py` to edit variables, etc.

### Local Development
While connected to the device over WiFi (password `hivemapper`), run the following to interact with the device

*To disable automatic over-the-air updates, which will wipe out local changes, enable dev mode:*
```
python3 devtools.py -dI
```

*To upload a local build artifact*
```
python3 devtools.py -i myplugin.py
```
This will automatically restart the plugin service on the device


*To manually restart the plugin service on the device*
```
python3 devtools.py -R
```

*To enable automatic over-the-air updates, which will wipe out local changes, disable dev mode:*
```
python3 devtools.py -dO
```

#### Fixture Data
*To load fixture data, specify a fixture dataset like:*
```
python3 devtools.py -f tokyo
```

**Provided Fixtures**
- `sf`
- `tokyo`


*To dump cache contents to local machine:*
```
python3 devtools.py -d
```

#### State dump
*To dump the device logs and state to a zip file:*
```
python3 devtools.py -sd
```

#### Networking
*To switch the network client to use WiFi, specify a SSID/password:*
```
python3 device.py -Wi mynetworkssid -P mynetworkpassword
```

*To switch the network client back to LTE:*
```
python3 device.py -L
```

*To view the WiFi SSIDs openly broadcasting to the Bee:*
```
python3 device.py -Ws
```

*To view WiFi status/settings:*
```
python3 device.py -W
```


### Calibration
*To retrieve device-specific calibration data:*
```
python3 device.py -C > calibration.json
```

## Encrypted Secrets

Plugins can securely load arbitrary environment variables at runtime instead of hardcoding credentials in source code. Keys are not restricted — any string key-value pairs work.

### Usage in your plugin

```python
import beeutil

def _setup(state):
    # Load all secrets (cached after first call)
    # Tries: .env file → Hivemapper API via ODC (in that order)
    env = beeutil.secrets.load('my-plugin')
    bucket = env['AWS_BUCKET']

    # Or get a single key
    bucket = beeutil.secrets.get('my-plugin', 'AWS_BUCKET')
```

### Local Development (.env file)

Create `/data/plugins/<plugin-name>/.env` on the device, or push via devtools:
```bash
python3 devtools.py -e path/to/.env
```

Example `.env`:
```
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_BUCKET=my-bucket
AWS_REGION=us-west-2
MY_CUSTOM_KEY=whatever
```

### Production (encrypt + upload to Hivemapper backend)

Use the provided upload script:
```bash
python3 util/upload_secrets.py \
    --plugin-name my-plugin \
    --plugin-secret <plugin-api-key> \
    --env-file .env
```

This will:
1. Parse the `.env` file into key-value pairs
2. Fetch the plugin's `_id` from the Hivemapper backend
3. Encrypt the KV pairs using `_id` as key material (PBKDF2 + AES-256-CBC)
4. Upload the encrypted blob via `PUT /plugins/:name/secrets`

The device fetches and decrypts at runtime via ODC API. Use `--dry-run` to encrypt without uploading.

### Technical details

- **Algorithm**: AES-256-CBC with PKCS7 padding
- **Key derivation**: PBKDF2-HMAC-SHA256 (100k iterations, salt: `hivemapper-plugin-secrets`)
- **Library**: Uses `cryptography` (pre-installed on device)
- **Loading priority**: `.env` file → Hivemapper API (via ODC)


## Deploy
Use your provided plugin name and secret key to build and deploy the build artifact
```
python3 deploy.py -n plugin-name -s mysecretkeygoeshere -i myplugin.py
```
