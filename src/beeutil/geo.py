import requests

BEEMAPS_API_BASE = 'https://hivemapper.com/api/developer'
ODC_API_BASE = 'http://127.0.0.1:5000/api/1'
DEFAULT_BURST_RADIUS_M = 10000

def point_in_polygon(lat, lon, polygon_coords):
  """Check if a point is inside a polygon using ray casting.

  Args:
    lat: Latitude of the point.
    lon: Longitude of the point.
    polygon_coords: List of rings, where each ring is a list of [lon, lat]
                    pairs (GeoJSON format). First ring is exterior, rest are holes.

  Returns:
    True if the point is inside the polygon.
  """
  if not polygon_coords:
    return False

  exterior = polygon_coords[0]
  if not _point_in_ring(lat, lon, exterior):
    return False

  for hole in polygon_coords[1:]:
    if _point_in_ring(lat, lon, hole):
      return False

  return True


def point_in_multipolygon(lat, lon, multipolygon_coords):
  """Check if a point is inside any polygon of a MultiPolygon.

  Args:
    lat: Latitude of the point.
    lon: Longitude of the point.
    multipolygon_coords: List of polygon coordinate arrays.

  Returns:
    True if the point is inside any polygon.
  """
  for polygon_coords in multipolygon_coords:
    if point_in_polygon(lat, lon, polygon_coords):
      return True
  return False


def point_in_geojson(lat, lon, geojson):
  """Check if a point is within a GeoJSON geometry.

  Args:
    lat: Latitude of the point.
    lon: Longitude of the point.
    geojson: Dict with 'type' and 'coordinates' keys.

  Returns:
    True if the point is inside the geometry.
  """
  geom_type = geojson.get('type')
  coords = geojson.get('coordinates')

  if geom_type == 'Polygon':
    return point_in_polygon(lat, lon, coords)
  elif geom_type == 'MultiPolygon':
    return point_in_multipolygon(lat, lon, coords)

  return False


def fetch_active_bursts(api_key, limit=100):
  """Fetch active burst geometries from the Beemaps API.

  Args:
    api_key: Beemaps developer API key.
    limit: Maximum number of bursts to fetch.

  Returns:
    List of burst dicts with 'id', 'geojson', 'isHit', etc.
  """
  url = f'{BEEMAPS_API_BASE}/bursts'
  headers = {
    'Authorization': f'Basic {api_key}',
  }
  params = {
    'limit': limit,
  }

  res = requests.get(url, headers=headers, params=params, timeout=15)
  if res.status_code != 200:
    raise Exception(f'Failed to fetch bursts: {res.status_code} {res.text}')

  data = res.json()
  bursts = data if isinstance(data, list) else data.get('bursts', [])
  return [b for b in bursts if not b.get('isHit', False)]


def fetch_nearby_burst(lat, lon, radius_m=DEFAULT_BURST_RADIUS_M):
  """Fetch the nearest burst for a coordinate from the local ODC API.

  The endpoint is assumed to exist and may return either:
    - a burst object
    - {'burst': {...}}
    - {'data': {...}}
    - {'bursts': [{...}, ...]}

  Args:
    lat: Latitude of the point.
    lon: Longitude of the point.

  Returns:
    A burst dict if one is found, otherwise None.
  """
  url = f'{ODC_API_BASE}/bursts/near'
  params = {
    'lat': lat,
    'lon': lon,
    'radius_m': radius_m,
  }

  res = requests.get(url, params=params, timeout=10)
  if res.status_code == 404:
    return None
  if res.status_code != 200:
    raise Exception(f'Failed to fetch nearby burst: {res.status_code} {res.text}')

  data = res.json()
  if isinstance(data, list):
    return data[0] if data else None
  if not isinstance(data, dict):
    return None
  if isinstance(data.get('burst'), dict):
    return data['burst']
  if isinstance(data.get('data'), dict):
    return data['data']
  bursts = data.get('bursts')
  if isinstance(bursts, list) and bursts:
    return bursts[0]
  if 'id' in data:
    return data
  return None


def fetch_nearby_bursts(lat, lon, radius_m=DEFAULT_BURST_RADIUS_M):
  """Fetch bursts near a coordinate from the local ODC API.

  The endpoint is assumed to exist and may return either:
    - a list of burst objects
    - {'bursts': [{...}, ...]}
    - {'data': [{...}, ...]}
    - a single burst object

  Args:
    lat: Latitude of the point.
    lon: Longitude of the point.

  Returns:
    List of burst dicts.
  """
  url = f'{ODC_API_BASE}/bursts/near'
  params = {
    'lat': lat,
    'lon': lon,
    'radius_m': radius_m,
  }

  res = requests.get(url, params=params, timeout=10)
  if res.status_code == 404:
    return []
  if res.status_code != 200:
    raise Exception(f'Failed to fetch nearby bursts: {res.status_code} {res.text}')

  data = res.json()
  if isinstance(data, list):
    return [item for item in data if isinstance(item, dict)]
  if not isinstance(data, dict):
    return []

  bursts = data.get('bursts')
  if isinstance(bursts, list):
    return [item for item in bursts if isinstance(item, dict)]

  payload = data.get('data')
  if isinstance(payload, list):
    return [item for item in payload if isinstance(item, dict)]
  if isinstance(payload, dict):
    return [payload]

  burst = data.get('burst')
  if isinstance(burst, dict):
    return [burst]
  if 'id' in data:
    return [data]
  return []


def _point_in_ring(lat, lon, ring):
  """Ray casting algorithm for point-in-ring test.

  Args:
    lat: Latitude of the point.
    lon: Longitude of the point.
    ring: List of [lon, lat] pairs (GeoJSON coordinate order).

  Returns:
    True if the point is inside the ring.
  """
  n = len(ring)
  inside = False

  j = n - 1
  for i in range(n):
    xi, yi = ring[i][0], ring[i][1]  # lon, lat
    xj, yj = ring[j][0], ring[j][1]

    if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
      inside = not inside

    j = i

  return inside
