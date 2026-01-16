import beeutil
import queue
import threading
import time

AWS_BUCKET = 'your_bucket'
AWS_REGION = 'your-aws-region'
AWS_SECRET = 'IaMaSeCrEt'
AWS_KEY = 'iAmAkEy'

CAPTURE_STEREO = False
LOOP_DELAY = 5
UPLOAD_THREADS = 1
VERBOSE = True

def vlog(msg):
  if VERBOSE:
    print(f'[{time.asctime()}] {msg}')

def _setup(state):
  vlog('enabling image caching')
  beeutil.enable_image_collection()

  if CAPTURE_STEREO:
    vlog('enabling stereo caching')
    beeutil.enable_stereo_collection()

  vlog(f'initializing {UPLOAD_THREADS} upload workers')
  state['uploadQueue'] = queue.Queue()

  def upload_worker():
    while True:
      handle = state['uploadQueue'].get()
      beeutil.upload_to_s3(handle, BUCKET, REGION, AWS_SECRET, AWS_KEY)

  state['threads'] = [threading.Thread(target=upload_worker, daemon=True).start() for i in range(UPLOAD_THREADS)]
  state['uploadQueue'] = queue.Queue()

def _loop(state):
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
    'threads': None,
    'uploadQueue': None,
  }

  vlog('setting up plugin')
  _setup(state)

  vlog('initializing run loop')
  while True:
    _loop(state)
    time.sleep(LOOP_DELAY)
