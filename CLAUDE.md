# iPhone Tracker Web App

## Project Description
A web-based GPS activity tracking application that visualizes iPhone location data from an OwnTracks server on Google Maps. Runs locally on a home network. Supports multi-layer activity detection (car, bike, walking/other) with ride splitting, distance calculations, and interactive map visualization.

## Tech Stack
- **Backend**: Python 3 + Flask
- **Frontend**: HTML/CSS/JavaScript + Google Maps JavaScript API
- **Data source**: OwnTracks Recorder API (local network) + local activity markers JSON file
- **Secrets**: `.env` file loaded via `python-dotenv`

## Project Structure
```
app.py              # Flask web server (entry point)
config.py           # Configuration from .env
lib/                # Backend library modules
  geo.py            # Haversine, movement detection, timezone
  owntracks.py      # OwnTracks API client
  activities.py     # Activity parsing, ride splitting
  markers.py        # Activity markers file reader
templates/          # Jinja2 HTML templates
  index.html        # Main page
static/             # Frontend assets
  js/map.js         # Google Maps visualization
  js/app.js         # UI logic and API calls
  css/style.css     # Styling
doc/                # Project documentation
  plan.md           # Technology comparison and project plan
  architecture.md   # Architecture and API contracts
iphonetrack.py      # Original desktop app (reference)
```

## How to Run
```bash
pip install -r requirements.txt
cp .env.example .env   # Then edit .env with your real values
python app.py
# Open http://localhost:5000
```

## Secrets Management
All sensitive values are stored in `.env` (git-ignored). Never commit secrets to the repository.

Required secrets (see `.env.example`):
- `GOOGLE_MAPS_API_KEY` - Google Maps JavaScript API key
- `OWNTRACKS_SERVER_IP` - OwnTracks Recorder server IP
- `OWNTRACKS_SERVER_PORT` - OwnTracks Recorder port
- `OWNTRACKS_USER` - OwnTracks user name
- `OWNTRACKS_DEVICE_ID` - OwnTracks device UUID
- `DEFAULT_TIMEZONE` - Fallback timezone (e.g., America/Montreal)

## Code Conventions
- Python: standard library style, no type annotations unless they add clarity
- JavaScript: vanilla JS (no frameworks), Google Maps JavaScript API v3
- Keep functions focused and small - match the existing module structure
- Backend handles all data processing; frontend only handles display
- API responses use JSON; all timestamps are UTC epoch seconds

## Planning & Documentation
- All planning documents and implementation plans go in the `doc/` folder
- Never place plan files outside the project directory
