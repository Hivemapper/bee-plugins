import beeutil
import queue
import threading
import time
import uuid
import requests

PLUGIN_NAME = 'burst-video'

LOOP_DELAY = 15
BURST_REFRESH_INTERVAL = 300
UPLOAD_THREADS = 2
VERBOSE = True

BEEMAPS_API_URL = 'https://hivemapper.com/api/developer/bursts'


def vlog(msg):
    if VERBOSE:
        print(f'[{time.asctime()}] {msg}')


def _fetch_bursts(state):
    """Fetch active burst geometries from beemaps API."""
    now = time.time()
    if state.get('bursts_fetched_at') and \
       now - state['bursts_fetched_at'] < BURST_REFRESH_INTERVAL:
        return state.get('bursts', [])

    api_key = beeutil.secrets.get(PLUGIN_NAME, 'BEEMAPS_API_KEY')

    try:
        headers = {'Authorization': f'Bearer {api_key}'}
        res = requests.get(BEEMAPS_API_URL, headers=headers)
        if res.status_code != 200:
            vlog(f'ERROR: Failed to fetch bursts: {res.status_code} {res.text}')
            return state.get('bursts', [])

        data = res.json()
        all_bursts = data.get('bursts', [])

        # Filter for active bee bursts
        active_bursts = []
        for burst in all_bursts:
            if burst.get('disabled', False):
                continue
            if burst.get('deviceType') and burst['deviceType'] != 'bee':
                continue
            valid_until = burst.get('validUntil')
            if valid_until:
                # ISO 8601 date string comparison works for future dates
                from datetime import datetime, timezone
                try:
                    expiry = datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
                    if expiry < datetime.now(timezone.utc):
                        continue
                except (ValueError, AttributeError):
                    pass
            active_bursts.append(burst)

        state['bursts'] = active_bursts
        state['bursts_fetched_at'] = now
        vlog(f'fetched {len(active_bursts)} active bursts (of {len(all_bursts)} total)')
        return active_bursts

    except Exception as e:
        vlog(f'ERROR: Burst fetch failed: {e}')
        return state.get('bursts', [])


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
                filepath = item['filepath']
                burst_id = item['burst_id']
                prefix = f'{state["session"]}/burst-{burst_id}'

                vlog(f'uploading video: {filepath} for burst {burst_id}')
                beeutil.video.upload_video_file(
                    filepath,
                    prefix,
                    beeutil.secrets.get(PLUGIN_NAME, 'AWS_BUCKET'),
                    beeutil.secrets.get(PLUGIN_NAME, 'AWS_REGION'),
                    beeutil.secrets.get(PLUGIN_NAME, 'AWS_SECRET'),
                    beeutil.secrets.get(PLUGIN_NAME, 'AWS_KEY'),
                )
                vlog(f'uploaded: {filepath}')
            except Exception as e:
                vlog(f'ERROR: Upload failed for {item}: {e}')
            finally:
                state['uploadQueue'].task_done()

    for _ in range(UPLOAD_THREADS):
        t = threading.Thread(target=upload_worker, daemon=True)
        t.start()

    # Fetch initial burst geometries
    _fetch_bursts(state)

    vlog('setup complete')


def _loop(state):
    contents = beeutil.list_contents(state['last_checked'])

    if len(contents) == 0:
        vlog(f'no new content since {state["last_checked"]}')
        return

    vlog(f'{len(contents)} new image(s) since {state["last_checked"]}')

    # Get location from most recent image handle
    latest_handle = contents[-1]
    location = beeutil.geo.parse_location_from_handle(latest_handle)

    if location is None:
        vlog(f'could not parse location from handle: {latest_handle}')
        state['last_checked'] = latest_handle.split('_')[0]
        return

    lat, lon = location
    vlog(f'current location: {lat}, {lon}')

    # Refresh burst geometries if stale
    bursts = _fetch_bursts(state)

    if not bursts:
        vlog('no active bursts')
        state['last_checked'] = latest_handle.split('_')[0]
        return

    # Check if inside any burst polygon
    matching_burst = beeutil.geo.point_in_any_burst(lat, lon, bursts)

    if matching_burst is None:
        vlog('not inside any burst area')
        state['last_checked'] = latest_handle.split('_')[0]
        return

    burst_id = matching_burst.get('_id', 'unknown')
    vlog(f'INSIDE BURST {burst_id} — collecting video')

    # List recent video files
    video_files = beeutil.video.list_video_files(state.get('video_checked_at'))

    new_videos = [f for f in video_files if f not in state['processed_videos']]

    if not new_videos:
        vlog('no new video files to upload')
    else:
        vlog(f'queuing {len(new_videos)} video file(s) for upload')
        for filepath in new_videos:
            state['uploadQueue'].put({
                'filepath': filepath,
                'burst_id': burst_id,
            })
            state['processed_videos'].add(filepath)

    state['video_checked_at'] = time.time()
    state['last_checked'] = latest_handle.split('_')[0]


def main():
    state = {
        'last_checked': None,
        'session': '',
        'uploadQueue': None,
        'bursts': [],
        'bursts_fetched_at': None,
        'processed_videos': set(),
        'video_checked_at': None,
    }

    vlog('setting up burst-video plugin')
    _setup(state)

    vlog('initializing run loop')
    while True:
        try:
            _loop(state)
        except Exception as e:
            vlog(f'ERROR in loop: {e}')
        time.sleep(LOOP_DELAY)
