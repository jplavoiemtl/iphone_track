"""
Live mode state persistence.

Handles saving/loading live mode state to disk for persistence
across container restarts.
"""
import json
import os

# State file in project root
LIVE_STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'live_mode_state.json'
)


def save_live_state(start_timestamp, timezone_name):
    """Save live mode state to disk for persistence across restarts.

    Args:
        start_timestamp: Epoch seconds when live mode started
        timezone_name: String timezone name (e.g., 'America/Montreal')
    """
    state = {
        'start_timestamp': start_timestamp,
        'timezone': timezone_name
    }
    with open(LIVE_STATE_FILE, 'w') as f:
        json.dump(state, f)


def load_live_state():
    """Load live mode state from disk.

    Returns:
        dict with 'start_timestamp' and 'timezone' keys, or None if no state exists
    """
    if not os.path.exists(LIVE_STATE_FILE):
        return None
    try:
        with open(LIVE_STATE_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def clear_live_state():
    """Remove the live state file."""
    if os.path.exists(LIVE_STATE_FILE):
        os.remove(LIVE_STATE_FILE)
