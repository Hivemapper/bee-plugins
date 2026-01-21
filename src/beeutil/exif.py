import csv
import json
import os
import subprocess
import time

from collections import deque

class BatchEXIFWriter:
  q = deque()

  def __init__(self, img_dir, verbose=False):
    self.img_dir = img_dir

  def flush(self):
    if self.verbose:
      print(f'flushing exif queue for {self.size()} elts...')
    data = []
    fields = set()
    for i in range(self.size()):
      d = self.q.popleft()
      data.append(d)
      fields.update(d.keys())

    header = list(fields)
    rows = [[d.get(k) for k in header] for d in data]

    csv_path = f"{time.monotonic().replace('.', '_')}.csv"
    with open(csv_path, 'w', newline='') as file:
      writer = csv.writer(file)
      writer.writerows([header] + rows)

    try:
      cmd = ['exiftool', f'-csv="{csv_path}"', '-overwrite_original', self.img_dir]
      res = subprocess.run(
        cmd,
        capture_output=not self.verbose,
        text=not self.verbose,
        check=True)

      if self.verbose:
        print(res.stdout)

    except Exception as e:
      print(e)
      for d in data:
        self.q.appendLeft(d)

  def add(self, img_file, tags):
    if os.path.exists(os.path.join(self.img_dir, img_file)):
      d = {**tags, 'SourceFile': img_file}
      self.q.append(d)

  def size(self):
    return len(self.q)

def metadata_to_exif_tags(metadata_file):
  with open(os.path.join(self.img_dir, metadata_file), 'r', encoding='utf-8') as file:
    data = json.load(file)

    tags = {}

    tags['GPSLatitude'] = data['lat']
    tags['GPSLatitudeRef'] = 'N'
    tags['GPSLongitude'] = data['lon']
    tags['GPSLongitudeRef'] = 'E'
    tags['SubSecDateTimeOriginal'] = data['time']
    tags['GPSSpeed'] = data.get('speed') * 3.6 # mps to kmh
    tags['GPSSpeedRef'] = 'K'

    return tags
