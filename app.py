from flask import Flask, render_template, request, jsonify, session, Response
import json
import os
import pytz
import uuid
import time
from datetime import datetime

import config
from lib.geo import get_timezone_from_gps, calculate_track_distance, format_time
from lib.owntracks import fetch_owntracks_data
from lib.activities import parse_activities, calculate_activity_stats
from lib.live import save_live_state, load_live_state, clear_live_state

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

# In-memory store for detection results, keyed by session ID
# Each browser/device gets its own cache to avoid conflicts
_session_caches = {}


def _get_cache():
    """Get the cache for the current session. Creates session ID if needed."""
    if 'cache_id' not in session:
        session['cache_id'] = str(uuid.uuid4())
    return _session_caches.setdefault(session['cache_id'], {})


# Live mode cache - shared across all sessions (single live mode per server)
_live_cache = {
    'is_active': False,
    'start_timestamp': None,
    'last_poll_timestamp': None,
    'detected_tz': None,
    'gps_points': [],
    'activities': {},
    'activity_stats': {},
    'raw_data': []
}


def _reset_live_cache():
    """Reset the live cache to empty state."""
    global _live_cache
    _live_cache = {
        'is_active': False,
        'start_timestamp': None,
        'last_poll_timestamp': None,
        'detected_tz': None,
        'gps_points': [],
        'activities': {},
        'activity_stats': {},
        'raw_data': []
    }


@app.route("/")
def index():
    return render_template("index.html", google_maps_api_key=config.GOOGLE_MAPS_API_KEY)


@app.route("/api/detect", methods=["POST"])
def detect_activities():
    data = request.get_json()
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    start_time = data.get("start_time", "00:00")
    end_time = data.get("end_time", "23:59")

    if not start_date or not end_date:
        return jsonify({"success": False, "error": "start_date and end_date are required"}), 400

    # Phase 1: Timezone discovery - broad fetch for the start date
    discovery_data = fetch_owntracks_data(
        start_date, start_date, "00:00", "23:59",
        server_ip=config.OWNTRACKS_SERVER_IP,
        server_port=config.OWNTRACKS_SERVER_PORT,
        user=config.OWNTRACKS_USER,
        device_id=config.OWNTRACKS_DEVICE_ID,
        default_timezone=config.DEFAULT_TIMEZONE
    )

    if not discovery_data:
        return jsonify({"success": False, "error": f"No data found for {start_date}"}), 404

    first_gps_point = next(
        (item for item in discovery_data
         if item.get("_type") == "location" and "lat" in item and "lon" in item),
        None
    )
    if not first_gps_point:
        return jsonify({"success": False, "error": "No GPS location points found to determine timezone"}), 404

    detected_tz = get_timezone_from_gps(first_gps_point["lat"], first_gps_point["lon"])
    tz_name = detected_tz.zone

    # Phase 2: Precise fetch with correct timezone
    raw_data = fetch_owntracks_data(
        start_date, end_date, start_time, end_time,
        server_ip=config.OWNTRACKS_SERVER_IP,
        server_port=config.OWNTRACKS_SERVER_PORT,
        user=config.OWNTRACKS_USER,
        device_id=config.OWNTRACKS_DEVICE_ID,
        target_timezone=detected_tz,
        default_timezone=config.DEFAULT_TIMEZONE
    )

    if not raw_data:
        return jsonify({
            "success": False,
            "error": f"No data for time range {start_time}-{end_time} in {tz_name}"
        }), 404

    gps_points, activities = parse_activities(raw_data)

    if not gps_points:
        return jsonify({"success": False, "error": "No GPS points found in the data"}), 404

    activity_stats = calculate_activity_stats(activities)

    # Cache results for track endpoint (per-session)
    cache = _get_cache()
    cache["gps_points"] = gps_points
    cache["activities"] = activities
    cache["activity_stats"] = activity_stats
    cache["detected_tz"] = detected_tz
    cache["raw_data"] = raw_data

    # Build timeline
    lwt_markers = [item for item in raw_data if item.get("_type") == "lwt" and item.get("custom") is True]
    timeline = _build_timeline(gps_points, activities, lwt_markers, detected_tz)

    # Format stats for JSON response
    stats_response = {}
    for activity_type in ['car', 'bike', 'other']:
        if activity_type in activity_stats:
            s = activity_stats[activity_type]
            stats_response[activity_type] = {
                'count': s['count'],
                'total_distance': round(s['total_distance'], 2),
                'total_duration': s['total_duration'],
                'total_duration_str': format_time(s['total_duration']),
                'total_points': s['total_points'],
                'filtered_count': s.get('filtered_count', 0),
                'avg_speed': round((s['total_distance'] / s['total_duration'] * 3600), 1) if s['total_duration'] > 0 else 0
            }

    # Build rides summary for display in UI
    rides_summary = []
    for activity_type in ['car', 'bike', 'other']:
        if activity_type in activities:
            for ride_idx, ride in enumerate(activities[activity_type]):
                if not ride['points']:
                    continue
                start_timestamp = ride['start']
                end_timestamp = ride['end']
                start_local = datetime.fromtimestamp(start_timestamp, tz=pytz.UTC).astimezone(detected_tz)
                end_local = datetime.fromtimestamp(end_timestamp, tz=pytz.UTC).astimezone(detected_tz)

                ride_distance = calculate_track_distance(ride['points'])

                ride_duration = end_timestamp - start_timestamp
                avg_speed = (ride_distance / ride_duration * 3600) if ride_duration > 0 else 0

                rides_summary.append({
                    'type': activity_type,
                    'ride_number': ride_idx + 1,
                    'start_timestamp': start_timestamp,
                    'end_timestamp': end_timestamp,
                    'start_datetime_str': start_local.strftime('%b %d, %H:%M'),
                    'end_datetime_str': end_local.strftime('%b %d, %H:%M'),
                    'distance': round(ride_distance, 2),
                    'duration': ride_duration,
                    'avg_speed': round(avg_speed, 1),
                    'points': len(ride['points'])
                })

    # Sort by start timestamp descending (most recent first)
    rides_summary.sort(key=lambda x: x['start_timestamp'], reverse=True)

    return jsonify({
        "success": True,
        "timezone": tz_name,
        "total_points": len(gps_points),
        "activity_markers": len(lwt_markers),
        "stats": stats_response,
        "rides": rides_summary,
        "timeline": timeline
    })


