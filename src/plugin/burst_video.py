import os
import queue
import threading
import time
import uuid

import beeutil

LOOP_DELAY = 10
BURST_REFRESH_INTERVAL = 300
BURST_RADIUS_M = int(os.environ.get('BURST_RADIUS_M', '10000'))
UPLOAD_THREADS = 2
VERBOSE = True


def vlog(msg):
  if VERBOSE:
    print(f'[{time.asctime()}] {msg}')


def _env(name):
  value = os.environ.get(name)
  if value in (None, ''):
    raise RuntimeError(f'missing required env var: {name}')
  return value


def _setup(state):
  state['session'] = str(uuid.uuid1())

  vlog(f'initializing {UPLOAD_THREADS} upload workers')
  state['uploadQueue'] = queue.Queue()
  state['queued_videos'] = set()
  state['completed_videos'] = set()
  state['evaluated_videos'] = {}
  state['burst_cache_version'] = 0

  def upload_worker():
    while True:
      item = state['uploadQueue'].get()
      filename = item['filename']
      filepath = item['filepath']
      ready_filepath = item['ready_filepath']
      burst_id = item['burst_id']
      try:
        prefix = f'{state["session"]}/burst/{burst_id}'
        vlog(f'uploading {filename} for burst {burst_id}')
        beeutil.upload_video_to_s3(
          prefix,
          filepath,
          _env('AWS_BUCKET'),
          _env('AWS_REGION'),
          _env('AWS_SECRET'),
          _env('AWS_KEY'),
        )
        beeutil.delete_video(filepath, ready_filepath)
        state['completed_videos'].add(filename)
        vlog(f'uploaded {filename}')
      except Exception as e:
        vlog(f'ERROR uploading {filename}: {e}')
      finally:
        state['queued_videos'].discard(filename)
        state['uploadQueue'].task_done()

  for _ in range(UPLOAD_THREADS):
    threading.Thread(target=upload_worker, daemon=True).start()

  vlog('fetching nearby burst cache')
  state['bursts'] = _refresh_bursts(state)
  state['last_burst_refresh'] = time.time()


def _refresh_bursts(state):
  position = beeutil.get_gnss_position()
  if position is None:
    vlog('unable to determine current GNSS position, keeping existing burst cache')
    return state.get('bursts', [])

  bursts = beeutil.fetch_nearby_bursts(
    position['lat'],
    position['lon'],
    radius_m=BURST_RADIUS_M,
  )
  state['burst_cache_version'] += 1
  vlog(
    f'fetched {len(bursts)} nearby bursts within {BURST_RADIUS_M}m around '
    f'{position["lat"]:.5f},{position["lon"]:.5f} '
    f'(cache version {state["burst_cache_version"]})'
  )
  return bursts


def _prune_evaluated_videos(state, videos):
  active_filenames = {video['filename'] for video in videos}
  keep_filenames = active_filenames | state['queued_videos'] | state['completed_videos']
  stale_filenames = [
    filename for filename in state['evaluated_videos']
    if filename not in keep_filenames
  ]
  for filename in stale_filenames:
    del state['evaluated_videos'][filename]


def _match_burst(video, bursts):
  gps_samples = video.get('gps_samples') or []
  for burst in bursts:
    geojson = burst.get('geojson')
    if not geojson:
      continue
    for sample in gps_samples:
      lat = sample.get('lat')
      lon = sample.get('lon')
      if lat is None or lon is None:
        continue
      if beeutil.point_in_geojson(lat, lon, geojson):
        return burst

  return None


def _describe_video(video):
  gps_samples = video.get('gps_samples') or []
  if not gps_samples:
    return f'{video["filename"]} (no GPS metadata)'

  first = gps_samples[0]
  last = gps_samples[-1]
  return (
    f'{video["filename"]} '
    f'({len(gps_samples)} gps samples, '
    f'start={first["lat"]:.5f},{first["lon"]:.5f}, '
    f'end={last["lat"]:.5f},{last["lon"]:.5f})'
  )


def _loop(state):
  now = time.time()
  if now - state['last_burst_refresh'] > BURST_REFRESH_INTERVAL:
    try:
      state['bursts'] = _refresh_bursts(state)
      state['last_burst_refresh'] = now
    except Exception as e:
      vlog(f'ERROR refreshing nearby bursts: {e}')

  videos = beeutil.list_video_contents()
  _prune_evaluated_videos(state, videos)

  pending_videos = [
    video for video in videos
    if video['filename'] not in state['completed_videos']
    and video['filename'] not in state['queued_videos']
    and state['evaluated_videos'].get(video['filename']) != state['burst_cache_version']
  ]

  if not pending_videos:
    vlog('no ready videos to process')
    return

  if not state['bursts']:
    for video in pending_videos:
      state['evaluated_videos'][video['filename']] = state['burst_cache_version']
    vlog(f'no nearby bursts cached, leaving {len(pending_videos)} ready videos queued on disk')
    return

  matched_count = 0
  for video in pending_videos:
    burst = _match_burst(video, state['bursts'])
    state['evaluated_videos'][video['filename']] = state['burst_cache_version']
    if burst is None:
      vlog(f'no burst match for {_describe_video(video)}')
      continue

    burst_id = burst.get('id', 'unknown')
    vlog(f'matched {_describe_video(video)} to burst {burst_id}')
    state['queued_videos'].add(video['filename'])
    state['uploadQueue'].put({
      'burst_id': burst_id,
      'filename': video['filename'],
      'filepath': video['filepath'],
      'ready_filepath': video['ready_filepath'],
    })
    matched_count += 1

  if matched_count == 0:
    vlog('no ready videos matched any active burst')


def main():
  state = {
    'session': '',
    'bursts': [],
    'last_burst_refresh': 0,
    'uploadQueue': None,
    'queued_videos': set(),
    'completed_videos': set(),
    'evaluated_videos': {},
    'burst_cache_version': 0,
  }

  vlog('setting up burst video plugin')
  _setup(state)

  vlog('initializing run loop')
  while True:
    _loop(state)
    time.sleep(LOOP_DELAY)
