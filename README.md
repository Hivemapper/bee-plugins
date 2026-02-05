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

## Deploy
Use your provided plugin name and secret key to build and deploy the build artifact
```
python3 deploy.py -n plugin-name -s mysecretkeygoeshere -i myplugin.py
```
