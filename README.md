# iPhone Tracker Web App

## Overview
This is a web-based GPS activity tracking application designed to visualize and analyze location data from an **OwnTracks** server. It provides a modern, responsive interface for tracking movement history, classifying activities (Car, Bike, Walking), and gaining insights into your trips, all while keeping your data private on your own network.  2026

## Features

*   **Interactive Visualization**: View your GPS tracks on a full-screen Google Map with color-coded segments for different activities.
*   **Activity Classification**: Automatically detects and classifies periods of movement into categories like **Car**, **Bike**, and **Other** (Walking/Transit).
    *   **Smart Filtering**: To reduce noise, rides are automatically filtered out if they are shorter than **5 minutes** or cover a distance of less than **100 meters**.
*   **Ride Analytics**: Calculates detailed statistics for each trip, including distance, duration, and average speed.
*   **Live Mode**: Real-time tracking feature to monitor current location updates as they happen.
*   **Journey Playback**: "Relive" your trips with an animated playback feature. You can watch your route trace out on the map, pause, resume, and step through your journey point-by-point.
*   **Save & Share**: Export your daily maps to standalone HTML files. These saved maps retain all interactivity (zooming, clicking markers, toggling layers) and can be shared or archived.
*   **Multi-Device Support**: Unique session management allows you to view different data on your desktop and mobile device simultaneously.
*   **Privacy-First**: Runs entirely on your local network/server, ensuring your location history remains private.

## Tech Stack

*   **Backend**: Python 3, Flask
*   **Frontend**: HTML5, CSS3, Vanilla JavaScript
*   **Maps**: Google Maps JavaScript API
*   **Data Source**: OwnTracks Recorder (communicating via HTTP API)

## Installation & Setup

### Prerequisites
*   Python 3.8+
*   An OwnTracks Recorder instance running on your network
*   A Google Maps JavaScript API Key

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configuration
Create a `.env` file in the project root directory. You can use the following template (fill in your actual values):

```env
# Google Maps API Key
GOOGLE_MAPS_API_KEY=your_google_maps_api_key

# OwnTracks Server Configuration
OWNTRACKS_SERVER_IP=192.168.1.xxx
OWNTRACKS_SERVER_PORT=8083
OWNTRACKS_USER=your_owntracks_user
OWNTRACKS_DEVICE_ID=your_device_id

# Application Settings
DEFAULT_TIMEZONE=America/New_York
FLASK_SECRET_KEY=generate_a_random_secure_key
```

### 3. Running the App
Start the Flask development server:
```bash
python app.py
```
Access the application in your browser at `http://localhost:5000`.

## Docker Deployment
The application is container-ready for deployment on devices like a Raspberry Pi.
-   See `Dockerfile` for the image definition.
-   Refer to `doc/labpi_stack.yml` for an example Portainer stack configuration.

## Documentation
Code documentation is located in the `doc/` folder (not included in the public repository).
