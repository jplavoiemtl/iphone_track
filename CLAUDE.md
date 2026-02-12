# iPhone Tracker Web App

## Project Description
A web-based GPS activity tracking application that visualizes iPhone location data from an OwnTracks server on Google Maps. Runs locally on a home network. Supports multi-layer activity detection (car, bike, walking/other) with ride splitting, distance calculations, and interactive map visualization.

## Tech Stack
- **Backend**: Python 3 + Flask
- **Frontend**: HTML/CSS/JavaScript + Google Maps JavaScript API
- **Data source**: OwnTracks Recorder API (local network) + local activity markers JSON file
- **Secrets**: Environment variables (set inline in Portainer stack for Pi deployment)

## Project Structure
```
app.py              # Flask web server (entry point)
config.py           # Configuration from .env
lib/                # Backend library modules
  geo.py            # Haversine, movement detection, timezone
  owntracks.py      # OwnTracks API client
  activities.py     # Activity parsing, ride splitting
  markers.py        # Activity markers file reader
  notifications.py  # Pushcut push notification sender
  push_worker.py    # Always-on push notification worker (separate container)
templates/          # Jinja2 HTML templates
  index.html        # Main page
static/             # Frontend assets
  js/map.js         # Google Maps visualization
  js/app.js         # UI logic and API calls
  css/style.css     # Styling
doc/                # Project documentation
  plan.md           # Technology comparison and project plan
  architecture.md   # Architecture and API contracts
Dockerfile          # Docker image for Raspberry Pi deployment
iphonetrack.py      # Original desktop app (reference)
```

## How to Run
The app runs on a Raspberry Pi (labpi) via Docker and Portainer. See the
"Docker Deployment" section below for the full workflow.

## Secrets Management
All sensitive values are set as environment variables inline in the Portainer
stack definition. Never commit secrets to the repository.

Required environment variables:
- `GOOGLE_MAPS_API_KEY` - Google Maps JavaScript API key
- `OWNTRACKS_SERVER_IP` - OwnTracks Recorder server IP
- `OWNTRACKS_SERVER_PORT` - OwnTracks Recorder port
- `OWNTRACKS_USER` - OwnTracks user name
- `OWNTRACKS_DEVICE_ID` - OwnTracks device UUID
- `DEFAULT_TIMEZONE` - Fallback timezone (e.g., America/Montreal)
- `FLASK_SECRET_KEY` - Random secret for Flask sessions
- `PUSHCUT_WEBHOOK_URL` - (Optional) Pushcut webhook URL for push notifications

## Code Conventions
- Python: standard library style, no type annotations unless they add clarity
- JavaScript: vanilla JS (no frameworks), Google Maps JavaScript API v3
- Keep functions focused and small - match the existing module structure
- Backend handles all data processing; frontend only handles display
- API responses use JSON; all timestamps are UTC epoch seconds

## Multi-Device Support
The app uses session-based caching so multiple devices (desktop, phone) can use
the app simultaneously without conflicts. Each browser gets a unique session ID
stored in a cookie, and detection results are cached per-session in memory.

- Detection data is stored in `_session_caches[session_id]` instead of a global variable
- This allows desktop to detect Monday's activities while phone detects Tuesday's
- Sessions are isolated — one device's actions don't affect another's view
- The `FLASK_SECRET_KEY` environment variable is required for session cookies

## Push Notifications
- A separate push worker container (`lib/push_worker.py`) runs alongside the Flask app
- It polls OwnTracks every 30 seconds independently of the browser
- Detects ride transitions (start/end) for car, bike, and walking activities
- Sends iPhone push notifications via Pushcut webhook API
- Shares no in-memory state with Flask — communicates only through `live_mode_state.json`
- Worker state persisted in `push_notification_state.json` (gitignored)
- Historical events (>10 minutes old) are suppressed to avoid false notifications from batch uploads
- Detailed plan: `doc/Phase_14_Push_Notifications_Plan.md`

## Docker Deployment (Raspberry Pi 4 / labpi)
- The app runs in a Docker container on labpi using gunicorn with `--reload`
- `Dockerfile` in the project root defines the image (installs Python dependencies)
- The Docker image is built manually on the Pi, not via Portainer (Portainer runs
  in a container and cannot access host paths for `build:` or `env_file`)
- The entire source tree is bind-mounted into the container (`/home/pi/appjpl/iphone_track:/app`),
  so code changes via VS Code are picked up automatically — no rebuild needed
- Environment variables (secrets) are defined inline in the Portainer stack definition
  (not via `env_file`, since Portainer can't read host files)
- `GPS_activity_markers.json` is bind-mounted read-only from Node-RED's volume
- `saved_maps/` persists inside the bind-mounted source tree
- The stack YAML reference is at `doc/labpi_stack.yml`
- Full deployment plan: `doc/Move_to_labpi_Implementation_Plan.md`
- Original planning analysis: `doc/Move_iphone_track_to_labpi_Planning.md`

### How the Docker image and bind mount work together
The Docker image **does** contain a copy of the app code (the `COPY` steps in the
Dockerfile copy `app.py`, `lib/`, `templates/`, `static/`, etc. into the image).
However, the Portainer stack overrides that with a bind mount
(`/home/pi/appjpl/iphone_track:/app`) which overlays the image's `/app` directory
with the live source tree on the Pi.

So at runtime, the container uses:
- **From the image**: Python, pip packages (Flask, gunicorn, etc.)
- **From the bind mount**: The actual app code on disk

This is why code changes are live — gunicorn's `--reload` flag detects file changes
in the mounted directory and restarts the worker automatically. For frontend changes
(JS, CSS, HTML), a browser reload is needed since those are cached by the browser.

### Building the Docker image
Only needed on first deploy or when `requirements.txt` changes (since pip packages
live inside the image):
```bash
cd /home/pi/appjpl/iphone_track && docker build -t iphone_track .
```

### Day-to-day development workflow
1. Edit code in VS Code via Samba share (`\\labpi\appjpl\iphone_track`)
2. Save — gunicorn `--reload` detects file changes and restarts the worker automatically
3. Reload the browser for frontend changes (JS, CSS, HTML)
4. No rebuild, no container restart needed

## Planning & Documentation
- All planning documents and implementation plans go in the `doc/` folder
- Never place plan files outside the project directory
