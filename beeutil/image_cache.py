import requests

HOST_URL = 'http://192.168.0.10:5000'
CACHE_ROUTE = f'{HOST_URL}/cache'

def image_cache_status():
  res = requests.get('http://192.168.0.10:5000/cache/status')
  if res.status_code != 200:
    raise Exception(res.json())

  return status

def enable_image_collection():
  requests.get(f'{CACHE_ROUTE}/enable')

def disable_image_collection():
  requests.get(f'{CACHE_ROUTE}/disable')  

def purge_data():
  requests.get(f'{CACHE_ROUTE}/purge')  

def enable_stereo_collection():
  requests.post(f'{CACHE_ROUTE}/enableDepthFlag')

def disable_stereo_collection():
  requests.post(f'{CACHE_ROUTE}/disableDepthFlag')

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

def upload_to_s3(handle, aws_bucket, aws_region, aws_secret, aws_key):
  url = f'{CACHE_ROUTE}/uploadS3/{handle}?key={aws_key}&bucket={aws_bucket}&region={aws_region}'
  headers = {
    'authorization': aws_secret,
  }
  res = requests.post(url, headers)

  if res.status_code != 200:
    raise Exception(res.json())
