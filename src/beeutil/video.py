import os
import time

VIDEO_DIR = '/data/video/'


def list_video_files(since_ts=None):
    """List video files from the device video directory.

    Args:
        since_ts: Optional unix timestamp (seconds). Only return files
                  modified after this time.

    Returns list of absolute file paths sorted by modification time.
    """
    if not os.path.isdir(VIDEO_DIR):
        return []

    files = []
    for name in os.listdir(VIDEO_DIR):
        if not name.endswith('.mp4'):
            continue
        path = os.path.join(VIDEO_DIR, name)
        mtime = os.path.getmtime(path)
        if since_ts is not None and mtime < since_ts:
            continue
        files.append((mtime, path))

    files.sort()
    return [path for _, path in files]


def upload_video_file(filepath, prefix, aws_bucket, aws_region, aws_secret, aws_key):
    """Upload a video file to S3 via the ODC API proxy.

    Uses the same cache upload endpoint pattern as image uploads,
    passing the video file path for the device-side upload handler.

    Args:
        filepath: Absolute path to the video file on device
        prefix: S3 key prefix (e.g. session ID or burst ID)
        aws_bucket: S3 bucket name
        aws_region: AWS region
        aws_secret: AWS secret access key
        aws_key: AWS access key ID
    """
    import requests

    filename = os.path.basename(filepath)
    host_url = 'http://127.0.0.1:5000'
    url = f'{host_url}/cache/uploadS3/{filename}?prefix={prefix}&key={aws_key}&bucket={aws_bucket}&region={aws_region}&source=video'

    headers = {
        'authorization': aws_secret,
    }

    res = requests.post(url, headers=headers)
    if res.status_code != 200:
        raise Exception(f'Video upload failed for {filename}: {res.text}')

    return res.json()
