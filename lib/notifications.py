"""
Push notifications via Pushcut webhook.

Sends iPhone notifications when ride transitions are detected.
Used by the push worker process, not by the Flask app.
"""
import time
import requests
from datetime import datetime

import pytz

import config
from lib.geo import calculate_track_distance, detect_stationary_gap


# Events older than this are considered historical and suppressed
HISTORICAL_THRESHOLD_SECONDS = 600  # 10 minutes

# Stationary duration to consider a walking/other ride ended
OTHER_STATIONARY_END_SECONDS = 1200  # 20 minutes

# Marker activity types
MARKER_TYPES = {
    'car_start': 'Car', 'car_end': 'Car',
    'bike_start': 'Bike', 'bike_end': 'Bike',
}


def send_pushcut_notification(title, text):
    """Send a push notification via Pushcut webhook.

    Returns True if sent successfully, False otherwise.
    Never raises — all exceptions are caught and logged.
    """
    url = config.PUSHCUT_WEBHOOK_URL
    if not url:
        return False

    try:
        response = requests.post(url, json={
            'title': title,
            'text': text,
            'isTimeSensitive': True
        }, timeout=5)
        if response.ok:
            print(f"[PUSHCUT] Sent: {title} — {text}", flush=True)
            return True
        else:
            print(f"[PUSHCUT] HTTP {response.status_code}: {title}", flush=True)
            return False
    except Exception as e:
        print(f"[PUSHCUT] Error sending '{title}': {e}", flush=True)
        return False


def format_ride_end_text(ride, detected_tz):
    """Format ride stats for notification body.

    Returns string like: "12.5 km | 35m | 21.4 km/h | 14:32-15:07"
    """
    distance = calculate_track_distance(ride['points'])
    duration = ride['end'] - ride['start']
    avg_speed = (distance / duration * 3600) if duration > 0 else 0

    duration_min = int(duration / 60)
    if duration_min >= 60:
        hours = duration_min // 60
        mins = duration_min % 60
        duration_str = f"{hours}h {mins}m"
    else:
        duration_str = f"{duration_min}m"

    start_local = datetime.fromtimestamp(ride['start'], tz=pytz.UTC).astimezone(detected_tz)
    end_local = datetime.fromtimestamp(ride['end'], tz=pytz.UTC).astimezone(detected_tz)

    return (f"{distance:.1f} km | {duration_str} | {avg_speed:.1f} km/h | "
            f"{start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')}")


def check_and_notify_markers(raw_data, seen_markers, activities, detected_tz):
    """Scan raw data for new car/bike markers and send notifications.

    Detects car_start, car_end, bike_start, bike_end markers directly from
    raw data (markers injected by Node-RED). Much faster than waiting for parse_activities() to
    validate rides with 5+ GPS points.

    Returns (updated_seen_markers, state_changed).
    """
    now = int(time.time())
    new_seen = set(seen_markers)
    state_changed = False

    # Collect car/bike markers from raw data, sorted by timestamp
    markers = []
    for item in raw_data:
        if item.get('_type') == 'lwt' and item.get('custom') is True:
            activity = item.get('activity', '')
            if activity in MARKER_TYPES:
                markers.append(item)
    markers.sort(key=lambda x: x['tst'])

    for marker in markers:
        activity = marker['activity']
        tst = marker['tst']
        ride_type = activity.split('_')[0]  # 'car' or 'bike'
        name = MARKER_TYPES[activity]

        # Skip already-seen markers
        if tst in new_seen:
            continue
        new_seen.add(tst)
        state_changed = True

        # Historical event suppression
        age = now - tst
        if age > HISTORICAL_THRESHOLD_SECONDS:
            print(f"[PUSH-WORKER] Suppressed: {name} marker at {tst} — "
                  f"{age // 60}m ago — historical event", flush=True)
            continue

        # Ride numbering from validated activities (matches map app)
        rides = activities.get(ride_type, [])

        if activity.endswith('_start'):
            # Ride may not be validated yet (< 5 GPS points), so next number
            ride_number = len(rides) + 1
            start_local = datetime.fromtimestamp(
                tst, tz=pytz.UTC).astimezone(detected_tz)
            send_pushcut_notification(
                f"{name} Ride {ride_number} Started",
                f"Started at {start_local.strftime('%H:%M')}")

        elif activity.endswith('_end'):
            # Find matching ride by end timestamp for stats and numbering
            ride = None
            for idx, r in enumerate(rides):
                if abs(r['end'] - tst) < 5:
                    ride = r
                    ride_number = idx + 1
                    break
            else:
                ride_number = len(rides)

            if ride and ride.get('points'):
                send_pushcut_notification(
                    f"{name} Ride {ride_number} Ended",
                    format_ride_end_text(ride, detected_tz))
            else:
                end_local = datetime.fromtimestamp(
                    tst, tz=pytz.UTC).astimezone(detected_tz)
                send_pushcut_notification(
                    f"{name} Ride {ride_number} Ended",
                    f"Ended at {end_local.strftime('%H:%M')}")

    return new_seen, state_changed


