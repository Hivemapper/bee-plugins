import importlib.util
from pathlib import Path

VIDEO_CACHE_PATH = Path(__file__).resolve().parents[1] / 'src' / 'beeutil' / 'video_cache.py'
SPEC = importlib.util.spec_from_file_location('video_cache', VIDEO_CACHE_PATH)
video_cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(video_cache)


def _build_metadata_tail(pairs):
  key_names = []
  for key, _ in pairs:
    if key not in key_names:
      key_names.append(key)

  key_entries = b''.join(
    (len(name.encode()) + 4).to_bytes(4, 'big') + name.encode()
    for name in key_names
  )
  keys_atom = (
    (16 + len(key_entries)).to_bytes(4, 'big')
    + b'keys'
    + b'\x00\x00\x00\x00'
    + len(key_names).to_bytes(4, 'big')
    + key_entries
  )

  items = b''
  for key, value in pairs:
    encoded = value.encode()
    data_atom_size = 16 + len(encoded)
    item_size = 24 + len(encoded)
    items += (
      item_size.to_bytes(4, 'big')
      + (key_names.index(key) + 1).to_bytes(4, 'big')
      + data_atom_size.to_bytes(4, 'big')
      + b'data'
      + b'\x00\x00\x00\x01'
      + b'\x00\x00\x00\x00'
      + encoded
    )

  ilst_atom = (8 + len(items)).to_bytes(4, 'big') + b'ilst' + items
  meta_payload = (
    b'\x00\x00\x00\x00'
    + b'\x00\x00\x00\x21hdlr'
    + b'\x00\x00\x00\x00'
    + b'\x00\x00\x00\x00'
    + b'mdta'
    + b'\x00\x00\x00\x00'
    + b'\x00\x00\x00\x00'
    + b'\x00\x00\x00\x00\x00'
    + keys_atom
    + ilst_atom
  )
  return len(meta_payload + b'meta').to_bytes(4, 'big') + b'meta' + meta_payload


def test_read_video_metadata_parses_gps_samples(tmp_path):
  video_path = tmp_path / 'session_12345.mp4'
  pairs = [
    ('mdtaDate/Time', '2026-03-13 10:15:00'),
    ('mdtaSampleTime', '2026-03-13 10:15:00'),
    ('mdtaGPSLatitude', '37.1234'),
    ('mdtaGPSLongitude', '-122.4321'),
    ('mdtaGPSSpeed', '42.5'),
    ('mdtaGPSSpeedRef', 'km/h'),
    ('mdtaTimeCode', '2026-03-13 10:15:00'),
    ('mdtaAccelerometer', '0.1 0.2 0.3'),
  ]
  video_path.write_bytes(b'fake-mp4-prefix' + _build_metadata_tail(pairs))

  metadata = video_cache.read_video_metadata(str(video_path))

  assert len(metadata['gps_samples']) == 1
  assert metadata['gps_samples'][0]['lat'] == 37.1234
  assert metadata['gps_samples'][0]['lon'] == -122.4321
  assert metadata['gps_samples'][0]['speed_kmh'] == 42.5
  assert metadata['gps_samples'][0]['timestamp_ms'] is not None
  assert metadata['imu_samples'][0]['accelerometer'] == '0.1 0.2 0.3'


def test_list_video_contents_only_returns_ready_files(tmp_path, monkeypatch):
  video_dir = tmp_path / 'videoCache'
  ready_dir = tmp_path / 'videoReady'
  video_dir.mkdir()
  ready_dir.mkdir()

  ready_video = video_dir / 'session_555.mp4'
  ready_video.write_bytes(b'video')
  (ready_dir / 'session_555.ready').write_text('')

  not_ready_video = video_dir / 'session_999.mp4'
  not_ready_video.write_bytes(b'video')

  monkeypatch.setattr(video_cache, 'VIDEO_DIR', str(video_dir))
  monkeypatch.setattr(video_cache, 'VIDEO_READY_DIR', str(ready_dir))

  videos = video_cache.list_video_contents()

  assert [video['filename'] for video in videos] == ['session_555.mp4']
  assert videos[0]['ready_filepath'] == str(ready_dir / 'session_555.ready')
  assert videos[0]['uptime_ms'] == 555
