def parse_location_from_handle(handle):
    """Extract lat/lon from image cache handle string.

    Handle format: {timestamp}_{lat}_{lon}
    Returns (lat, lon) tuple or None if parsing fails.
    """
    parts = handle.split('_')
    if len(parts) < 3:
        return None
    try:
        lat = float(parts[1])
        lon = float(parts[2])
        return (lat, lon)
    except (ValueError, IndexError):
        return None


def point_in_polygon(lat, lon, polygon_coords):
    """Ray-casting point-in-polygon test.

    Args:
        lat: Latitude of point
        lon: Longitude of point
        polygon_coords: GeoJSON polygon coordinates (list of rings).
                        Each ring is a list of [lon, lat] pairs.
                        First ring is exterior, rest are holes.

    Returns True if point is inside the polygon.
    """
    if not polygon_coords or not polygon_coords[0]:
        return False

    # Check exterior ring
    ring = polygon_coords[0]
    if not _point_in_ring(lat, lon, ring):
        return False

    # Check holes (interior rings) — point must NOT be in any hole
    for hole in polygon_coords[1:]:
        if _point_in_ring(lat, lon, hole):
            return False

    return True


def _point_in_ring(lat, lon, ring):
    """Ray-casting algorithm for a single ring.

    Ring is a list of [lon, lat] pairs (GeoJSON order).
    """
    n = len(ring)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]  # lon, lat
        xj, yj = ring[j][0], ring[j][1]

        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i

    return inside


def point_in_any_burst(lat, lon, bursts):
    """Check if a point is inside any active burst geometry.

    Args:
        lat: Latitude of point
        lon: Longitude of point
        bursts: List of burst dicts with 'geojson' field containing
                GeoJSON Polygon or MultiPolygon geometry.

    Returns the first matching burst dict, or None.
    """
    for burst in bursts:
        geojson = burst.get('geojson', {})
        geo_type = geojson.get('type', '')
        coords = geojson.get('coordinates', [])

        if geo_type == 'Polygon':
            if point_in_polygon(lat, lon, coords):
                return burst
        elif geo_type == 'MultiPolygon':
            for polygon_coords in coords:
                if point_in_polygon(lat, lon, polygon_coords):
                    return burst

    return None