@app.route("/api/track/<activity_type>")
def get_track_data(activity_type):
    cache = _get_cache()
    if not cache.get("activities"):
        return jsonify({"success": False, "error": "No detection data. Run detect first."}), 400

    activities = cache["activities"]
    gps_points = cache["gps_points"]
    activity_stats = cache["activity_stats"]
    detected_tz = cache["detected_tz"]

    ride_colors = {
        'car': ['#FF0000', '#FF8C00', '#FFD700', '#FF1493', '#8B0000'],
        'bike': ['#FF8C00', '#228B22', '#1E90FF', '#8B4513', '#4B0082', '#DC143C', '#00CED1'],
        'other': ['#800080', '#FF00FF', '#FFA500', '#00FFFF', '#8B4513']
    }

    if activity_type == 'all':
        if not gps_points:
            return jsonify({"success": False, "error": "No GPS points available"}), 404

        layer_distance = calculate_track_distance(gps_points)
        layer_duration = gps_points[-1]["tst"] - gps_points[0]["tst"] if len(gps_points) > 1 else 0

        start_local = datetime.fromtimestamp(gps_points[0]['tst'], tz=pytz.UTC).astimezone(detected_tz)
        end_local = datetime.fromtimestamp(gps_points[-1]['tst'], tz=pytz.UTC).astimezone(detected_tz)

        return jsonify({
            "success": True,
            "activity_type": "all",
            "mode": "basic",
            "points": [{"lat": p["lat"], "lng": p["lon"], "tst": p["tst"]} for p in gps_points],
            "stats": {
                "distance": round(layer_distance, 2),
                "duration": layer_duration,
                "rides": sum(activity_stats.get(a, {}).get('count', 0) for a in ['car', 'bike', 'other']),
                "points": len(gps_points)
            },
            "start_time_str": start_local.strftime('%H:%M:%S'),
            "end_time_str": end_local.strftime('%H:%M:%S')
        })

    if activity_type not in activities or not activities[activity_type]:
        return jsonify({"success": False, "error": f"No {activity_type} activities found"}), 404

    colors = ride_colors.get(activity_type, ['#FFA500'])
    rides_data = []

    for ride_idx, ride in enumerate(activities[activity_type]):
        if not ride['points']:
            continue

        color = colors[ride_idx % len(colors)]
        start_timestamp = ride['start']
        end_timestamp = ride['end']

        start_local = datetime.fromtimestamp(start_timestamp, tz=pytz.UTC).astimezone(detected_tz)
        end_local = datetime.fromtimestamp(end_timestamp, tz=pytz.UTC).astimezone(detected_tz)

        ride_distance = calculate_track_distance(ride['points'])

        ride_duration = end_timestamp - start_timestamp
        avg_speed = (ride_distance / ride_duration * 3600) if ride_duration > 0 else 0

        rides_data.append({
            'ride_number': ride_idx + 1,
            'start_timestamp': start_timestamp,
            'end_timestamp': end_timestamp,
            'start_time_str': start_local.strftime('%H:%M:%S'),
            'end_time_str': end_local.strftime('%H:%M:%S'),
            'start_datetime_str': start_local.strftime('%b %d, %H:%M'),
            'end_datetime_str': end_local.strftime('%b %d, %H:%M'),
            'points': [{"lat": p["lat"], "lng": p["lon"], "tst": p["tst"]} for p in ride['points']],
            'distance': round(ride_distance, 2),
            'duration': ride_duration,
            'avg_speed': round(avg_speed, 1),
            'color': color
        })

    stats = activity_stats.get(activity_type, {})

    return jsonify({
        "success": True,
        "activity_type": activity_type,
        "mode": "rich",
        "rides": rides_data,
        "stats": {
            "distance": round(stats.get('total_distance', 0), 2),
            "duration": stats.get('total_duration', 0),
            "rides": stats.get('count', 0),
            "points": stats.get('total_points', 0)
        }
    })


@app.route("/api/save-map", methods=["POST"])
def save_map():
    cache = _get_cache()
    if not cache.get("activities"):
        return jsonify({"success": False, "error": "No detection data. Run detect first."}), 400

    data = request.get_json()
    active_layers = data.get("active_layers", [])

    if not active_layers:
        return jsonify({"success": False, "error": "No active layers to save"}), 400

    gps_points = cache["gps_points"]
    activities = cache["activities"]
    activity_stats = cache["activity_stats"]
    detected_tz = cache["detected_tz"]

    # Build layer data and ride data for embedding
    saved_layers_data = {}
    saved_rides_data = {}

    ride_colors = {
        'car': ['#FF0000', '#FF8C00', '#FFD700', '#FF1493', '#8B0000'],
        'bike': ['#FF8C00', '#228B22', '#1E90FF', '#8B4513', '#4B0082', '#DC143C', '#00CED1'],
        'other': ['#800080', '#FF00FF', '#FFA500', '#00FFFF', '#8B4513']
    }

    for layer_type in active_layers:
        if layer_type == 'all':
            points = gps_points
        elif layer_type in activities:
            points = []
            for ride in activities[layer_type]:
                points.extend(ride['points'])
            points.sort(key=lambda x: x['tst'])
        else:
            continue

        if not points:
            continue

        if layer_type in activity_stats:
            stats = activity_stats[layer_type]
            layer_distance = stats.get('total_distance', 0)
            layer_duration = stats.get('total_duration', 0)
            layer_rides = stats.get('count', 0)
        else:
            layer_distance = calculate_track_distance(points)
            layer_duration = points[-1]["tst"] - points[0]["tst"] if len(points) > 1 else 0
            layer_rides = sum(activity_stats.get(a, {}).get('count', 0) for a in ['car', 'bike', 'other'])

        start_local = datetime.fromtimestamp(points[0]['tst'], tz=pytz.UTC).astimezone(detected_tz)
        end_local = datetime.fromtimestamp(points[-1]['tst'], tz=pytz.UTC).astimezone(detected_tz)

        saved_layers_data[layer_type] = {
            'points': [{'lat': p['lat'], 'lng': p['lon'], 'tst': p['tst']} for p in points],
            'stats': {
                'distance': layer_distance,
                'duration': layer_duration,
                'rides': layer_rides,
                'points': len(points),
                'start_time_str': start_local.strftime('%H:%M:%S'),
                'end_time_str': end_local.strftime('%H:%M:%S')
            }
        }

        if layer_type in ['car', 'bike', 'other'] and layer_type in activities:
            colors = ride_colors.get(layer_type, ['#FFA500'])
            saved_rides_data[layer_type] = []
            for ride_idx, ride in enumerate(activities[layer_type]):
                if not ride['points']:
                    continue
                s_local = datetime.fromtimestamp(ride['start'], tz=pytz.UTC).astimezone(detected_tz)
                e_local = datetime.fromtimestamp(ride['end'], tz=pytz.UTC).astimezone(detected_tz)
                saved_rides_data[layer_type].append({
                    'start': ride['start'],
                    'end': ride['end'],
                    'points': [{'lat': p['lat'], 'lng': p['lon'], 'tst': p['tst']} for p in ride['points']],
                    'start_time_str': s_local.strftime('%b %d, %H:%M'),
                    'end_time_str': e_local.strftime('%b %d, %H:%M'),
                    'color': colors[ride_idx % len(colors)]
                })

    # Generate filename
    now = datetime.now()
    start_date = data.get("start_date", now.strftime("%Y-%m-%d"))
    end_date = data.get("end_date", start_date)
    date_str = start_date if start_date == end_date else f"{start_date}_to_{end_date}"
    layer_names = "_".join(sorted(active_layers))
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"interactive_map_{date_str}_{layer_names}_{timestamp}.html"

    # Generate self-contained HTML
    html = _generate_saved_map_html(
        saved_layers_data, saved_rides_data,
        date_range=f"{start_date} to {end_date}",
        active_layers=active_layers,
        total_points=len(gps_points),
        saved_timestamp=now.strftime("%Y-%m-%d %H:%M:%S")
    )

    # Save to saved_maps directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    saved_maps_dir = os.path.join(script_dir, "saved_maps")
    os.makedirs(saved_maps_dir, exist_ok=True)
    saved_path = os.path.join(saved_maps_dir, filename)
    with open(saved_path, 'w', encoding='utf-8', newline='') as f:
        f.write(html)

    return jsonify({
        "success": True,
        "filename": filename,
        "path": saved_path,
        "layers": active_layers,
        "total_points": len(gps_points)
    })


