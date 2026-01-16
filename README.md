# bee-plugins
Develop realtime mapping and edge AI solutions with the Bee

## Development
Use `src/plugin/example.py` to edit variables, etc.

## Build
```
bash build.sh [output_name] [entrypoint]
```
will output `myplugin.py` by default, or specify a custom name:
```
bash build.sh hello
```

## Deploy
Use your provided plugin name and secret key to build and deploy the build artifact
```
python3 deploy.py -n plugin-name -s mysecretkeygoeshere -i myplugin.py
```
