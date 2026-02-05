import math
import pytz
from timezonefinder import TimezoneFinder


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def haversine_with_stationary_detection(lat1, lon1, lat2, lon2, stationary_threshold=10):
    distance_km = haversine(lat1, lon1, lat2, lon2)
    distance_meters = distance_km * 1000
    if distance_meters < stationary_threshold:
        return 0.0
    return distance_km


def find_movement_boundaries(points, stationary_threshold=10):
    if len(points) < 2:
        return None, None

    movement_start_idx = None
    movement_end_idx = None

    for i in range(1, len(points)):
        prev_point = points[i - 1]
        curr_point = points[i]
        distance_meters = haversine(prev_point["lat"], prev_point["lon"],
                                    curr_point["lat"], curr_point["lon"]) * 1000
        if distance_meters >= stationary_threshold:
            movement_start_idx = i - 1
            break

    for i in range(len(points) - 1, 0, -1):
        prev_point = points[i - 1]
        curr_point = points[i]
        distance_meters = haversine(prev_point["lat"], prev_point["lon"],
                                    curr_point["lat"], curr_point["lon"]) * 1000
        if distance_meters >= stationary_threshold:
            movement_end_idx = i
            break

    return movement_start_idx, movement_end_idx


def detect_stationary_gap(points, gap_threshold_seconds, stationary_threshold_meters):
    if len(points) < 2:
        return 0

    stationary_start_idx = len(points) - 1

    for i in range(len(points) - 1, 0, -1):
        prev_point = points[i - 1]
        curr_point = points[i]
        distance_meters = haversine(prev_point["lat"], prev_point["lon"],
                                    curr_point["lat"], curr_point["lon"]) * 1000
        if distance_meters >= stationary_threshold_meters:
            break
        else:
            stationary_start_idx = i - 1

    if stationary_start_idx < len(points) - 1:
        return points[-1]['tst'] - points[stationary_start_idx]['tst']

    return 0


def get_timezone_from_gps(lat, lon):
    tf = TimezoneFinder()
    timezone_str = tf.timezone_at(lat=lat, lng=lon)
    if timezone_str:
        return pytz.timezone(timezone_str)
    return pytz.UTC


def format_time(seconds_input):
    days, remainder = divmod(seconds_input, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs_component = divmod(remainder, 60)
    return f"{int(days):02d}:{int(hours):02d}:{int(minutes):02d}:{int(secs_component):02d}"
