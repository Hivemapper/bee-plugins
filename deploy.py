import argparse
import hashlib
import requests

def get_upload_url(plugin_name, plugin_secret):
  url = f'https://beemaps.com/api/plugins/upload/{plugin_name}?secret={plugin_secret}'
  print(url)
  res = requests.get(url)
  if res.status_code != 200:
    raise Exception(res.json())

  res_data = res.json()
  signed_url = res_data['url']
  return signed_url

def plugin_hash(filepath):
  sha256_hash = hashlib.sha256()
  with open(filepath, 'rb') as plugin_bin:
    for chunk in iter(lambda: plugin_bin.read(4096), b""):
      sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def upload_plugin(filepath, url):
  with open(filepath, 'rb') as plugin_bin:
    res = requests.put(url, data=plugin_bin)

  if res.status_code != 200:
    raise Exception(res.json())

def update_plugin(plugin_name, plugin_secret, filepath, version = 1):
  print(f'[{plugin_name}] uploading {filepath}')
  upload_url = get_upload_url(plugin_name, plugin_secret)
  upload_plugin(filepath, upload_url)
  sha256 = plugin_hash(filepath)

  print(f'[{plugin_name}] registering {sha256}')

  url = f'https://beemaps.com/api/plugins/{plugin_name}?secret={plugin_secret}'
  data = {
    "version": version,
    "hash": sha256,
  }
  res = requests.put(url, json=data)
  if res.status_code != 200:
    raise Exception(res.json())

  return res.json()

def plugin_info(plugin_name):
  url = f'https://beemaps.com/api/plugins/{plugin_name}'
  res = requests.get(url)
  if res.status_code != 200:
    raise Exception(res.json())

  return res.json()

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Upload and deploy bee plugins.")

  parser.add_argument('-n', '--name', help="Plugin name.", type=str, required=True)
  parser.add_argument('-s', '--secret', help="Plugin auth secret.", type=str, required=True)
  parser.add_argument('-i', '--input_file', help="Path to build.sh output .py file.", type=str, required=True)
  parser.add_argument('-v', '--version', help="Note-level version", default=1)

  args = parser.parse_args()

  update_plugin(args.name, args.secret, args.input_file, args.version)

  info = plugin_info(args.name)
  print(info)