def _generate_saved_map_html(saved_layers_data, saved_rides_data, date_range, active_layers, total_points, saved_timestamp):
    title = f"GPS Multi-Layer Tracking - {date_range} ({len(active_layers)} layers)"
    layers_json = json.dumps(saved_layers_data)
    rides_json = json.dumps(saved_rides_data)
    api_key = config.GOOGLE_MAPS_API_KEY
    layers_list = ', '.join(active_layers)

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <script src="https://maps.googleapis.com/maps/api/js?key={api_key}&callback=initMap" async defer></script>
    <script>
        var map;
        var activityLayers = {{}};
        var layerVisibility = {{}};

        var savedLayersData = {layers_json};
        var savedRidesData = {rides_json};

        var activityConfig = {{
            'car': {{ color: '#FF4444', icon: '\\u{{1F697}}', name: 'Car' }},
            'bike': {{ color: '#FFD700', icon: '\\u{{1F6B4}}', name: 'Bike' }},
            'other': {{ color: '#4444FF', icon: '\\u{{1F6B6}}', name: 'Other' }},
            'all': {{ color: '#FFA500', icon: '\\u{{1F4CD}}', name: 'All' }}
        }};

        function initMap() {{
            map = new google.maps.Map(document.getElementById('map'), {{
                center: {{ lat: 0, lng: 0 }},
                zoom: 15,
                mapTypeId: 'roadmap'
            }});
            createLayerControl();
            loadSavedLayers();
        }}

        function loadSavedLayers() {{
            var bounds = new google.maps.LatLngBounds();
            var hasData = false;

            Object.keys(savedLayersData).forEach(function(activityType) {{
                var layerData = savedLayersData[activityType];
                var points = layerData.points;
                var stats = layerData.stats;

                if (points && points.length > 0) {{
                    if (savedRidesData[activityType] && savedRidesData[activityType].length > 0) {{
                        addActivityWithIndividualRides(activityType, savedRidesData[activityType], stats);
                    }} else {{
                        addActivityLayerWithStats(activityType, points, stats);
                    }}
                    points.forEach(function(p) {{
                        bounds.extend(new google.maps.LatLng(p.lat, p.lng));
                        hasData = true;
                    }});
                }}
            }});

            if (hasData) {{
                map.fitBounds(bounds);
                google.maps.event.addListenerOnce(map, 'bounds_changed', function() {{
                    if (map.getZoom() > 16) map.setZoom(16);
                    updateLayerControl();
                }});
            }}
            setTimeout(function() {{ calculateTotalDistance(); updateLayerControl(); }}, 1000);
        }}

        function addActivityWithIndividualRides(activityType, rides, stats) {{
            if (!activityLayers[activityType]) {{
                activityLayers[activityType] = {{ paths: [], markers: [], visible: true }};
                layerVisibility[activityType] = true;
            }}
            var config = activityConfig[activityType] || activityConfig['all'];
            var layer = activityLayers[activityType];

            rides.forEach(function(ride, rideIndex) {{
                var rideColor = ride.color || config.color;
                var points = ride.points;
                for (var i = 1; i < points.length; i++) {{
                    var seg = new google.maps.Polyline({{
                        path: [{{ lat: points[i-1].lat, lng: points[i-1].lng }}, {{ lat: points[i].lat, lng: points[i].lng }}],
                        geodesic: true, strokeColor: rideColor, strokeOpacity: 0.8, strokeWeight: 4,
                        map: layer.visible ? map : null
                    }});
                    layer.paths.push(seg);
                }}
                addSavedRideMarkers(activityType, ride, rideIndex + 1, rideColor, layer);
            }});
            updateLayerControl();
        }}

        function addSavedRideMarkers(activityType, ride, rideNumber, rideColor, layer) {{
            var config = activityConfig[activityType] || activityConfig['all'];
            var points = ride.points;
            if (points.length === 0) return;

            var startPoint = points[0];
            for (var i = 0; i < points.length; i++) {{ if (points[i].tst >= ride.start) {{ startPoint = points[i]; break; }} }}

            var endPoint = points[points.length - 1];
            for (var i = points.length - 1; i >= 0; i--) {{ if (points[i].tst <= ride.end) {{ endPoint = points[i]; break; }} }}

            var rideDuration = ride.end - ride.start;
            var dh = Math.floor(rideDuration / 3600);
            var dm = Math.floor((rideDuration % 3600) / 60);
            var rideDistance = 0;
            for (var i = 1; i < points.length; i++) {{
                var la1=points[i-1].lat*Math.PI/180, lo1=points[i-1].lng*Math.PI/180;
                var la2=points[i].lat*Math.PI/180, lo2=points[i].lng*Math.PI/180;
                var dla=la2-la1, dlo=lo2-lo1;
                var a=Math.sin(dla/2)*Math.sin(dla/2)+Math.cos(la1)*Math.cos(la2)*Math.sin(dlo/2)*Math.sin(dlo/2);
                var sd=6371*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));
                if(sd>=0.01) rideDistance+=sd*1.05;
            }}
            var avgSpeed = rideDuration > 0 ? (rideDistance / rideDuration * 3600) : 0;

            var sm = new google.maps.Marker({{
                position: {{ lat: startPoint.lat, lng: startPoint.lng }},
                map: layer.visible ? map : null,
                title: config.name + ' Ride ' + rideNumber + ' Start',
                icon: {{ path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 6, fillColor: rideColor, fillOpacity: 1, strokeColor: '#FFF', strokeWeight: 2 }},
                zIndex: 1000 + rideNumber
            }});
            var si = new google.maps.InfoWindow({{ content: '<div style="font-size:12px;min-width:150px;">' + config.name + ' Ride ' + rideNumber + '<br>Start: ' + ride.start_time_str + '</div>' }});
            sm.addListener('click', function() {{ si.open(map, sm); }});
            layer.markers.push(sm);

            var endInfo = config.name + ' Ride ' + rideNumber + '<br>End: ' + ride.end_time_str + '<br>Distance: ' + rideDistance.toFixed(2) + ' km<br>Duration: ' + dh + 'h ' + dm + 'm<br>Avg Speed: ' + avgSpeed.toFixed(1) + ' km/h<br>Points: ' + points.length;
            var em = new google.maps.Marker({{
                position: {{ lat: endPoint.lat, lng: endPoint.lng }},
                map: layer.visible ? map : null,
                title: config.name + ' Ride ' + rideNumber + ' End',
                icon: {{ path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: rideColor, fillOpacity: 0.9, strokeColor: '#FFF', strokeWeight: 2 }},
                zIndex: 999 + rideNumber
            }});
            var ei = new google.maps.InfoWindow({{ content: '<div style="font-size:12px;min-width:150px;">' + endInfo + '</div>' }});
            em.addListener('click', function() {{ ei.open(map, em); }});
            layer.markers.push(em);
        }}

        function addActivityLayerWithStats(activityType, points, stats) {{
            if (!activityLayers[activityType]) {{
                activityLayers[activityType] = {{ paths: [], markers: [], visible: true }};
                layerVisibility[activityType] = true;
            }}
            var config = activityConfig[activityType] || activityConfig['all'];
            var layer = activityLayers[activityType];

            for (var i = 1; i < points.length; i++) {{
                var seg = new google.maps.Polyline({{
                    path: [{{ lat: points[i-1].lat, lng: points[i-1].lng }}, {{ lat: points[i].lat, lng: points[i].lng }}],
                    geodesic: true, strokeColor: config.color, strokeOpacity: 0.8, strokeWeight: 4,
                    map: layer.visible ? map : null
                }});
                layer.paths.push(seg);
            }}
            if (points.length > 0) {{
                var sm = new google.maps.Marker({{
                    position: {{ lat: points[0].lat, lng: points[0].lng }},
                    map: layer.visible ? map : null,
                    icon: {{ path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW, scale: 6, fillColor: config.color, fillOpacity: 1, strokeColor: '#FFF', strokeWeight: 2 }},
                    zIndex: 1000
                }});
                var si = new google.maps.InfoWindow({{ content: '<div style="font-size:12px;"><strong>' + config.name + ' Start</strong><br>' + stats.start_time_str + '</div>' }});
                sm.addListener('click', function() {{ si.open(map, sm); }});
                layer.markers.push(sm);

                var dh = Math.floor(stats.duration / 3600);
                var dm = Math.floor((stats.duration % 3600) / 60);
                var as = stats.duration > 0 ? (stats.distance / stats.duration * 3600) : 0;
                var endContent = '<div style="font-size:12px;min-width:150px;"><strong>' + config.name + ' End</strong><br>Time: ' + stats.end_time_str + '<br>Distance: ' + stats.distance.toFixed(2) + ' km<br>Duration: ' + dh + 'h ' + dm + 'm<br>Avg Speed: ' + as.toFixed(1) + ' km/h<br>Points: ' + stats.points + '</div>';
                var em = new google.maps.Marker({{
                    position: {{ lat: points[points.length-1].lat, lng: points[points.length-1].lng }},
                    map: layer.visible ? map : null,
                    icon: {{ path: google.maps.SymbolPath.CIRCLE, scale: 10, fillColor: config.color, fillOpacity: 0.9, strokeColor: '#FFF', strokeWeight: 3 }},
                    zIndex: 999
                }});
                var ei = new google.maps.InfoWindow({{ content: endContent }});
                em.addListener('click', function() {{ ei.open(map, em); }});
                layer.markers.push(em);
            }}
            updateLayerControl();
        }}

        function toggleLayer(activityType) {{
            if (!activityLayers[activityType]) return;
            var layer = activityLayers[activityType];
            var isVisible = !layer.visible;
            layer.visible = isVisible;
            layerVisibility[activityType] = isVisible;
            layer.paths.forEach(function(p) {{ p.setMap(isVisible ? map : null); }});
            layer.markers.forEach(function(m) {{ m.setMap(isVisible ? map : null); }});
            updateLayerControl();
            calculateTotalDistance();
        }}

        function createLayerControl() {{
            var div = document.createElement('div');
            div.id = 'layerControl';
            div.innerHTML = '<div style="background:rgba(255,255,255,0.95);border:2px solid #666;border-radius:8px;margin:10px;padding:12px;font-family:Arial,sans-serif;font-size:12px;box-shadow:0 3px 10px rgba(0,0,0,0.3);min-width:200px;"><div style="font-weight:bold;margin-bottom:10px;color:#333;font-size:14px;text-align:center;border-bottom:1px solid #ddd;padding-bottom:8px;">Active Layers</div><div id="layerList"></div></div>';
            map.controls[google.maps.ControlPosition.TOP_LEFT].push(div);
        }}

        function updateLayerControl() {{
            var list = document.getElementById('layerList');
            if (!list) return;
            list.innerHTML = '';
            Object.keys(activityLayers).forEach(function(type) {{
                var layer = activityLayers[type];
                if (layer.paths.length > 0 || layer.markers.length > 0) {{
                    var cfg = activityConfig[type] || activityConfig['all'];
                    var vis = layerVisibility[type];
                    var stats = savedLayersData[type] ? savedLayersData[type].stats : null;

                    var container = document.createElement('div');
                    container.style.cssText = 'margin:8px 0;';

                    var item = document.createElement('div');
                    item.style.cssText = 'display:flex;align-items:center;padding:6px;background:rgba(248,248,248,0.8);border-radius:' + (stats ? '6px 6px 0 0' : '6px') + ';border:1px solid #e0e0e0;' + (stats ? 'border-bottom:none;' : '');
                    item.innerHTML = '<span style="font-size:16px;margin-right:8px;width:20px;text-align:center;">' + cfg.icon + '</span><span style="flex-grow:1;font-weight:500;color:#333;">' + cfg.name + '</span><button onclick="toggleLayer(\\'' + type + '\\')" style="padding:4px 8px;border:none;border-radius:4px;color:white;font-size:10px;font-weight:bold;cursor:pointer;background:' + cfg.color + ';opacity:' + (vis ? '1' : '0.5') + ';">' + (vis ? 'Hide' : 'Show') + '</button>';
                    container.appendChild(item);

                    if (stats) {{
                        var durationMins = Math.floor(stats.duration / 60);
                        var durationStr = durationMins >= 60 ? Math.floor(durationMins / 60) + 'h ' + (durationMins % 60) + 'm' : durationMins + 'm';
                        var avgSpeed = stats.duration > 0 ? (stats.distance / stats.duration * 3600) : 0;

                        var statsRow = document.createElement('div');
                        statsRow.style.cssText = 'padding:4px 6px 6px 34px;background:rgba(248,248,248,0.6);border-radius:0 0 6px 6px;border:1px solid #e0e0e0;border-top:none;font-size:11px;color:#666;';
                        statsRow.innerHTML = stats.distance.toFixed(1) + ' km | ' + durationStr + ' | ' + avgSpeed.toFixed(1) + ' km/h';
                        container.appendChild(statsRow);
                    }}

                    list.appendChild(container);
                }}
            }});
        }}

        function calculateTotalDistance() {{
            var total = 0;
            if ('all' in savedLayersData && layerVisibility['all'] !== false) {{
                total = savedLayersData['all'].stats.distance;
            }} else {{
                Object.keys(savedLayersData).forEach(function(type) {{
                    if (type !== 'all' && layerVisibility[type] !== false) {{
                        total += savedLayersData[type].stats.distance;
                    }}
                }});
            }}
            document.getElementById('distanceTitle').innerText = 'Saved Interactive Map - Total Distance: ' + total.toFixed(3) + ' km';
        }}
    </script>
    <style>
        body {{ margin: 0; font-family: Arial, sans-serif; background-color: #d3d3d3; }}
        h1 {{ font-size: 18px; margin: 5px; color: #333; background-color: #e8f5e8; padding: 5px; border-radius: 4px; }}
        #map {{ height: 95vh; width: 100%; }}
    </style>
</head>
<body>
    <h1 id="distanceTitle">Total Distance: 0 km</h1>
    <div id="map"></div>
    <div style="position:absolute;top:100px;right:10px;background:rgba(255,255,255,0.95);border:2px solid #666;border-radius:8px;padding:12px;font-family:Arial,sans-serif;font-size:12px;box-shadow:0 3px 10px rgba(0,0,0,0.3);z-index:1000;max-width:250px;">
        <div style="font-weight:bold;margin-bottom:8px;color:#333;font-size:13px;">Session Info</div>
        <div><strong>Date:</strong> {date_range}</div>
        <div><strong>Saved:</strong> {saved_timestamp}</div>
        <div><strong>Layers:</strong> {layers_list}</div>
        <div><strong>Total Points:</strong> {total_points:,}</div>
        <div style="margin-top:8px;font-size:11px;color:#666;font-style:italic;">Use layer controls (left) to show/hide</div>
    </div>
</body>
</html>"""


# =============================================================================
# Live Mode Endpoints
# =============================================================================

@app.route("/api/live/start", methods=["POST"])
def live_start():
    """Initialize or resume live mode.

    Behavior:
    - If reset=true: force fresh start (clear existing session)
    - If session is already active in memory: return existing session (join)
    - If resume=true and saved state exists: restore from saved state
    - Otherwise: fresh start from now
    """
    global _live_cache

    data = request.get_json() or {}
    resume = data.get('resume', False)
    reset = data.get('reset', False)

    now = int(time.time())

    # If reset requested, skip the join logic and force fresh start
    if reset:
        # Clear existing cache and fall through to fresh start
        _reset_live_cache()

    # Check if session is already active in memory (another device joined)
    elif _live_cache.get('is_active') and _live_cache.get('start_timestamp'):
        # Return existing session for joining device
        detected_tz = _live_cache.get('detected_tz') or pytz.timezone(config.DEFAULT_TIMEZONE)
        start_dt = datetime.fromtimestamp(_live_cache['start_timestamp'], tz=pytz.UTC).astimezone(detected_tz)

        # Format stats for response
        stats_response = _format_activity_stats(_live_cache.get('activity_stats', {}))

        return jsonify({
            "success": True,
            "mode": "joined",
            "start_timestamp": _live_cache['start_timestamp'],
            "start_time_str": start_dt.strftime('%Y-%m-%d %H:%M:%S'),
            "timezone": detected_tz.zone,
            "total_points": len(_live_cache.get('gps_points', [])),
            "stats": stats_response
        })

    # Check for saved state to resume
    saved_state = load_live_state()

    if resume and saved_state:
        # Resume from saved state - fetch all data from start to now
        start_timestamp = saved_state['start_timestamp']
        tz_name = saved_state.get('timezone', config.DEFAULT_TIMEZONE)
        detected_tz = pytz.timezone(tz_name)

        # Fetch all data from start_timestamp to now
        from_dt = datetime.fromtimestamp(start_timestamp, tz=pytz.UTC).astimezone(detected_tz)
        to_dt = datetime.fromtimestamp(now, tz=pytz.UTC).astimezone(detected_tz)

        raw_data = fetch_owntracks_data(
            from_dt.strftime('%Y-%m-%d'),
            to_dt.strftime('%Y-%m-%d'),
            from_dt.strftime('%H:%M:%S'),
            to_dt.strftime('%H:%M:%S'),
            server_ip=config.OWNTRACKS_SERVER_IP,
            server_port=config.OWNTRACKS_SERVER_PORT,
            user=config.OWNTRACKS_USER,
            device_id=config.OWNTRACKS_DEVICE_ID,
            target_timezone=detected_tz,
            default_timezone=config.DEFAULT_TIMEZONE
        )

        if raw_data:
            # Update timezone from first GPS point if available
            first_gps = next((item for item in raw_data if item.get("_type") == "location"), None)
            if first_gps:
                detected_tz = get_timezone_from_gps(first_gps['lat'], first_gps['lon'])
                tz_name = detected_tz.zone

            gps_points, activities = parse_activities(raw_data)
            activity_stats = calculate_activity_stats(activities) if activities else {}
        else:
            raw_data = []
            gps_points = []
            activities = {}
            activity_stats = {}

        # Initialize live cache with restored data
        _live_cache = {
            'is_active': True,
            'start_timestamp': start_timestamp,
            'last_poll_timestamp': now,
            'detected_tz': detected_tz,
            'gps_points': gps_points,
            'activities': activities,
            'activity_stats': activity_stats,
            'raw_data': raw_data
        }

        start_dt = datetime.fromtimestamp(start_timestamp, tz=pytz.UTC).astimezone(detected_tz)
        stats_response = _format_activity_stats(activity_stats)

        return jsonify({
            "success": True,
            "mode": "resumed",
            "start_timestamp": start_timestamp,
            "start_time_str": start_dt.strftime('%Y-%m-%d %H:%M:%S'),
            "timezone": tz_name,
            "total_points": len(gps_points),
            "stats": stats_response
        })

    # Fresh start
    default_tz = pytz.timezone(config.DEFAULT_TIMEZONE)
    tz_name = default_tz.zone

    # Initialize live cache
    _live_cache = {
        'is_active': True,
        'start_timestamp': now,
        'last_poll_timestamp': now,
        'detected_tz': default_tz,
        'gps_points': [],
        'activities': {},
        'activity_stats': {},
        'raw_data': []
    }

    # Persist state for restart recovery
    save_live_state(now, tz_name)

    start_dt = datetime.fromtimestamp(now, tz=pytz.UTC).astimezone(default_tz)

    return jsonify({
        "success": True,
        "mode": "fresh",
        "start_timestamp": now,
        "start_time_str": start_dt.strftime('%Y-%m-%d %H:%M:%S'),
        "timezone": tz_name,
        "total_points": 0,
        "stats": {}
    })


def _format_activity_stats(activity_stats):
    """Format activity stats for JSON response."""
    stats_response = {}
    for activity_type in ['car', 'bike', 'other']:
        if activity_type in activity_stats:
            s = activity_stats[activity_type]
            stats_response[activity_type] = {
                'count': s['count'],
                'total_distance': round(s['total_distance'], 2),
                'total_duration': s['total_duration'],
                'total_duration_str': format_time(s['total_duration']),
                'total_points': s['total_points'],
                'avg_speed': round((s['total_distance'] / s['total_duration'] * 3600), 1) if s['total_duration'] > 0 else 0
            }
    return stats_response


@app.route("/api/live/poll", methods=["POST"])
def live_poll():
    """Fetch new points since last poll and update live cache.

    Called by frontend every 30 seconds.
    """
    global _live_cache

    # Auto-recover if session was lost (e.g., gunicorn reload) but persisted state exists
    if not _live_cache.get('is_active'):
        saved_state = load_live_state()
        if saved_state and saved_state.get('start_timestamp'):
            # Reinitialize cache from persisted state
            print("AUTO-RECOVERING live session from persisted state", flush=True)
            tz_name = saved_state.get('timezone', config.DEFAULT_TIMEZONE)
            _live_cache = {
                'is_active': True,
                'start_timestamp': saved_state['start_timestamp'],
                'last_poll_timestamp': saved_state['start_timestamp'],  # Will refetch all data
                'detected_tz': pytz.timezone(tz_name),
                'gps_points': [],
                'activities': {},
                'activity_stats': {},
                'raw_data': []
            }
        else:
            return jsonify({"success": False, "error": "Live mode not active"}), 400

    # Get last_drawn_timestamp from frontend (to know what to send for drawing)
    data = request.get_json() or {}
    last_drawn_timestamp = data.get('last_drawn_timestamp', 0)

    now = int(time.time())
    last_poll = _live_cache.get('last_poll_timestamp', now)
    detected_tz = _live_cache.get('detected_tz')

    # Convert timestamps to date/time strings for OwnTracks API
    # Fetch from 1 second after last poll to now
    from_dt = datetime.fromtimestamp(last_poll, tz=pytz.UTC).astimezone(detected_tz)
    to_dt = datetime.fromtimestamp(now, tz=pytz.UTC).astimezone(detected_tz)

    # Fetch new data
    new_data = fetch_owntracks_data(
        from_dt.strftime('%Y-%m-%d'),
        to_dt.strftime('%Y-%m-%d'),
        from_dt.strftime('%H:%M:%S'),
        to_dt.strftime('%H:%M:%S'),
        server_ip=config.OWNTRACKS_SERVER_IP,
        server_port=config.OWNTRACKS_SERVER_PORT,
        user=config.OWNTRACKS_USER,
        device_id=config.OWNTRACKS_DEVICE_ID,
        target_timezone=detected_tz,
        default_timezone=config.DEFAULT_TIMEZONE
    )

    new_points = []
    if new_data:
        # Filter to only points after last_poll timestamp
        for item in new_data:
            if item.get('_type') == 'location' and item.get('tst', 0) > last_poll:
                new_points.append(item)

        # Merge new raw data (avoiding duplicates based on timestamp)
        existing_timestamps = set(item.get('tst') for item in _live_cache['raw_data'])
        for item in new_data:
            if item.get('tst') not in existing_timestamps:
                _live_cache['raw_data'].append(item)
                existing_timestamps.add(item.get('tst'))

    # Update timezone from first GPS point if we haven't yet
    if _live_cache['gps_points'] == [] and new_points:
        first_point = new_points[0]
        detected_tz = get_timezone_from_gps(first_point['lat'], first_point['lon'])
        _live_cache['detected_tz'] = detected_tz
        # Update persisted state with detected timezone
        save_live_state(_live_cache['start_timestamp'], detected_tz.zone)

    # Re-parse all activities from full raw data
    _live_cache['raw_data'].sort(key=lambda x: x.get('tst', 0))
    gps_points, activities = parse_activities(_live_cache['raw_data'])
    activity_stats = calculate_activity_stats(activities) if activities else {}

    _live_cache['gps_points'] = gps_points
    _live_cache['activities'] = activities
    _live_cache['activity_stats'] = activity_stats

    # Only advance last_poll_timestamp if we received new points.
    # Set it to the last point's timestamp, not 'now', so late-arriving
    # data (e.g., batched from iPhone when returning home) will be picked up.
    if new_points:
        last_point_tst = max(p.get('tst', 0) for p in new_points)
        _live_cache['last_poll_timestamp'] = last_point_tst

    # Format stats for response
    stats_response = _format_activity_stats(activity_stats)

    # Format new points for frontend (legacy, kept for debugging)
    new_points_response = [
        {"lat": p["lat"], "lng": p["lon"], "tst": p["tst"]}
        for p in new_points
    ]

    # Get all points to draw (points after last_drawn_timestamp)
    # This ensures no points are missed due to timing issues
    points_to_draw = [
        {"lat": p["lat"], "lng": p["lon"], "tst": p["tst"]}
        for p in gps_points
        if p["tst"] > last_drawn_timestamp
    ]

    # Calculate total distance and duration for tracking display
    total_distance = calculate_track_distance(gps_points)
    total_duration = 0
    last_point_time = None
    if len(gps_points) > 1:
        total_duration = gps_points[-1]["tst"] - gps_points[0]["tst"]
        # Format last point time
        last_tst = gps_points[-1]["tst"]
        last_dt = datetime.fromtimestamp(last_tst, tz=pytz.UTC).astimezone(detected_tz)
        last_point_time = last_dt.strftime('%H:%M:%S')

    return jsonify({
        "success": True,
        "new_points": new_points_response,
        "new_points_count": len(new_points),
        "points_to_draw": points_to_draw,
        "points_to_draw_count": len(points_to_draw),
        "total_points": len(gps_points),
        "total_distance": round(total_distance, 2),
        "total_duration": total_duration,
        "last_point_time": last_point_time,
        "stats": stats_response,
        "last_poll_timestamp": now
    })


@app.route("/api/live/track/<activity_type>")
def get_live_track_data(activity_type):
    """Get track data from live cache (same format as /api/track/<activity_type>)."""
    if not _live_cache.get('is_active') and not _live_cache.get('gps_points'):
        return jsonify({"success": False, "error": "No live data. Start live mode first."}), 400

    activities = _live_cache.get('activities', {})
    gps_points = _live_cache.get('gps_points', [])
    activity_stats = _live_cache.get('activity_stats', {})
    detected_tz = _live_cache.get('detected_tz') or pytz.timezone(config.DEFAULT_TIMEZONE)

    ride_colors = {
        'car': ['#FF0000', '#FF8C00', '#FFD700', '#FF1493', '#8B0000'],
        'bike': ['#FF8C00', '#228B22', '#1E90FF', '#8B4513', '#4B0082', '#DC143C', '#00CED1'],
        'other': ['#800080', '#FF00FF', '#FFA500', '#00FFFF', '#8B4513']
    }

    if activity_type == 'all':
        if not gps_points:
            return jsonify({"success": False, "error": "No GPS points available"}), 404

        layer_distance = calculate_track_distance(gps_points)
        layer_duration = gps_points[-1]["tst"] - gps_points[0]["tst"] if len(gps_points) > 1 else 0

        start_local = datetime.fromtimestamp(gps_points[0]['tst'], tz=pytz.UTC).astimezone(detected_tz)
        end_local = datetime.fromtimestamp(gps_points[-1]['tst'], tz=pytz.UTC).astimezone(detected_tz)

        return jsonify({
            "success": True,
            "activity_type": "all",
            "mode": "basic",
            "points": [{"lat": p["lat"], "lng": p["lon"], "tst": p["tst"]} for p in gps_points],
            "stats": {
                "distance": round(layer_distance, 2),
                "duration": layer_duration,
                "rides": sum(activity_stats.get(a, {}).get('count', 0) for a in ['car', 'bike', 'other']),
                "points": len(gps_points)
            },
            "start_time_str": start_local.strftime('%H:%M:%S'),
            "end_time_str": end_local.strftime('%H:%M:%S')
        })

    if activity_type not in activities or not activities[activity_type]:
        return jsonify({"success": False, "error": f"No {activity_type} activities found"}), 404

    colors = ride_colors.get(activity_type, ['#FFA500'])
    rides_data = []

    for ride_idx, ride in enumerate(activities[activity_type]):
        if not ride['points']:
            continue

        color = colors[ride_idx % len(colors)]
        start_timestamp = ride['start']
        end_timestamp = ride['end']

        start_local = datetime.fromtimestamp(start_timestamp, tz=pytz.UTC).astimezone(detected_tz)
        end_local = datetime.fromtimestamp(end_timestamp, tz=pytz.UTC).astimezone(detected_tz)

        ride_distance = calculate_track_distance(ride['points'])

        ride_duration = end_timestamp - start_timestamp
        avg_speed = (ride_distance / ride_duration * 3600) if ride_duration > 0 else 0

        rides_data.append({
            'ride_number': ride_idx + 1,
            'start_timestamp': start_timestamp,
            'end_timestamp': end_timestamp,
            'start_time_str': start_local.strftime('%H:%M:%S'),
            'end_time_str': end_local.strftime('%H:%M:%S'),
            'start_datetime_str': start_local.strftime('%b %d, %H:%M'),
            'end_datetime_str': end_local.strftime('%b %d, %H:%M'),
            'points': [{"lat": p["lat"], "lng": p["lon"], "tst": p["tst"]} for p in ride['points']],
            'distance': round(ride_distance, 2),
            'duration': ride_duration,
            'avg_speed': round(avg_speed, 1),
            'color': color
        })

    stats = activity_stats.get(activity_type, {})

    return jsonify({
        "success": True,
        "activity_type": activity_type,
        "mode": "rich",
        "rides": rides_data,
        "stats": {
            "distance": round(stats.get('total_distance', 0), 2),
            "duration": stats.get('total_duration', 0),
            "rides": stats.get('count', 0),
            "points": stats.get('total_points', 0)
        }
    })


@app.route("/api/live/stop", methods=["POST"])
def live_stop():
    """Stop live mode polling (but preserve data in cache)."""
    global _live_cache
    _live_cache['is_active'] = False
    return jsonify({"success": True})


@app.route("/api/live/save-map", methods=["POST"])
def live_save_map():
    """Save the current live mode session as an interactive HTML map."""
    if not _live_cache.get('gps_points'):
        return jsonify({"success": False, "error": "No live data to save. Start live mode first."}), 400

    gps_points = _live_cache['gps_points']
    activities = _live_cache.get('activities', {})
    activity_stats = _live_cache.get('activity_stats', {})
    detected_tz = _live_cache.get('detected_tz') or pytz.timezone(config.DEFAULT_TIMEZONE)
    start_timestamp = _live_cache.get('start_timestamp')

    # Determine which layers have data
    active_layers = []
    if gps_points:
        active_layers.append('all')
    for activity_type in ['car', 'bike', 'other']:
        if activity_type in activities and activities[activity_type]:
            active_layers.append(activity_type)

    if not active_layers:
        return jsonify({"success": False, "error": "No layers to save"}), 400

    # Build layer data and ride data for embedding
    saved_layers_data = {}
    saved_rides_data = {}

    ride_colors = {
        'car': ['#FF0000', '#FF8C00', '#FFD700', '#FF1493', '#8B0000'],
        'bike': ['#FF8C00', '#228B22', '#1E90FF', '#8B4513', '#4B0082', '#DC143C', '#00CED1'],
        'other': ['#800080', '#FF00FF', '#FFA500', '#00FFFF', '#8B4513']
    }

    for layer_type in active_layers:
        if layer_type == 'all':
            points = gps_points
        elif layer_type in activities:
            points = []
            for ride in activities[layer_type]:
                points.extend(ride['points'])
            points.sort(key=lambda x: x['tst'])
        else:
            continue

        if not points:
            continue

        if layer_type in activity_stats:
            stats = activity_stats[layer_type]
            layer_distance = stats.get('total_distance', 0)
            layer_duration = stats.get('total_duration', 0)
            layer_rides = stats.get('count', 0)
        else:
            layer_distance = calculate_track_distance(points)
            layer_duration = points[-1]["tst"] - points[0]["tst"] if len(points) > 1 else 0
            layer_rides = sum(activity_stats.get(a, {}).get('count', 0) for a in ['car', 'bike', 'other'])

        start_local = datetime.fromtimestamp(points[0]['tst'], tz=pytz.UTC).astimezone(detected_tz)
        end_local = datetime.fromtimestamp(points[-1]['tst'], tz=pytz.UTC).astimezone(detected_tz)

        saved_layers_data[layer_type] = {
            'points': [{'lat': p['lat'], 'lng': p['lon'], 'tst': p['tst']} for p in points],
            'stats': {
                'distance': layer_distance,
                'duration': layer_duration,
                'rides': layer_rides,
                'points': len(points),
                'start_time_str': start_local.strftime('%H:%M:%S'),
                'end_time_str': end_local.strftime('%H:%M:%S')
            }
        }

        if layer_type in ['car', 'bike', 'other'] and layer_type in activities:
            colors = ride_colors.get(layer_type, ['#FFA500'])
            saved_rides_data[layer_type] = []
            for ride_idx, ride in enumerate(activities[layer_type]):
                if not ride['points']:
                    continue
                s_local = datetime.fromtimestamp(ride['start'], tz=pytz.UTC).astimezone(detected_tz)
                e_local = datetime.fromtimestamp(ride['end'], tz=pytz.UTC).astimezone(detected_tz)
                saved_rides_data[layer_type].append({
                    'start': ride['start'],
                    'end': ride['end'],
                    'points': [{'lat': p['lat'], 'lng': p['lon'], 'tst': p['tst']} for p in ride['points']],
                    'start_time_str': s_local.strftime('%b %d, %H:%M'),
                    'end_time_str': e_local.strftime('%b %d, %H:%M'),
                    'color': colors[ride_idx % len(colors)]
                })

    # Generate filename with date range
    now = datetime.now()
    if start_timestamp:
        start_dt = datetime.fromtimestamp(start_timestamp, tz=pytz.UTC).astimezone(detected_tz)
    else:
        start_dt = datetime.fromtimestamp(gps_points[0]['tst'], tz=pytz.UTC).astimezone(detected_tz)
    end_dt = now

    start_date_str = start_dt.strftime("%Y-%m-%d")
    end_date_str = end_dt.strftime("%Y-%m-%d")

    if start_date_str == end_date_str:
        date_str = start_date_str
    else:
        date_str = f"{start_date_str}_to_{end_date_str}"

    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"interactive_map_live_{date_str}_{timestamp}.html"

    # Generate date range string for display
    date_range_display = f"{start_dt.strftime('%Y-%m-%d %H:%M')} to {end_dt.strftime('%Y-%m-%d %H:%M')}"

    # Generate self-contained HTML
    html = _generate_saved_map_html(
        saved_layers_data, saved_rides_data,
        date_range=date_range_display,
        active_layers=active_layers,
        total_points=len(gps_points),
        saved_timestamp=now.strftime("%Y-%m-%d %H:%M:%S")
    )

    # Save to saved_maps directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    saved_maps_dir = os.path.join(script_dir, "saved_maps")
    os.makedirs(saved_maps_dir, exist_ok=True)
    saved_path = os.path.join(saved_maps_dir, filename)
    with open(saved_path, 'w', encoding='utf-8', newline='') as f:
        f.write(html)

    return jsonify({
        "success": True,
        "filename": filename,
        "path": saved_path,
        "layers": active_layers,
        "total_points": len(gps_points)
    })


@app.route("/api/live/status")
def live_status():
    """Get current live mode status without fetching data.

    Used by frontend to check if a session exists and how old it is
    before deciding to resume or reset.
    """
    # Check for persisted state first (survives container restart)
    saved_state = load_live_state()

    if not saved_state:
        return jsonify({
            "success": True,
            "has_session": False
        })

    start_timestamp = saved_state.get('start_timestamp')
    tz_name = saved_state.get('timezone', config.DEFAULT_TIMEZONE)

    # Calculate session age
    now = int(time.time())
    age_seconds = now - start_timestamp
    age_days = age_seconds / 86400  # seconds per day

    # Session is stale if > 7 days old
    STALE_THRESHOLD_DAYS = 7
    is_stale = age_days > STALE_THRESHOLD_DAYS

    # Format start time for display
    tz = pytz.timezone(tz_name)
    start_dt = datetime.fromtimestamp(start_timestamp, tz=pytz.UTC).astimezone(tz)

    # Check if session is currently active in memory
    is_active = _live_cache.get('is_active', False)
    total_points = len(_live_cache.get('gps_points', []))

    return jsonify({
        "success": True,
        "has_session": True,
        "start_timestamp": start_timestamp,
        "start_time_str": start_dt.strftime('%Y-%m-%d %H:%M:%S'),
        "timezone": tz_name,
        "age_seconds": age_seconds,
        "age_days": round(age_days, 1),
        "is_stale": is_stale,
        "is_active": is_active,
        "total_points": total_points
    })


def _build_timeline(gps_points, activities, lwt_markers, detected_tz):
    timeline = []

    all_activities = []
    for activity_type in ['car', 'bike']:
        if activity_type in activities:
            for activity in activities[activity_type]:
                all_activities.append({
                    'start': activity['start'],
                    'end': activity['end'],
                    'type': activity_type
                })

    all_activities.sort(key=lambda x: x['start'])

    if 'other' in activities and activities['other']:
        first_gps_time = min(p['tst'] for p in gps_points) if gps_points else 0
        current_time = first_gps_time

        for activity in all_activities:
            if current_time < activity['start']:
                timeline.append({
                    'timestamp': current_time,
                    'event': 'other_start',
                    'type': 'generated'
                })
                timeline.append({
                    'timestamp': activity['start'],
                    'event': 'other_end',
                    'type': 'generated'
                })

            timeline.append({
                'timestamp': activity['start'],
                'event': f"{activity['type']}_start",
                'type': 'real'
            })
            timeline.append({
                'timestamp': activity['end'],
                'event': f"{activity['type']}_end",
                'type': 'real'
            })
            current_time = activity['end']

        last_gps_time = max(p['tst'] for p in gps_points) if gps_points else 0
        if current_time < last_gps_time:
            timeline.append({
                'timestamp': current_time,
                'event': 'other_start',
                'type': 'generated'
            })
            timeline.append({
                'timestamp': last_gps_time,
                'event': 'other_end',
                'type': 'generated'
            })
    else:
        for marker in lwt_markers:
            timeline.append({
                'timestamp': marker["tst"],
                'event': marker.get("activity", "unknown"),
                'type': 'real'
            })

    timeline.sort(key=lambda x: x['timestamp'])

    # Format timestamps for display
    for event in timeline:
        ts_utc = datetime.fromtimestamp(event['timestamp'], tz=pytz.UTC)
        ts_local = ts_utc.astimezone(detected_tz)
        event['time'] = ts_local.strftime("%Y-%m-%d %H:%M:%S %Z")

    return timeline


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
