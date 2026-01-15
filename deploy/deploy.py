import hashlib
import requests

def get_upload_url(plugin_name, plugin_secret):
  res = requests.get('https://beemaps.com/api/plugins/upload/{plugin_name}?secret{plugin_secret}')
  if res.status != 200:
    raise Exception(res.json())

  res_data = res.json()
  return res_data['url']

def plugin_hash(filepath):
  sha256_hash = hashlib.sha256()
  with open(filepath, 'rb') as plugin_bin:
    for chunk in iter(lambda: plugin_bin.read(4096), b""):
      sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def upload_plugin(filepath, url):
  with open(filepath, 'rb') as plugin_bin:
    res = requests.put(url, headers, data=plugin_bin)

  if res.status != 200:
    raise Exception(res.json())

def update_plugin(plugin_name, plugin_secret, filepath, version = 1):
  upload_url = get_upload_url(plugin_name, plugin_secret)
  upload_plugin(filepath, upload_url)
  sha256 = plugin_hash(filepath)

  url = 'https://beemaps.com/api/plugins/upload/{plugin_name}?secret{plugin_secret}'
  headers = {
    'content-type': 'application/json',
  }
  data = {
    "version": version,
    "hash": sha256,
  }
  res = requests.put(url, headers, data)
  if res.status != 200:
    raise Exception(res.json())

  return res.json()

def plugin_info(plugin_name):
  url = 'https://beemaps.com/api/plugins/upload/{plugin_name}'
  res = requests.get(url)
  if res.status != 200:
    raise Exception(res.json())

  return res.json()
