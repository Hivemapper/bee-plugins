import requests

HOST_URL = 'http://127.0.0.1:5000'
CACHE_ROUTE = f'{HOST_URL}/cache'

def image_cache_status():
  res = requests.get(f'{CACHE_ROUTE}/status')
  if res.status_code != 200:
    raise Exception(res.json())

  return status

def enable_image_collection():
  res = requests.get(f'{CACHE_ROUTE}/enable')
  if res.status_code != 200:
    raise Exception(res.json())

  print(res.json())

def disable_image_collection():
  res = requests.get(f'{CACHE_ROUTE}/disable')  
  if res.status_code != 200:
    raise Exception(res.json())

  print(res.json())

def purge_data():
  res = requests.get(f'{CACHE_ROUTE}/purge')  
  if res.status_code != 200:
    raise Exception(res.json())

  print(res.json())

def enable_stereo_collection():
  res = requests.post(f'{CACHE_ROUTE}/enableDepthFlag')
  if res.status_code != 200:
    raise Exception(res.json())

  print(res.json())

def disable_stereo_collection():
  res = requests.post(f'{CACHE_ROUTE}/disableDepthFlag')
  if res.status_code != 200:
    raise Exception(res.json())

  print(res.json())

def list_contents(since = None, until = None):
  url = f'{CACHE_ROUTE}/list'
  if since is not None or until is not None:
    url += '?'
    if since is not None:
      url += f'since={since}'
      if until is not None:
        url += '&'
    if until is not None:
      url += f'until={until}'

  res = requests.get(url)
  if res.status_code != 200:
    raise Exception(res.json())

  contents = res.json()
  return contents

def cache_dir():
  return '/data/cache'

def upload_to_s3(prefix, handle, aws_bucket, aws_region, aws_secret, aws_key):
  url = f'{CACHE_ROUTE}/uploadS3/{handle}?prefix={prefix}&key={aws_key}&bucket={aws_bucket}&region={aws_region}'
  headers = {
    'authorization': aws_secret,
  }
  res = requests.post(url, headers)

  if res.status_code != 200:
    raise Exception(res.json())

  print (res.json())
