import os
import re
import requests

HOST_URL = 'http://127.0.0.1:5000'
API_ROUTE = f'{HOST_URL}/api/1'
CACHE_ROUTE = f'{HOST_URL}/cache'

VIDEO_DIR = '/data/video'

def list_video_contents(since=None):
  """List MP4 video files in the video cache directory.

  Args:
    since: Optional timestamp (ms) - only return files newer than this.

  Returns:
    List of dicts with 'filepath', 'filename', 'timestamp_ms' keys,
    sorted by timestamp ascending.
  """
  if not os.path.isdir(VIDEO_DIR):
    return []

  files = []
  for name in os.listdir(VIDEO_DIR):
    if not name.endswith('.mp4'):
      continue

    filepath = os.path.join(VIDEO_DIR, name)
    timestamp_ms = _parse_timestamp_from_filename(name)

    if since is not None and timestamp_ms is not None and timestamp_ms <= since:
      continue

    files.append({
      'filepath': filepath,
      'filename': name,
      'timestamp_ms': timestamp_ms,
    })

  files.sort(key=lambda f: f['timestamp_ms'] or 0)
  return files


def upload_video_to_s3(prefix, filepath, aws_bucket, aws_region, aws_secret, aws_key):
  """Upload a video file to S3 via the ODC-API cache endpoint.

  Args:
    prefix: S3 key prefix (e.g. session ID or burst ID).
    filepath: Local path to the video file.
    aws_bucket: S3 bucket name.
    aws_region: AWS region.
    aws_secret: AWS secret access key.
    aws_key: AWS access key ID.
  """
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
  """Get the current device GNSS position from the ODC-API.

  Returns:
    Dict with 'lat' and 'lon' keys, or None if unavailable.
  """
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


def delete_video(filepath):
  """Remove a video file from the cache.

  Args:
    filepath: Full path to the video file to delete.
  """
  if os.path.isfile(filepath):
    os.remove(filepath)


def _parse_timestamp_from_filename(filename):
  """Extract timestamp_ms from video filename.

  Supports formats:
    - {timestamp_ms}.mp4
    - UNKNOWN_{session_id}_uptime_ms_{uptime_ms}.mp4
  """
  name = filename.replace('.mp4', '')

  if name.isdigit():
    return int(name)

  match = re.match(r'UNKNOWN_[^_]+_uptime_ms_(\d+)', name)
  if match:
    return int(match.group(1))

  return None
