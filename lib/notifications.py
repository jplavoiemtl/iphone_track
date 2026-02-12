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
from lib.geo import calculate_track_distance


# Events older than this are considered historical and suppressed
HISTORICAL_THRESHOLD_SECONDS = 600  # 10 minutes


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


def check_and_notify_ride_transitions(prev_counts, new_counts, prev_ends,
                                      new_ends, activities, detected_tz):
    """Compare ride snapshots and send notifications for recent transitions.

    For each activity type, detects:
    - Count increase + short duration (<2min): ride just started
    - Count increase + long duration (>=2min): ride appeared already complete
    - Same count + end timestamp moved >60s: open ride got its end marker

    Events older than 10 minutes (wall clock) are suppressed as historical.

    Returns dict of updated counts and ends to persist.
    """
    now = int(time.time())
    activity_names = {'car': 'Car', 'bike': 'Bike', 'other': 'Walking'}

    for activity_type in ['car', 'bike', 'other']:
        prev_count = prev_counts.get(activity_type, 0)
        new_count = new_counts.get(activity_type, 0)
        prev_end = prev_ends.get(activity_type, 0)
        new_end = new_ends.get(activity_type, 0)
        name = activity_names[activity_type]

        rides = activities.get(activity_type, [])

        if new_count > prev_count:
            # New ride appeared — check the latest ride
            ride = rides[-1] if rides else None
            if not ride:
                continue

            ride_duration = ride['end'] - ride['start']
            ride_number = new_count

            if ride_duration < 120:
                # Short duration — ride just started
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
                # Long duration — ride appeared already complete
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
            # Same count — check if end timestamp moved (ride completed)
            if new_end - prev_end > 60:
                ride = rides[-1] if rides else None
                if not ride:
                    continue

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
