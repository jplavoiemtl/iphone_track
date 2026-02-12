"""
Push notification worker for activity detection.

Runs as a separate process (Docker container) alongside the Flask app.
Polls OwnTracks every 30 seconds, detects ride transitions, and sends
iPhone push notifications via Pushcut.

Shares no in-memory state with the Flask app. Communicates only through:
- live_mode_state.json (reads — written by Flask on session start/reset)
- push_notification_state.json (reads/writes — own state file)

Usage:
    python -m lib.push_worker
"""
import json
import os
import random
import time
from datetime import datetime

import pytz

import config
from lib.geo import get_timezone_from_gps
from lib.live import load_live_state
from lib.owntracks import fetch_owntracks_data
from lib.activities import parse_activities, calculate_activity_stats
from lib.notifications import check_and_notify_ride_transitions


# Worker state file path
WORKER_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'push_notification_state.json'
)

POLL_INTERVAL = 30  # seconds
POLL_JITTER = (3, 7)  # random jitter range in seconds
WAIT_FOR_SESSION = 60  # seconds to wait when no live session exists


def load_worker_state():
    """Load worker state from disk.

    Returns dict with prev_ride_counts, prev_ride_ends, etc., or None.
    """
    if not os.path.exists(WORKER_STATE_FILE):
        return None
    try:
        with open(WORKER_STATE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_worker_state(state):
    """Save worker state to disk atomically (write to temp, then rename)."""
    tmp_path = WORKER_STATE_FILE + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(state, f)
    os.replace(tmp_path, WORKER_STATE_FILE)


def _extract_ride_counts(activities):
    """Extract ride count per activity type."""
    counts = {}
    for activity_type in ['car', 'bike', 'other']:
        rides = activities.get(activity_type, [])
        counts[activity_type] = len(rides)
    return counts


def _extract_ride_ends(activities):
    """Extract the last ride's end timestamp per activity type."""
    ends = {}
    for activity_type in ['car', 'bike', 'other']:
        rides = activities.get(activity_type, [])
        if rides:
            ends[activity_type] = rides[-1]['end']
        else:
            ends[activity_type] = 0
    return ends


def _fetch_data(from_timestamp, to_timestamp, detected_tz):
    """Fetch OwnTracks data between two timestamps."""
    from_dt = datetime.fromtimestamp(from_timestamp, tz=pytz.UTC).astimezone(detected_tz)
    to_dt = datetime.fromtimestamp(to_timestamp, tz=pytz.UTC).astimezone(detected_tz)

    return fetch_owntracks_data(
        from_dt.strftime('%Y-%m-%d'),
        to_dt.strftime('%Y-%m-%d'),
        from_dt.strftime('%H:%M'),
        to_dt.strftime('%H:%M'),
        server_ip=config.OWNTRACKS_SERVER_IP,
        server_port=config.OWNTRACKS_SERVER_PORT,
        user=config.OWNTRACKS_USER,
        device_id=config.OWNTRACKS_DEVICE_ID,
        target_timezone=detected_tz,
        default_timezone=config.DEFAULT_TIMEZONE
    )


def run():
    """Main worker loop."""
    print("[PUSH-WORKER] Starting push notification worker", flush=True)

    if not config.PUSHCUT_WEBHOOK_URL:
        print("[PUSH-WORKER] PUSHCUT_WEBHOOK_URL not set — notifications disabled", flush=True)

    # In-memory accumulated data (lost on restart, rebuilt from catch-up fetch)
    raw_data = []
    existing_timestamps = set()
    last_poll_timestamp = None
    detected_tz = pytz.timezone(config.DEFAULT_TIMEZONE)
    session_start_timestamp = None

    # Load persisted state (ride counts/ends survive restarts)
    worker_state = load_worker_state()
    prev_counts = {'car': 0, 'bike': 0, 'other': 0}
    prev_ends = {'car': 0, 'bike': 0, 'other': 0}
    first_run = True

    if worker_state:
        prev_counts = worker_state.get('prev_ride_counts', prev_counts)
        prev_ends = worker_state.get('prev_ride_ends', prev_ends)
        session_start_timestamp = worker_state.get('session_start_timestamp')
        tz_name = worker_state.get('detected_tz', config.DEFAULT_TIMEZONE)
        detected_tz = pytz.timezone(tz_name)
        first_run = False
        print(f"[PUSH-WORKER] Loaded state: counts={prev_counts}", flush=True)

    while True:
        try:
            # Read live session info
            live_state = load_live_state()

            if not live_state:
                print("[PUSH-WORKER] No live session yet — waiting", flush=True)
                time.sleep(WAIT_FOR_SESSION)
                continue

            live_start = live_state['start_timestamp']
            live_tz_name = live_state.get('timezone', config.DEFAULT_TIMEZONE)
            live_tz = pytz.timezone(live_tz_name)

            # Detect session reset
            if session_start_timestamp != live_start:
                if session_start_timestamp is not None:
                    print(f"[PUSH-WORKER] Session reset detected — reinitializing", flush=True)
                else:
                    print(f"[PUSH-WORKER] Starting session from {live_start}", flush=True)

                session_start_timestamp = live_start
                detected_tz = live_tz
                raw_data = []
                existing_timestamps = set()
                last_poll_timestamp = None
                prev_counts = {'car': 0, 'bike': 0, 'other': 0}
                prev_ends = {'car': 0, 'bike': 0, 'other': 0}
                first_run = True

            now = int(time.time())

            # Determine fetch window
            if last_poll_timestamp is None:
                # First poll — catch-up fetch from session start
                fetch_from = session_start_timestamp
                print(f"[PUSH-WORKER] Catch-up fetch from session start", flush=True)
            else:
                fetch_from = last_poll_timestamp

            # Fetch data
            new_data = _fetch_data(fetch_from, now, detected_tz)

            new_points = []
            if new_data:
                # Filter new GPS points
                for item in new_data:
                    if (item.get('_type') == 'location'
                            and item.get('tst', 0) > (last_poll_timestamp or 0)):
                        new_points.append(item)

                # Merge into accumulated raw_data (dedup by timestamp)
                for item in new_data:
                    tst = item.get('tst')
                    if tst not in existing_timestamps:
                        raw_data.append(item)
                        existing_timestamps.add(tst)

            # Update timezone from first GPS point if needed
            if not any(item.get('_type') == 'location' for item in raw_data[:1]):
                pass  # No GPS data yet
            elif last_poll_timestamp is None and new_points:
                first_point = new_points[0]
                if 'lat' in first_point and 'lon' in first_point:
                    detected_tz = get_timezone_from_gps(
                        first_point['lat'], first_point['lon'])

            # Re-parse all activities from full accumulated data
            raw_data.sort(key=lambda x: x.get('tst', 0))
            gps_points, activities = parse_activities(raw_data)
            activity_stats = calculate_activity_stats(activities) if activities else {}

            # Extract current ride state
            new_counts = _extract_ride_counts(activities)
            new_ends = _extract_ride_ends(activities)

            # Advance last_poll_timestamp only if new points arrived
            if new_points:
                last_point_tst = max(p.get('tst', 0) for p in new_points)
                last_poll_timestamp = last_point_tst

            # On first run, initialize baseline without sending notifications
            if first_run:
                prev_counts = dict(new_counts)
                prev_ends = dict(new_ends)
                first_run = False
                save_worker_state({
                    'session_start_timestamp': session_start_timestamp,
                    'detected_tz': detected_tz.zone,
                    'prev_ride_counts': prev_counts,
                    'prev_ride_ends': prev_ends
                })
                print(f"[PUSH-WORKER] Initialized baseline: counts={new_counts}, "
                      f"points={len(gps_points)}", flush=True)
            else:
                # Check for transitions and notify
                counts_changed = new_counts != prev_counts
                ends_changed = any(
                    new_ends.get(t, 0) - prev_ends.get(t, 0) > 60
                    for t in ['car', 'bike', 'other']
                )

                last_gps_tst = gps_points[-1]['tst'] if gps_points else 0

                if counts_changed or ends_changed:
                    check_and_notify_ride_transitions(
                        prev_counts, new_counts, prev_ends, new_ends,
                        activities, detected_tz, last_gps_tst)

                    prev_counts = dict(new_counts)
                    prev_ends = dict(new_ends)
                    save_worker_state({
                        'session_start_timestamp': session_start_timestamp,
                        'detected_tz': detected_tz.zone,
                        'prev_ride_counts': prev_counts,
                        'prev_ride_ends': prev_ends
                    })

            total_points = len(gps_points)
            print(f"[PUSH-WORKER] Poll: {len(new_points)} new points, "
                  f"{total_points} total, counts={new_counts}", flush=True)

        except Exception as e:
            print(f"[PUSH-WORKER] Error in poll cycle: {e}", flush=True)

        # Sleep with jitter
        jitter = random.uniform(*POLL_JITTER)
        time.sleep(POLL_INTERVAL + jitter)


if __name__ == '__main__':
    run()