def _is_other_ride_active(ride, last_gps_timestamp):
    """Check if a walking/other ride is still accumulating GPS points.

    Walking rides have no markers. Instead, check if the ride's points
    array still includes the latest GPS data. The points array contains
    all GPS points (including stationary trailing ones), even though
    ride['end'] is trimmed back to the last movement point by
    find_movement_boundaries().
    """
    if not ride.get('points'):
        return False
    return abs(ride['points'][-1]['tst'] - last_gps_timestamp) < 120


def is_other_ride_ended(ride):
    """Check if a walking/other ride has ended (user stationary for 5+ min).

    Uses detect_stationary_gap() on the ride's points to measure how long
    the trailing GPS points have been stationary (< 10m between consecutive
    points). Returns True if stationary for >= 5 minutes.
    """
    points = ride.get('points', [])
    if len(points) < 2:
        return False
    stationary = detect_stationary_gap(
        points, OTHER_STATIONARY_END_SECONDS, 10)
    return stationary >= OTHER_STATIONARY_END_SECONDS


def check_and_notify_other_transitions(prev_count, new_count, activities,
                                       detected_tz, last_gps_timestamp):
    """Handle walking/other ride count changes.

    Walking rides have no markers, so transitions are detected from
    parse_activities() count changes:
    - Count increase + ride is active (points include latest GPS): Started
    - Count increase + ride is not active (segment was split): Ended

    "Ended" for active walking rides is handled separately by the worker
    via stationary gap check (check_and_notify_other_ride_end).
    """
    if new_count <= prev_count:
        return

    now = int(time.time())
    rides = activities.get('other', [])
    ride = rides[-1] if rides else None
    if not ride:
        return

    ride_number = new_count

    if _is_other_ride_active(ride, last_gps_timestamp):
        # Currently walking — send "Started"
        event_timestamp = ride['start']
        age = now - event_timestamp

        if age > HISTORICAL_THRESHOLD_SECONDS:
            print(f"[PUSH-WORKER] Suppressed: Walking Ride {ride_number} "
                  f"started {age // 60}m ago — historical event", flush=True)
            return

        start_local = datetime.fromtimestamp(
            ride['start'], tz=pytz.UTC).astimezone(detected_tz)
        send_pushcut_notification(
            f"Walking Ride {ride_number} Started",
            f"Started at {start_local.strftime('%H:%M')}")
    else:
        # Completed segment appeared (split from previous) — send "Ended"
        event_timestamp = ride['end']
        age = now - event_timestamp

        if age > HISTORICAL_THRESHOLD_SECONDS:
            print(f"[PUSH-WORKER] Suppressed: Walking Ride {ride_number} "
                  f"ended {age // 60}m ago — historical event", flush=True)
            return

        send_pushcut_notification(
            f"Walking Ride {ride_number} Ended",
            format_ride_end_text(ride, detected_tz))


def check_and_notify_other_ride_end(ride, ride_number, detected_tz):
    """Check if a walking/other ride has ended and send notification.

    Called by the worker on every poll for active walking rides that haven't
    had their "Ended" notification sent yet. Uses detect_stationary_gap()
    to check if the user has been stationary for 5+ minutes.

    Returns True if the ride is considered ended (notification sent or
    suppressed as historical), False if still in progress.
    """
    if not is_other_ride_ended(ride):
        return False

    now = int(time.time())
    event_timestamp = ride['end']
    age = now - event_timestamp

    if age > HISTORICAL_THRESHOLD_SECONDS:
        print(f"[PUSH-WORKER] Suppressed: Walking Ride {ride_number} "
              f"ended {age // 60}m ago — historical event", flush=True)
        return True

    send_pushcut_notification(
        f"Walking Ride {ride_number} Ended",
        format_ride_end_text(ride, detected_tz))
    return True
