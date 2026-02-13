"""
Push notification worker for activity detection.

Runs as a separate process (Docker container) alongside the Flask app.
Polls OwnTracks every 30 seconds, detects ride transitions, and sends
iPhone push notifications via Pushcut.

Car/bike: Detects start/end markers (injected by Node-RED) directly for
  immediate notifications (no 5-point filter delay).
Walking/other: Uses parse_activities() with count tracking and stationary
  gap detection (no markers available).

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
from lib.activities import parse_activities
from lib.notifications import (
    check_and_notify_markers,
    check_and_notify_other_transitions,
    check_and_notify_other_ride_end,
    is_other_ride_ended,
)


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

    Returns dict with seen_marker_timestamps, prev_other_count, etc.,
    or None.
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


def _build_state_dict(session_start_timestamp, detected_tz, seen_markers,
                      prev_other_count, other_ended_notified):
    """Build the state dict for saving."""
    return {
        'session_start_timestamp': session_start_timestamp,
        'detected_tz': detected_tz.zone,
        'seen_marker_timestamps': list(seen_markers),
        'prev_other_count': prev_other_count,
        'other_ended_notified': other_ended_notified,
    }


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

    # Load persisted state
    worker_state = load_worker_state()
    seen_markers = set()
    prev_other_count = 0
    other_ended_notified = False
    first_run = True

    if worker_state:
        seen_markers = set(worker_state.get('seen_marker_timestamps', []))
        prev_other_count = worker_state.get('prev_other_count', 0)
        other_ended_notified = worker_state.get('other_ended_notified', False)
        session_start_timestamp = worker_state.get('session_start_timestamp')
        tz_name = worker_state.get('detected_tz', config.DEFAULT_TIMEZONE)
        detected_tz = pytz.timezone(tz_name)
        first_run = False
        print(f"[PUSH-WORKER] Loaded state: {len(seen_markers)} seen markers, "
              f"other_count={prev_other_count}", flush=True)

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
                seen_markers = set()
                prev_other_count = 0
                other_ended_notified = False
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

            # Advance last_poll_timestamp only if new points arrived
            if new_points:
                last_point_tst = max(p.get('tst', 0) for p in new_points)
                last_poll_timestamp = last_point_tst

            # On first run, initialize baseline without sending notifications
            if first_run:
                # Collect all existing markers into seen set
                for item in raw_data:
                    if (item.get('_type') == 'lwt' and item.get('custom') is True
                            and item.get('activity', '') in
                            ('car_start', 'car_end', 'bike_start', 'bike_end')):
                        seen_markers.add(item['tst'])

                new_other_count = len(activities.get('other', []))
                prev_other_count = new_other_count
                other_ended_notified = False
                first_run = False
                save_worker_state(_build_state_dict(
                    session_start_timestamp, detected_tz, seen_markers,
                    prev_other_count, other_ended_notified))
                print(f"[PUSH-WORKER] Initialized baseline: "
                      f"{len(seen_markers)} markers, "
                      f"other_count={prev_other_count}, "
                      f"points={len(gps_points)}", flush=True)
            else:
                state_changed = False

                # Car/bike: scan for new markers (immediate notification)
                seen_markers, markers_changed = check_and_notify_markers(
                    raw_data, seen_markers, activities, detected_tz)
                if markers_changed:
                    state_changed = True

                # Walking/other: count-based detection
                last_gps_tst = gps_points[-1]['tst'] if gps_points else 0
                new_other_count = len(activities.get('other', []))

                if new_other_count != prev_other_count:
                    check_and_notify_other_transitions(
                        prev_other_count, new_other_count, activities,
                        detected_tz, last_gps_tst)
                    prev_other_count = new_other_count
                    other_ended_notified = False
                    state_changed = True

                # Walking/other: stationary gap end detection
                other_rides = activities.get('other', [])
                if other_rides and last_gps_tst > 0:
                    last_other = other_rides[-1]
                    if not other_ended_notified:
                        if check_and_notify_other_ride_end(
                                last_other, len(other_rides), detected_tz):
                            other_ended_notified = True
                            state_changed = True
                    elif not is_other_ride_ended(last_other):
                        # User resumed walking — reset for next end detection
                        other_ended_notified = False
                        state_changed = True

                if state_changed:
                    save_worker_state(_build_state_dict(
                        session_start_timestamp, detected_tz, seen_markers,
                        prev_other_count, other_ended_notified))

            total_points = len(gps_points)
            other_count = len(activities.get('other', []))
            print(f"[PUSH-WORKER] Poll: {len(new_points)} new points, "
                  f"{total_points} total, markers_seen={len(seen_markers)}, "
                  f"other_count={other_count}", flush=True)

        except Exception as e:
            print(f"[PUSH-WORKER] Error in poll cycle: {e}", flush=True)

        # Sleep with jitter
        jitter = random.uniform(*POLL_JITTER)
        time.sleep(POLL_INTERVAL + jitter)


if __name__ == '__main__':
    run()
