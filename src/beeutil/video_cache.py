import os
import re
from datetime import datetime, timezone

import requests

HOST_URL = 'http://127.0.0.1:5000'
API_ROUTE = f'{HOST_URL}/api/1'
CACHE_ROUTE = f'{HOST_URL}/cache'

VIDEO_DIR = '/tmp/recording/videoCache'
VIDEO_READY_DIR = '/tmp/recording/videoReady'
TAIL_READ_BYTES = 256 * 1024


def list_video_contents(since=None):
  """List ready MP4 video files produced by map-ai.

  Args:
    since: Optional timestamp in ms. Items with availability timestamps at or
      before this value are filtered out.

  Returns:
    List of dicts sorted by availability time ascending. Each item includes:
      filepath, filename, ready_filepath, timestamp_ms, session_id, uptime_ms,
      metadata, and gps_samples.
  """
  if not os.path.isdir(VIDEO_DIR):
    return []

  files = []
  for name in sorted(os.listdir(VIDEO_DIR)):
    if not name.endswith('.mp4'):
      continue

    filepath = os.path.join(VIDEO_DIR, name)
    ready_filepath = os.path.join(VIDEO_READY_DIR, f'{os.path.splitext(name)[0]}.ready')
    if not os.path.isfile(filepath) or not os.path.isfile(ready_filepath):
      continue

    metadata = read_video_metadata(filepath)
    session_id, uptime_ms = _parse_session_and_uptime(name)
    timestamp_ms = _availability_timestamp_ms(filepath, ready_filepath, metadata, uptime_ms)

    if since is not None and timestamp_ms is not None and timestamp_ms <= since:
      continue

    files.append({
      'filepath': filepath,
      'filename': name,
      'ready_filepath': ready_filepath,
      'timestamp_ms': timestamp_ms,
      'session_id': session_id,
      'uptime_ms': uptime_ms,
      'metadata': metadata,
      'gps_samples': metadata.get('gps_samples', []),
    })

  files.sort(key=lambda item: (item['timestamp_ms'] if item['timestamp_ms'] is not None else 0, item['filename']))
  return files


def upload_video_to_s3(prefix, filepath, aws_bucket, aws_region, aws_secret, aws_key):
  """Upload a video file to S3 via the ODC-API cache endpoint."""
  filename = os.path.basename(filepath)
  url = f'{CACHE_ROUTE}/uploadVideoS3/{filename}?prefix={prefix}&key={aws_key}&bucket={aws_bucket}&region={aws_region}'
  headers = {
    'authorization': aws_secret,
  }
  res = requests.post(url, headers=headers)

  if res.status_code != 200:
    raise Exception(res.json())

  print(res.json())


def get_gnss_position():
  """Get the current device GNSS position from the ODC-API."""
  try:
    res = requests.get(f'{API_ROUTE}/gnss', timeout=5)
    if res.status_code != 200:
      return None

    data = res.json()
    lat = data.get('latitude') or data.get('lat')
    lon = data.get('longitude') or data.get('lon')

    if lat is None or lon is None:
      return None

    return {'lat': float(lat), 'lon': float(lon)}
  except Exception:
    return None


def delete_video(filepath, ready_filepath=None):
  """Remove a processed video file and its ready marker."""
  if ready_filepath and os.path.isfile(ready_filepath):
    os.remove(ready_filepath)
  elif ready_filepath is None:
    derived_ready = os.path.join(VIDEO_READY_DIR, f'{os.path.splitext(os.path.basename(filepath))[0]}.ready')
    if os.path.isfile(derived_ready):
      os.remove(derived_ready)

  if os.path.isfile(filepath):
    os.remove(filepath)


def read_video_metadata(filepath):
  """Parse the custom mdta payload appended by the firmware video pipeline."""
  try:
    with open(filepath, 'rb') as handle:
      handle.seek(0, os.SEEK_END)
      size = handle.tell()
      handle.seek(max(0, size - TAIL_READ_BYTES))
      tail = handle.read()
  except OSError:
    return {'pairs': [], 'gps_samples': [], 'imu_samples': []}

  pairs = _parse_tail_metadata_pairs(tail)
  return {
    'pairs': pairs,
    'gps_samples': _merge_gps_samples(pairs),
    'imu_samples': _merge_imu_samples(pairs),
  }


def _availability_timestamp_ms(filepath, ready_filepath, metadata, uptime_ms):
  gps_samples = metadata.get('gps_samples', [])
  gps_times = [
    sample['timestamp_ms']
    for sample in gps_samples
    if sample.get('timestamp_ms') is not None
  ]
  if gps_times:
    return min(gps_times)

  if uptime_ms is not None:
    return uptime_ms

  try:
    return int(os.path.getmtime(ready_filepath) * 1000)
  except OSError:
    try:
      return int(os.path.getmtime(filepath) * 1000)
    except OSError:
      return None


