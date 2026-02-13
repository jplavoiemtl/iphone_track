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
OTHER_STATIONARY_END_SECONDS = 300  # 5 minutes


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


def _is_ride_open(ride, last_gps_timestamp):
    """Check if a car/bike ride is still open (end matches the last GPS point).

    Open rides have their end set to the last GPS point's timestamp by
    parse_activities(). Closed rides have an explicit end marker timestamp
    that is well before the latest GPS data.

    Only valid for car/bike rides (marker-based). Walking/other rides use
    _is_other_ride_active() and _is_other_ride_ended() instead.
    """
    return abs(ride['end'] - last_gps_timestamp) < 10


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


def check_and_notify_ride_transitions(prev_counts, new_counts, prev_ends,
                                      new_ends, activities, detected_tz,
                                      last_gps_timestamp):
    """Compare ride snapshots and send notifications for recent transitions.

    Car/bike (marker-based):
    - Count increase + ride is open (end ≈ last GPS point): ride just started
    - Count increase + ride is closed (end < last GPS point): ride appeared complete
    - Same count + ride was open but is now closed: ride got its end marker

    Walking/other (count changes only — "Ended" handled separately by worker):
    - Count increase + ride is active (points include latest GPS): ride started
    - Count increase + ride is not active (segment was split): ride ended

    Events older than 10 minutes (wall clock) are suppressed as historical.

    Returns the updated prev_ends dict. For rides that were skipped (still
    open), the old prev_end value is preserved so ends_changed will fire
    again on the next poll.
    """
    now = int(time.time())
    activity_names = {'car': 'Car', 'bike': 'Bike', 'other': 'Walking'}
    updated_ends = dict(prev_ends)

    for activity_type in ['car', 'bike', 'other']:
        prev_count = prev_counts.get(activity_type, 0)
        new_count = new_counts.get(activity_type, 0)
        name = activity_names[activity_type]

        rides = activities.get(activity_type, [])

        # Walking/other rides: no markers, different detection logic
        if activity_type == 'other':
            updated_ends['other'] = new_ends.get('other', 0)
            if new_count > prev_count:
                ride = rides[-1] if rides else None
                if not ride:
                    continue

                ride_number = new_count

                if _is_other_ride_active(ride, last_gps_timestamp):
                    # Currently walking — send "Started"
                    event_timestamp = ride['start']
                    age = now - event_timestamp

                    if age > HISTORICAL_THRESHOLD_SECONDS:
                        print(f"[PUSH-WORKER] Suppressed: {name} Ride {ride_number} "
                              f"started {age // 60}m ago — historical event", flush=True)
                        continue

                    start_local = datetime.fromtimestamp(
                        ride['start'], tz=pytz.UTC).astimezone(detected_tz)
                    send_pushcut_notification(
                        f"{name} Ride {ride_number} Started",
                        f"Started at {start_local.strftime('%H:%M')}")
                else:
                    # Completed segment appeared (split from previous) — send "Ended"
                    event_timestamp = ride['end']
                    age = now - event_timestamp

                    if age > HISTORICAL_THRESHOLD_SECONDS:
                        print(f"[PUSH-WORKER] Suppressed: {name} Ride {ride_number} "
                              f"ended {age // 60}m ago — historical event", flush=True)
                        continue

                    send_pushcut_notification(
                        f"{name} Ride {ride_number} Ended",
                        format_ride_end_text(ride, detected_tz))

            # "Ended" for active walking rides is handled by the worker
            # via stationary gap check (check_and_notify_other_ride_end)
            continue

        # Car/bike: marker-based detection
        prev_end = prev_ends.get(activity_type, 0)
        new_end = new_ends.get(activity_type, 0)

        if new_count > prev_count:
            # New ride appeared — always update prev_end
            updated_ends[activity_type] = new_end
            ride = rides[-1] if rides else None
            if not ride:
                continue

            ride_number = new_count

            if _is_ride_open(ride, last_gps_timestamp):
                # Ride is still in progress — send "Started"
                event_timestamp = ride['start']
                age = now - event_timestamp

                if age > HISTORICAL_THRESHOLD_SECONDS:
                    print(f"[PUSH-WORKER] Suppressed: {name} Ride {ride_number} "
                          f"started {age // 60}m ago — historical event", flush=True)
                    continue

                start_local = datetime.fromtimestamp(
                    ride['start'], tz=pytz.UTC).astimezone(detected_tz)
                send_pushcut_notification(
                    f"{name} Ride {ride_number} Started",
                    f"Started at {start_local.strftime('%H:%M')}")
            else:
                # Ride appeared already complete (has real end marker)
                event_timestamp = ride['end']
                age = now - event_timestamp

                if age > HISTORICAL_THRESHOLD_SECONDS:
                    print(f"[PUSH-WORKER] Suppressed: {name} Ride {ride_number} "
                          f"ended {age // 60}m ago — historical event", flush=True)
                    continue

                send_pushcut_notification(
                    f"{name} Ride {ride_number} Ended",
                    format_ride_end_text(ride, detected_tz))

        elif new_count == prev_count and new_count > 0:
            # Same count — check if a ride that was open is now closed
            ride = rides[-1] if rides else None
            if not ride:
                continue

            if _is_ride_open(ride, last_gps_timestamp):
                # Ride is still open — end is just advancing with GPS points.
                # Do NOT notify, and do NOT update prev_end so that
                # ends_changed will fire again on the next poll.
                continue

            # Ride is closed (has real end marker). Only notify if the end
            # actually changed significantly from what we last saw.
            updated_ends[activity_type] = new_end
            if new_end - prev_end > 60:
                ride_number = new_count
                event_timestamp = ride['end']
                age = now - event_timestamp

                if age > HISTORICAL_THRESHOLD_SECONDS:
                    print(f"[PUSH-WORKER] Suppressed: {name} Ride {ride_number} "
                          f"ended {age // 60}m ago — historical event", flush=True)
                    continue

                send_pushcut_notification(
                    f"{name} Ride {ride_number} Ended",
                    format_ride_end_text(ride, detected_tz))

    return updated_ends


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
