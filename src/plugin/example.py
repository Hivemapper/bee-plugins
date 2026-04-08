import beeutil
import queue
import threading
import time
import uuid

PLUGIN_NAME = 'your-plugin-name'

CAPTURE_STEREO = False
LOOP_DELAY = 5
UPLOAD_THREADS = 1
VERBOSE = True

# Run a device health check every N loop iterations
HEALTH_CHECK_INTERVAL = 60


def vlog(msg):
  if VERBOSE:
    print(f'[{time.asctime()}] {msg}')

def _setup(state):
  # Check device health before starting (detects CAP-96 clock drift, GPS issues)
  vlog('running device health check')
  health = beeutil.device_health.check()
  if not health['healthy']:
    for w in health['warnings']:
      vlog(f'HEALTH WARNING: {w}')

  vlog('enabling image caching')
  beeutil.enable_image_collection()

  if CAPTURE_STEREO:
    vlog('enabling stereo caching')
    beeutil.enable_stereo_collection()

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
      handle = state['uploadQueue'].get()
      beeutil.upload_to_s3(
        state['session'],
        handle,
        beeutil.secrets.get(PLUGIN_NAME, 'AWS_BUCKET'),
        beeutil.secrets.get(PLUGIN_NAME, 'AWS_REGION'),
        beeutil.secrets.get(PLUGIN_NAME, 'AWS_SECRET'),
        beeutil.secrets.get(PLUGIN_NAME, 'AWS_KEY'),
      )

  state['threads'] = [threading.Thread(target=upload_worker, daemon=True).start() for i in range(UPLOAD_THREADS)]
  state['uploadQueue'] = queue.Queue()
  state['loop_count'] = 0

def _loop(state):
  # Periodic health check
  state['loop_count'] += 1
  if state['loop_count'] % HEALTH_CHECK_INTERVAL == 0:
    health = beeutil.device_health.check()
    if not health['healthy']:
      for w in health['warnings']:
        vlog(f'HEALTH WARNING: {w}')

  contents = beeutil.list_contents(state['last_checked'])

  if len(contents) == 0:
    vlog(f'no new content since {state["last_checked"]}')
    return

  vlog(f'since {state["last_checked"]}:')
  vlog(contents)

  for handle in contents:
    state['uploadQueue'].put(handle)

  state['last_checked'] = contents[-1].split('_')[0]

def main():
  state = {
    'last_checked': None,
    'session': '',
    'threads': None,
    'uploadQueue': None,
    'loop_count': 0,
  }

  vlog('setting up plugin')
  _setup(state)

  vlog('initializing run loop')
  while True:
    _loop(state)
    time.sleep(LOOP_DELAY)
