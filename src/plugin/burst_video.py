import beeutil
import queue
import threading
import time
import uuid

PLUGIN_NAME = 'burst-video'

LOOP_DELAY = 10
BURST_REFRESH_INTERVAL = 300
UPLOAD_THREADS = 2
VERBOSE = True

def vlog(msg):
  if VERBOSE:
    print(f'[{time.asctime()}] {msg}')

def _setup(state):
  vlog('enabling image caching')
  beeutil.enable_image_collection()

  state['session'] = str(uuid.uuid1())

  vlog('loading env')
  try:
    beeutil.secrets.load(PLUGIN_NAME)
    vlog('env loaded')
  except beeutil.SecretsError as e:
    vlog(f'ERROR: Failed to load env: {e}')
    raise

  vlog(f'initializing {UPLOAD_THREADS} upload workers')
  state['uploadQueue'] = queue.Queue()

  def upload_worker():
    while True:
      item = state['uploadQueue'].get()
      try:
        burst_id = item['burst_id']
        filepath = item['filepath']
        prefix = f'{state["session"]}/burst/{burst_id}'
        vlog(f'uploading {filepath} for burst {burst_id}')
        beeutil.upload_video_to_s3(
          prefix,
          filepath,
          beeutil.secrets.get(PLUGIN_NAME, 'AWS_BUCKET'),
          beeutil.secrets.get(PLUGIN_NAME, 'AWS_REGION'),
          beeutil.secrets.get(PLUGIN_NAME, 'AWS_SECRET'),
          beeutil.secrets.get(PLUGIN_NAME, 'AWS_KEY'),
        )
        vlog(f'uploaded {filepath}')
      except Exception as e:
        vlog(f'ERROR uploading {item.get("filepath", "?")}: {e}')
      finally:
        state['uploadQueue'].task_done()

  for _ in range(UPLOAD_THREADS):
    threading.Thread(target=upload_worker, daemon=True).start()

  vlog('fetching initial burst geometries')
  state['bursts'] = _refresh_bursts(state)
  state['last_burst_refresh'] = time.time()
  state['last_video_check'] = None
  state['uploaded_videos'] = set()

def _refresh_bursts(state):
  try:
    api_key = beeutil.secrets.get(PLUGIN_NAME, 'BEEMAPS_API_KEY')
    bursts = beeutil.fetch_active_bursts(api_key)
    vlog(f'fetched {len(bursts)} active bursts')
    return bursts
  except Exception as e:
    vlog(f'ERROR fetching bursts: {e}')
    return state.get('bursts', [])

def _loop(state):
  now = time.time()

  if now - state['last_burst_refresh'] > BURST_REFRESH_INTERVAL:
    state['bursts'] = _refresh_bursts(state)
    state['last_burst_refresh'] = now

  if not state['bursts']:
    vlog('no active bursts')
    return

  position = beeutil.get_gnss_position()
  if position is None:
    vlog('no GNSS position available')
    return

  lat = position['lat']
  lon = position['lon']

  matching_burst = None
  for burst in state['bursts']:
    geojson = burst.get('geojson')
    if geojson and beeutil.point_in_geojson(lat, lon, geojson):
      matching_burst = burst
      break

  if matching_burst is None:
    vlog(f'not in any burst area ({lat:.5f}, {lon:.5f})')
    return

  burst_id = matching_burst.get('id', 'unknown')
  vlog(f'in burst area {burst_id} ({lat:.5f}, {lon:.5f})')

  videos = beeutil.list_video_contents(since=state['last_video_check'])

  new_videos = [v for v in videos if v['filename'] not in state['uploaded_videos']]

  if not new_videos:
    vlog('no new videos to upload')
  else:
    vlog(f'queueing {len(new_videos)} videos for upload')
    for video in new_videos:
      state['uploaded_videos'].add(video['filename'])
      state['uploadQueue'].put({
        'burst_id': burst_id,
        'filepath': video['filepath'],
      })

  if videos:
    last_ts = max(v['timestamp_ms'] for v in videos if v['timestamp_ms'] is not None)
    if last_ts is not None:
      state['last_video_check'] = last_ts

def main():
  state = {
    'session': '',
    'bursts': [],
    'last_burst_refresh': 0,
    'last_video_check': None,
    'uploaded_videos': set(),
    'uploadQueue': None,
  }

  vlog('setting up burst video plugin')
  _setup(state)

  vlog('initializing run loop')
  while True:
    _loop(state)
    time.sleep(LOOP_DELAY)
