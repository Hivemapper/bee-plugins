# bee-plugins
Develop realtime mapping and edge AI solutions with the Bee

## Installation
```
python3 -m pip install -r requirements.txt
```

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
python3 devtools -f tokyo
```

**Provided Fixtures**
- `sf`
- `tokyo`


*To dump cache contents to local machine:*
```
python3 devtools -d
```

#### State dump
*To dump the device logs and state to a zip file:*
```
python3 devtools -sd
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

Plugins can securely load AWS credentials at runtime instead of hardcoding them in source code.

### Usage in your plugin

```python
import beeutil

def _setup(state):
    # Load secrets once per session (cached automatically)
    # Tries: env vars → secrets.json → API (in that order)
    secrets = beeutil.load_secrets(plugin_name='your-plugin-name')
    
    # Use the credentials
    aws_key = secrets['aws_key']
    aws_secret = secrets['aws_secret']
    aws_bucket = secrets['aws_bucket']
    aws_region = secrets['aws_region']
```

### Local Development (Option 1: Environment Variables)

For local testing, set these environment variables:

```bash
export PLUGIN_AWS_KEY="AKIAIOSFODNN7EXAMPLE"
export PLUGIN_AWS_SECRET="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
export PLUGIN_AWS_BUCKET="my-bucket"
export PLUGIN_AWS_REGION="us-west-2"
```

Then in your plugin:
```python
# No plugin_name needed when using env vars
secrets = beeutil.load_secrets()
```

### Local Development (Option 2: Config File)

Create a `secrets.json` file in your plugin directory:

```json
{
    "aws_key": "AKIAIOSFODNN7EXAMPLE",
    "aws_secret": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "aws_bucket": "my-bucket",
    "aws_region": "us-west-2"
}
```

**Important:** Add `secrets.json` to `.gitignore` to avoid committing credentials!

### Production Deployment

For production, secrets are encrypted and stored in Hivemapper backend:

1. **Developer encrypts secrets** using the plugin `_id` as the encryption key
2. **Encrypted blob is stored** in Hivemapper backend (TODO: API route)
3. **Device fetches and decrypts** at runtime

```python
from beeutil import encrypt_secrets

plugin_id = "your-plugin-mongodb-id"
secrets = {
    "aws_key": "AKIAIOSFODNN7EXAMPLE",
    "aws_secret": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "aws_bucket": "my-bucket",
    "aws_region": "us-west-2"
}

encrypted_blob = encrypt_secrets(plugin_id, secrets)
print(encrypted_blob)  # Upload this to Hivemapper backend
```

### Technical details

- **Algorithm**: AES-256-CBC with PKCS7 padding
- **Key derivation**: PBKDF2-HMAC-SHA256 (100k iterations)
- **Library**: Uses `cryptography` (pre-installed on device)
- **Priority**: Environment variables → `secrets.json` → API


## Deploy
Use your provided plugin name and secret key to build and deploy the build artifact
```
python3 deploy.py -n plugin-name -s mysecretkeygoeshere -i myplugin.py
```