def _parse_session_and_uptime(filename):
  stem = os.path.splitext(filename)[0]

  if stem.isdigit():
    return None, int(stem)

  unknown_match = re.match(r'UNKNOWN_(.+)_uptime_ms_(\d+)$', stem)
  if unknown_match:
    return unknown_match.group(1), int(unknown_match.group(2))

  session_match = re.match(r'(.+)_(\d+)$', stem)
  if session_match:
    return session_match.group(1), int(session_match.group(2))

  return None, None


def _parse_tail_metadata_pairs(tail):
  keys_index = tail.rfind(b'keys')
  ilst_index = tail.rfind(b'ilst')
  if keys_index < 4 or ilst_index < 4:
    return []

  try:
    key_count = int.from_bytes(tail[keys_index + 8:keys_index + 12], 'big')
    cursor = keys_index + 12
    keys = []
    for _ in range(key_count):
      entry_size = int.from_bytes(tail[cursor:cursor + 4], 'big')
      if entry_size < 4:
        return []
      entry_end = cursor + entry_size
      keys.append(tail[cursor + 4:entry_end].decode('utf-8', errors='replace'))
      cursor = entry_end

    list_size = int.from_bytes(tail[ilst_index - 4:ilst_index], 'big')
    list_end = min(len(tail), ilst_index - 4 + list_size)
    cursor = ilst_index + 4
    pairs = []
    while cursor + 24 <= list_end:
      item_size = int.from_bytes(tail[cursor:cursor + 4], 'big')
      if item_size < 24:
        break
      item_end = min(cursor + item_size, list_end)
      key_index = int.from_bytes(tail[cursor + 4:cursor + 8], 'big')
      data_size = int.from_bytes(tail[cursor + 8:cursor + 12], 'big')
      value_start = cursor + 24
      value_end = min(cursor + 8 + data_size, item_end)
      if value_start > value_end:
        break
      key_name = keys[key_index - 1] if 0 < key_index <= len(keys) else f'unknown_{key_index}'
      value = tail[value_start:value_end].decode('utf-8', errors='replace')
      pairs.append((key_name, value))
      cursor = item_end

    return pairs
  except Exception:
    return []


def _merge_gps_samples(pairs):
  samples = []
  current = None

  for key, value in pairs:
    if key == 'mdtaDate/Time':
      if current is not None:
        samples.append(_normalize_gps_sample(current))
      current = {
        'time': _nullify(value),
        'sample_time': None,
        'lat': None,
        'lon': None,
        'speed_kmh': None,
      }
    elif key == 'mdtaSampleTime':
      current = current or {
        'time': None,
        'sample_time': None,
        'lat': None,
        'lon': None,
        'speed_kmh': None,
      }
      current['sample_time'] = _nullify(value)
    elif key == 'mdtaGPSLatitude':
      current = current or {
        'time': None,
        'sample_time': None,
        'lat': None,
        'lon': None,
        'speed_kmh': None,
      }
      current['lat'] = _parse_float(value)
    elif key == 'mdtaGPSLongitude':
      current = current or {
        'time': None,
        'sample_time': None,
        'lat': None,
        'lon': None,
        'speed_kmh': None,
      }
      current['lon'] = _parse_float(value)
    elif key == 'mdtaGPSSpeed':
      current = current or {
        'time': None,
        'sample_time': None,
        'lat': None,
        'lon': None,
        'speed_kmh': None,
      }
      current['speed_kmh'] = _parse_float(value)
    elif key == 'mdtaGPSSpeedRef' and current is not None:
      samples.append(_normalize_gps_sample(current))
      current = None

  if current is not None:
    samples.append(_normalize_gps_sample(current))

  return [sample for sample in samples if sample.get('lat') is not None and sample.get('lon') is not None]


def _merge_imu_samples(pairs):
  samples = []
  current = None

  for key, value in pairs:
    if key == 'mdtaTimeCode':
      if current is not None:
        samples.append(current)
      current = {
        'time': _nullify(value),
        'accelerometer': None,
      }
    elif key == 'mdtaAccelerometer':
      current = current or {
        'time': None,
        'accelerometer': None,
      }
      accel = _nullify(value)
      current['accelerometer'] = accel
      samples.append(current)
      current = None

  if current is not None:
    samples.append(current)

  return samples


def _normalize_gps_sample(sample):
  normalized = dict(sample)
  normalized['timestamp_ms'] = _parse_datetime_ms(sample.get('sample_time') or sample.get('time'))
  return normalized


def _parse_float(value):
  value = _nullify(value)
  if value is None:
    return None
  try:
    return float(value)
  except (TypeError, ValueError):
    return None


def _nullify(value):
  if value in (None, '', 'None'):
    return None
  return value


def _parse_datetime_ms(value):
  value = _nullify(value)
  if value is None:
    return None

  if isinstance(value, str) and value.isdigit():
    return int(value)

  for candidate in (
    str(value).replace(' ', 'T'),
    str(value),
  ):
    try:
      dt = datetime.fromisoformat(candidate)
      if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
      return int(dt.timestamp() * 1000)
    except ValueError:
      continue

  return None
