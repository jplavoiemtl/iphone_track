var map;
var activityLayers = {};
var layerVisibility = {};
var layerStats = {};  // Store stats for layer control display

var activityConfig = {
    'car': { color: '#FF4444', icon: '\u{1F697}', name: 'Car' },
    'bike': { color: '#FFD700', icon: '\u{1F6B4}', name: 'Bike' },
    'other': { color: '#4444FF', icon: '\u{1F6B6}', name: 'Other' },
    'all': { color: '#FFA500', icon: '\u{1F4CD}', name: 'All' },
    'live': { color: '#FF00FF', icon: '\u{1F4CD}', name: 'Live' }
};

// Dark mode state
var darkModeEnabled = false;
var darkModePreference = 'auto';  // 'auto', 'dark', 'light'

var DARK_MAP_STYLES = [
    { elementType: 'geometry', stylers: [{ color: '#1a1a2e' }] },
    { elementType: 'labels.text.stroke', stylers: [{ color: '#1a1a2e' }] },
    { elementType: 'labels.text.fill', stylers: [{ color: '#a0a0b8' }] },
    { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#0f3460' }] },
    { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#16213e' }] },
    { featureType: 'road.arterial', elementType: 'geometry', stylers: [{ color: '#1a4a7a' }] },
    { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#2a5a9a' }] },
    { featureType: 'road.highway', elementType: 'geometry.stroke', stylers: [{ color: '#0f3460' }] },
    { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0a1628' }] },
    { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#4a6fa5' }] },
    { featureType: 'poi', elementType: 'geometry', stylers: [{ color: '#16213e' }] },
    { featureType: 'poi.park', elementType: 'geometry', stylers: [{ color: '#0d2b1a' }] },
    { featureType: 'transit', elementType: 'geometry', stylers: [{ color: '#0f2235' }] },
    { featureType: 'administrative', elementType: 'geometry.stroke', stylers: [{ color: '#4a6fa5' }] },
    { featureType: 'administrative.land_parcel', elementType: 'labels', stylers: [{ visibility: 'off' }] }
];

function initMap() {
    map = new google.maps.Map(document.getElementById('map'), {
        center: { lat: 45.5017, lng: -73.5673 },
        zoom: 12,
        mapTypeId: 'roadmap'
    });
    createLayerControl();
    createDarkModeControl();
    _initDarkModePreference();
}

function clearAllLayers() {
    Object.keys(activityLayers).forEach(function (key) {
        var layer = activityLayers[key];
        layer.paths.forEach(function (p) { p.setMap(null); });
        layer.markers.forEach(function (m) { m.setMap(null); });
    });
    activityLayers = {};
    layerVisibility = {};
    layerStats = {};

    // Also clear live layer polyline
    if (livePolyline) {
        livePolyline.setMap(null);
        livePolyline = null;
        livePolylinePath = null;
    }

    updateLayerControl();
}

function clearDatetimeLayers() {
    // Clear all layers except the live layer
    Object.keys(activityLayers).forEach(function (key) {
        if (key === 'live') return;  // Skip live layer
        var layer = activityLayers[key];
        layer.paths.forEach(function (p) { p.setMap(null); });
        layer.markers.forEach(function (m) { m.setMap(null); });
        delete activityLayers[key];
        delete layerVisibility[key];
        delete layerStats[key];
    });

    updateLayerControl();
}

function clearActivityLayer(activityType) {
    // Clear a specific activity layer (used for live mode redraw)
    if (!activityLayers[activityType]) return;

    var layer = activityLayers[activityType];
    layer.paths.forEach(function (p) { p.setMap(null); });
    layer.markers.forEach(function (m) { m.setMap(null); });
    delete activityLayers[activityType];
    delete layerVisibility[activityType];
    delete layerStats[activityType];

    updateLayerControl();
}

function addRichLayer(activityType, ridesData, statsData, skipFitBounds) {
    if (!activityLayers[activityType]) {
        activityLayers[activityType] = { paths: [], markers: [], visible: true };
        layerVisibility[activityType] = true;
    }

    var config = activityConfig[activityType] || activityConfig['all'];
    var layer = activityLayers[activityType];

    // Store stats for layer control display
    if (statsData) {
        layerStats[activityType] = {
            distance: statsData.distance || 0,
            duration: statsData.duration || 0,
            rides: statsData.rides || ridesData.length,
            points: statsData.points || 0
        };
    }

    ridesData.forEach(function (ride) {
        for (var i = 1; i < ride.points.length; i++) {
            var pathSegment = new google.maps.Polyline({
                path: [
                    { lat: ride.points[i - 1].lat, lng: ride.points[i - 1].lng },
                    { lat: ride.points[i].lat, lng: ride.points[i].lng }
                ],
                geodesic: true,
                strokeColor: ride.color,
                strokeOpacity: 0.8,
                strokeWeight: 4,
                map: layer.visible ? map : null
            });
            layer.paths.push(pathSegment);
        }

        addRideMarkers(activityType, ride, layer);
    });

    if (!skipFitBounds) {
        fitBoundsToRides(ridesData);
    }
    updateLayerControl();
}

function addBasicLayer(activityType, points, stats, startTimeStr, endTimeStr) {
    if (!activityLayers[activityType]) {
        activityLayers[activityType] = { paths: [], markers: [], visible: true };
        layerVisibility[activityType] = true;
    }

    var config = activityConfig[activityType] || activityConfig['all'];
    var layer = activityLayers[activityType];

    // Store stats for layer control display
    if (stats) {
        layerStats[activityType] = {
            distance: stats.distance || 0,
            duration: stats.duration || 0,
            rides: stats.rides || 1,
            points: stats.points || points.length
        };
    }

    for (var i = 1; i < points.length; i++) {
        var pathSegment = new google.maps.Polyline({
            path: [
                { lat: points[i - 1].lat, lng: points[i - 1].lng },
                { lat: points[i].lat, lng: points[i].lng }
            ],
            geodesic: true,
            strokeColor: config.color,
            strokeOpacity: 0.8,
            strokeWeight: 4,
            map: layer.visible ? map : null
        });
        layer.paths.push(pathSegment);
    }

    if (points.length > 0) {
        var startMarker = new google.maps.Marker({
            position: { lat: points[0].lat, lng: points[0].lng },
            map: layer.visible ? map : null,
            title: config.name + ' Activity Start',
            icon: {
                path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                scale: 6,
                fillColor: config.color,
                fillOpacity: 1,
                strokeColor: '#FFFFFF',
                strokeWeight: 2
            },
            zIndex: 1000
        });

        var startInfo = new google.maps.InfoWindow({
            content: '<div style="font-size:12px;"><strong>' + config.name + ' Start</strong><br>' + startTimeStr + '</div>'
        });
        startMarker.addListener('click', function () { startInfo.open(map, startMarker); });
        layer.markers.push(startMarker);

        var durationHours = Math.floor(stats.duration / 3600);
        var durationMins = Math.floor((stats.duration % 3600) / 60);
        var avgSpeed = stats.duration > 0 ? (stats.distance / stats.duration * 3600) : 0;

        var endContent = '<div style="font-size:12px; min-width:150px;"><strong>' + config.name + ' End</strong><br>' +
            'Time: ' + endTimeStr + '<br>' +
            'Distance: ' + stats.distance.toFixed(2) + ' km<br>' +
            'Duration: ' + durationHours + 'h ' + durationMins + 'm<br>' +
            'Avg Speed: ' + avgSpeed.toFixed(1) + ' km/h<br>' +
            'Rides: ' + stats.rides + '<br>' +
            'Points: ' + stats.points + '</div>';

        var endMarker = new google.maps.Marker({
            position: { lat: points[points.length - 1].lat, lng: points[points.length - 1].lng },
            map: layer.visible ? map : null,
            title: config.name + ' Activity End',
            icon: {
                path: google.maps.SymbolPath.CIRCLE,
                scale: 10,
                fillColor: config.color,
                fillOpacity: 0.9,
                strokeColor: '#FFFFFF',
                strokeWeight: 3
            },
            zIndex: 999
        });

        var endInfo = new google.maps.InfoWindow({ content: endContent });
        endMarker.addListener('click', function () { endInfo.open(map, endMarker); });
        layer.markers.push(endMarker);

        var bounds = new google.maps.LatLngBounds();
        points.forEach(function (p) { bounds.extend(new google.maps.LatLng(p.lat, p.lng)); });
        map.fitBounds(bounds);
    }

    updateLayerControl();
}

function addRideMarkers(activityType, ride, layer) {
    var config = activityConfig[activityType] || activityConfig['all'];
    if (ride.points.length === 0) return;

    var startPoint = ride.points[0];
    for (var i = 0; i < ride.points.length; i++) {
        if (ride.points[i].tst >= ride.start_timestamp) {
            startPoint = ride.points[i];
            break;
        }
    }

    var endPoint = ride.points[ride.points.length - 1];
    for (var i = ride.points.length - 1; i >= 0; i--) {
        if (ride.points[i].tst <= ride.end_timestamp) {
            endPoint = ride.points[i];
            break;
        }
    }

    var durationHours = Math.floor(ride.duration / 3600);
    var durationMins = Math.floor((ride.duration % 3600) / 60);

    // Use datetime strings (with date) if available, fall back to time-only
    var startTimeDisplay = ride.start_datetime_str || ride.start_time_str;
    var endTimeDisplay = ride.end_datetime_str || ride.end_time_str;

    var startContent = '<div style="font-size:12px; min-width:150px;">' +
        config.name + ' Ride ' + ride.ride_number + '<br>Start: ' + startTimeDisplay + '</div>';

    var endContent = '<div style="font-size:12px; min-width:150px;">' +
        config.name + ' Ride ' + ride.ride_number + '<br>' +
        'End: ' + endTimeDisplay + '<br>' +
        'Distance: ' + ride.distance.toFixed(2) + ' km<br>' +
        'Duration: ' + durationHours + 'h ' + durationMins + 'm<br>' +
        'Avg Speed: ' + ride.avg_speed.toFixed(1) + ' km/h<br>' +
        'Points: ' + ride.points.length + '</div>';

    var startMarker = new google.maps.Marker({
        position: { lat: startPoint.lat, lng: startPoint.lng },
        map: layer.visible ? map : null,
        title: config.name + ' Ride ' + ride.ride_number + ' Start',
        icon: {
            path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
            scale: 6,
            fillColor: ride.color,
            fillOpacity: 1,
            strokeColor: '#FFFFFF',
            strokeWeight: 2,
            rotation: 0
        },
        zIndex: 1000 + ride.ride_number
    });

    var startInfoWindow = new google.maps.InfoWindow({ content: startContent });
    startMarker.addListener('click', function () { startInfoWindow.open(map, startMarker); });
    layer.markers.push(startMarker);

    var endMarker = new google.maps.Marker({
        position: { lat: endPoint.lat, lng: endPoint.lng },
        map: layer.visible ? map : null,
        title: config.name + ' Ride ' + ride.ride_number + ' End',
        icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 8,
            fillColor: ride.color,
            fillOpacity: 0.9,
            strokeColor: '#FFFFFF',
            strokeWeight: 2
        },
        zIndex: 999 + ride.ride_number
    });

    var endInfoWindow = new google.maps.InfoWindow({ content: endContent });
    endMarker.addListener('click', function () { endInfoWindow.open(map, endMarker); });
    layer.markers.push(endMarker);
}

// ============================================================
// Animation config - change this single value to adjust speed
// Higher = slower animation. Represents ms per GPS point.
// The total animation time is capped at ANIMATION_MAX_TOTAL_MS.
// ============================================================
var ANIMATION_MS_PER_POINT = 200;
var ANIMATION_MAX_TOTAL_MS = 60000;

// Animation state
var animationTimer = null;
var animationPaused = false;
var animationResumeFunc = null;
var animationRunning = false;

// Playback state (module-level so step functions can access)
var animationDrawnSegments = [];  // { polyline, distance } for undo
var animationCurrentIdx = 0;
var animationRunningDistance = 0;
var animationLayer = null;
var animationSegments = null;     // rich: array of {ride,idx}; basic: array of points
var animationFirstTimestamp = 0;
var animationDelayMs = 50;
var animationMode = null;         // 'rich' or 'basic'
var animationOnComplete = null;
var animationRidesData = null;
var animationActivityType = null;
var animationBasicStats = null;
var animationBasicConfig = null;
var animationBasicEndTimeStr = null;

function stopAnimation() {
    if (animationTimer) {
        clearTimeout(animationTimer);
        animationTimer = null;
    }
    animationPaused = false;
    animationResumeFunc = null;
    animationRunning = false;
    animationDrawnSegments = [];
    animationCurrentIdx = 0;
    animationRunningDistance = 0;
    animationLayer = null;
    animationSegments = null;
    animationMode = null;
    animationOnComplete = null;
    animationRidesData = null;
    animationActivityType = null;
    animationBasicStats = null;
    animationBasicConfig = null;
    animationBasicEndTimeStr = null;
    updatePauseStatus('');
    hidePlaybackControls();
}

function togglePause() {
    if (!animationRunning) return;

    if (animationPaused) {
        // Resume
        animationPaused = false;
        updatePauseStatus('Tracking...');
        updatePlaybackButtons();
        if (animationResumeFunc) {
            var fn = animationResumeFunc;
            animationResumeFunc = null;
            fn();
        }
    } else {
        // Pause
        animationPaused = true;
        if (animationTimer) {
            clearTimeout(animationTimer);
            animationTimer = null;
        }
        updatePauseStatus('PAUSED');
        updatePlaybackButtons();
    }
}

function updatePauseStatus(text) {
    var el = document.getElementById('pause-status');
    if (el) el.textContent = text;
}

// Playback controls UI
function showPlaybackControls() {
    var el = document.getElementById('playback-controls');
    if (el) {
        el.style.display = 'flex';
        var btn = document.getElementById('pause-play-btn');
        if (btn) btn.textContent = 'Pause';
        var back = document.getElementById('step-back-btn');
        var fwd = document.getElementById('step-forward-btn');
        if (back) back.disabled = true;
        if (fwd) fwd.disabled = true;
    }
}

function hidePlaybackControls() {
    var el = document.getElementById('playback-controls');
    if (el) el.style.display = 'none';
}

function updatePlaybackButtons() {
    var btn = document.getElementById('pause-play-btn');
    var back = document.getElementById('step-back-btn');
    var fwd = document.getElementById('step-forward-btn');
    if (!btn) return;

    if (animationPaused) {
        btn.textContent = 'Play';
        if (back) back.disabled = (animationDrawnSegments.length === 0);
        if (fwd) fwd.disabled = !_hasMoreSegments();
    } else {
        btn.textContent = 'Pause';
        if (back) back.disabled = true;
        if (fwd) fwd.disabled = true;
    }
}

function _hasMoreSegments() {
    if (!animationSegments) return false;
    if (animationMode === 'rich') {
        return animationCurrentIdx < animationSegments.length;
    } else {
        return animationCurrentIdx < animationSegments.length;
    }
}

function _fireProgress() {
    if (!onAnimationProgress) return;
    var totalPts = animationSegments ? animationSegments.length : 0;
    var elapsed = 0;
    var lat = 0, lng = 0, tst = 0;

    if (animationMode === 'rich' && animationDrawnSegments.length > 0) {
        var lastDrawn = animationDrawnSegments[animationDrawnSegments.length - 1];
        lat = lastDrawn.lat;
        lng = lastDrawn.lng;
        tst = lastDrawn.tst;
        elapsed = tst - animationFirstTimestamp;
    } else if (animationMode === 'basic' && animationDrawnSegments.length > 0) {
        var lastDrawn = animationDrawnSegments[animationDrawnSegments.length - 1];
        lat = lastDrawn.lat;
        lng = lastDrawn.lng;
        tst = lastDrawn.tst;
        elapsed = tst - animationFirstTimestamp;
    }

    var speed = elapsed > 0 ? (animationRunningDistance / elapsed * 3600) : 0;
    onAnimationProgress({
        distance: animationRunningDistance,
        duration: elapsed,
        speed: speed,
        pointIndex: animationCurrentIdx,
        totalPoints: totalPts,
        lat: lat,
        lng: lng,
        timestamp: tst
    });
}

function stepBack() {
    if (!animationPaused || !animationRunning) return;
    if (animationDrawnSegments.length === 0) return;

    var entry = animationDrawnSegments.pop();
    entry.polyline.setMap(null);

    // Remove from layer.paths
    if (animationLayer) {
        var idx = animationLayer.paths.indexOf(entry.polyline);
        if (idx !== -1) animationLayer.paths.splice(idx, 1);
    }

    animationCurrentIdx--;
    animationRunningDistance -= entry.distance;
    if (animationRunningDistance < 0) animationRunningDistance = 0;

    // Pan to current position
    if (animationDrawnSegments.length > 0) {
        var last = animationDrawnSegments[animationDrawnSegments.length - 1];
        map.panTo({ lat: last.lat, lng: last.lng });
    }

    _fireProgress();
    updatePlaybackButtons();
}

function stepForward() {
    if (!animationPaused || !animationRunning) return;
    if (!_hasMoreSegments()) return;

    // Draw one segment
    _drawOneSegment();
    _fireProgress();
    updatePlaybackButtons();
}

function _drawOneSegment() {
    if (animationMode === 'rich') {
        _drawOneRichSegment();
    } else {
        _drawOneBasicSegment();
    }
}

function _drawOneRichSegment() {
    if (animationCurrentIdx >= animationSegments.length) return;

    var seg = animationSegments[animationCurrentIdx];
    var ride = seg.ride;
    var i = seg.idx;

    var pathSegment = new google.maps.Polyline({
        path: [
            { lat: ride.points[i - 1].lat, lng: ride.points[i - 1].lng },
            { lat: ride.points[i].lat, lng: ride.points[i].lng }
        ],
        geodesic: true,
        strokeColor: ride.color,
        strokeOpacity: 0.8,
        strokeWeight: 4,
        map: map
    });
    animationLayer.paths.push(pathSegment);

    var segDist = _haversineJs(
        ride.points[i - 1].lat, ride.points[i - 1].lng,
        ride.points[i].lat, ride.points[i].lng);
    animationRunningDistance += segDist;

    animationDrawnSegments.push({
        polyline: pathSegment,
        distance: segDist,
        lat: ride.points[i].lat,
        lng: ride.points[i].lng,
        tst: ride.points[i].tst
    });

    map.panTo({ lat: ride.points[i].lat, lng: ride.points[i].lng });
    animationCurrentIdx++;
}

function _drawOneBasicSegment() {
    var points = animationSegments;
    if (animationCurrentIdx >= points.length) return;

    var pathSegment = new google.maps.Polyline({
        path: [
            { lat: points[animationCurrentIdx - 1].lat, lng: points[animationCurrentIdx - 1].lng },
            { lat: points[animationCurrentIdx].lat, lng: points[animationCurrentIdx].lng }
        ],
        geodesic: true,
        strokeColor: animationBasicConfig.color,
        strokeOpacity: 0.8,
        strokeWeight: 4,
        map: map
    });
    animationLayer.paths.push(pathSegment);

    var segDist = _haversineJs(
        points[animationCurrentIdx - 1].lat, points[animationCurrentIdx - 1].lng,
        points[animationCurrentIdx].lat, points[animationCurrentIdx].lng);
    animationRunningDistance += segDist;

    animationDrawnSegments.push({
        polyline: pathSegment,
        distance: segDist,
        lat: points[animationCurrentIdx].lat,
        lng: points[animationCurrentIdx].lng,
        tst: points[animationCurrentIdx].tst
    });

    map.panTo({ lat: points[animationCurrentIdx].lat, lng: points[animationCurrentIdx].lng });
    animationCurrentIdx++;
}

// Callback for live stats updates during animation
var onAnimationProgress = null;

function _calcDelay(totalSegments) {
    var totalMs = Math.min(totalSegments * ANIMATION_MS_PER_POINT, ANIMATION_MAX_TOTAL_MS);
    return Math.max(Math.floor(totalMs / totalSegments), 10);
}

// Haversine in JS for live distance tracking
function _haversineJs(lat1, lon1, lat2, lon2) {
    var R = 6371;
    var dLat = (lat2 - lat1) * Math.PI / 180;
    var dLon = (lon2 - lon1) * Math.PI / 180;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    var d = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return d >= 0.01 ? d * 1.05 : 0;
}

function addRichLayerAnimated(activityType, ridesData, statsData, onComplete) {
    if (!activityLayers[activityType]) {
        activityLayers[activityType] = { paths: [], markers: [], visible: true };
        layerVisibility[activityType] = true;
    }

    var layer = activityLayers[activityType];

    // Store stats for layer control display
    if (statsData) {
        layerStats[activityType] = {
            distance: statsData.distance || 0,
            duration: statsData.duration || 0,
            rides: statsData.rides || ridesData.length,
            points: statsData.points || 0
        };
    }

    // Flatten all segments across rides
    var segments = [];
    ridesData.forEach(function (ride) {
        for (var i = 1; i < ride.points.length; i++) {
            segments.push({ ride: ride, idx: i });
        }
    });

    if (segments.length === 0) {
        if (onComplete) onComplete();
        return;
    }

    fitBoundsToRides(ridesData);

    if (ridesData.length > 0 && ridesData[0].points.length > 0) {
        var firstPt = ridesData[0].points[0];
        map.setCenter({ lat: firstPt.lat, lng: firstPt.lng });
        map.setZoom(15);
    }

    var delayMs = _calcDelay(segments.length);

    // Store in module-level state for step controls
    animationMode = 'rich';
    animationSegments = segments;
    animationCurrentIdx = 0;
    animationRunningDistance = 0;
    animationDrawnSegments = [];
    animationLayer = layer;
    animationFirstTimestamp = segments[0].ride.points[0].tst;
    animationDelayMs = delayMs;
    animationOnComplete = onComplete;
    animationRidesData = ridesData;
    animationActivityType = activityType;
    animationRunning = true;
    animationPaused = false;
    updatePauseStatus('Tracking...');
    showPlaybackControls();

    function drawNext() {
        if (animationPaused) {
            animationResumeFunc = drawNext;
            return;
        }

        if (animationCurrentIdx >= segments.length) {
            ridesData.forEach(function (ride) {
                addRideMarkers(activityType, ride, layer);
            });
            updateLayerControl();
            animationRunning = false;
            updatePauseStatus('');
            hidePlaybackControls();
            if (animationOnComplete) animationOnComplete();
            animationTimer = null;
            return;
        }

        _drawOneRichSegment();
        _fireProgress();

        animationResumeFunc = drawNext;
        animationTimer = setTimeout(drawNext, delayMs);
    }

    drawNext();
}

function addBasicLayerAnimated(activityType, points, stats, startTimeStr, endTimeStr, onComplete) {
    if (!activityLayers[activityType]) {
        activityLayers[activityType] = { paths: [], markers: [], visible: true };
        layerVisibility[activityType] = true;
    }

    var config = activityConfig[activityType] || activityConfig['all'];
    var layer = activityLayers[activityType];

    // Store stats for layer control display
    if (stats) {
        layerStats[activityType] = {
            distance: stats.distance || 0,
            duration: stats.duration || 0,
            rides: stats.rides || 1,
            points: stats.points || points.length
        };
    }

    if (points.length === 0) {
        if (onComplete) onComplete();
        return;
    }

    map.setCenter({ lat: points[0].lat, lng: points[0].lng });
    map.setZoom(15);

    // Add start marker immediately
    var startMarker = new google.maps.Marker({
        position: { lat: points[0].lat, lng: points[0].lng },
        map: map,
        title: config.name + ' Activity Start',
        icon: {
            path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
            scale: 6,
            fillColor: config.color,
            fillOpacity: 1,
            strokeColor: '#FFFFFF',
            strokeWeight: 2
        },
        zIndex: 1000
    });
    var startInfo = new google.maps.InfoWindow({
        content: '<div style="font-size:12px;"><strong>' + config.name + ' Start</strong><br>' + startTimeStr + '</div>'
    });
    startMarker.addListener('click', function () { startInfo.open(map, startMarker); });
    layer.markers.push(startMarker);

    var delayMs = _calcDelay(points.length);

    // Store in module-level state for step controls
    animationMode = 'basic';
    animationSegments = points;
    animationCurrentIdx = 1;
    animationRunningDistance = 0;
    animationDrawnSegments = [];
    animationLayer = layer;
    animationFirstTimestamp = points[0].tst;
    animationDelayMs = delayMs;
    animationOnComplete = onComplete;
    animationActivityType = activityType;
    animationBasicStats = stats;
    animationBasicConfig = config;
    animationBasicEndTimeStr = endTimeStr;
    animationRunning = true;
    animationPaused = false;
    updatePauseStatus('Tracking...');
    showPlaybackControls();

    function drawNext() {
        if (animationPaused) {
            animationResumeFunc = drawNext;
            return;
        }

        if (animationCurrentIdx >= points.length) {
            var durationHours = Math.floor(stats.duration / 3600);
            var durationMins = Math.floor((stats.duration % 3600) / 60);
            var avgSpeed = stats.duration > 0 ? (stats.distance / stats.duration * 3600) : 0;

            var endContent = '<div style="font-size:12px; min-width:150px;"><strong>' + config.name + ' End</strong><br>' +
                'Time: ' + endTimeStr + '<br>' +
                'Distance: ' + stats.distance.toFixed(2) + ' km<br>' +
                'Duration: ' + durationHours + 'h ' + durationMins + 'm<br>' +
                'Avg Speed: ' + avgSpeed.toFixed(1) + ' km/h<br>' +
                'Rides: ' + stats.rides + '<br>' +
                'Points: ' + stats.points + '</div>';

            var endMarker = new google.maps.Marker({
                position: { lat: points[points.length - 1].lat, lng: points[points.length - 1].lng },
                map: map,
                title: config.name + ' Activity End',
                icon: {
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 10,
                    fillColor: config.color,
                    fillOpacity: 0.9,
                    strokeColor: '#FFFFFF',
                    strokeWeight: 3
                },
                zIndex: 999
            });
            var endInfo = new google.maps.InfoWindow({ content: endContent });
            endMarker.addListener('click', function () { endInfo.open(map, endMarker); });
            layer.markers.push(endMarker);

            updateLayerControl();
            animationRunning = false;
            updatePauseStatus('');
            hidePlaybackControls();
            if (animationOnComplete) animationOnComplete();
            animationTimer = null;
            return;
        }

        _drawOneBasicSegment();
        _fireProgress();

        animationResumeFunc = drawNext;
        animationTimer = setTimeout(drawNext, delayMs);
    }

    drawNext();
}

function fitBoundsToRides(ridesData) {
    if (ridesData.length > 0) {
        var bounds = new google.maps.LatLngBounds();
        ridesData.forEach(function (ride) {
            ride.points.forEach(function (point) {
                bounds.extend(new google.maps.LatLng(point.lat, point.lng));
            });
        });
        map.fitBounds(bounds);
    }
}

function toggleLayer(activityType) {
    if (!activityLayers[activityType]) return;

    var layer = activityLayers[activityType];
    var isVisible = !layer.visible;
    layer.visible = isVisible;
    layerVisibility[activityType] = isVisible;

    layer.paths.forEach(function (path) { path.setMap(isVisible ? map : null); });
    layer.markers.forEach(function (marker) { marker.setMap(isVisible ? map : null); });

    updateLayerControl();
}

var layerPanelCollapsed = false;

function createLayerControl() {
    var controlDiv = document.createElement('div');
    controlDiv.id = 'mapLayerControl';
    controlDiv.innerHTML =
        '<div id="layerPanelOuter" style="background:rgba(255,255,255,0.95);border:2px solid #666;border-radius:8px;margin:8px 4px;padding:8px 10px;font-family:Arial,sans-serif;font-size:12px;box-shadow:0 3px 10px rgba(0,0,0,0.3);max-width:calc(100vw - 70px);">' +
        '<div id="layerPanelHeader" style="display:flex;align-items:center;justify-content:space-between;cursor:pointer;padding:2px 0;" onclick="toggleLayerPanel()">' +
            '<span style="font-weight:bold;color:#333;font-size:13px;">Active Layers</span>' +
            '<span id="layerPanelArrow" style="font-size:10px;color:#666;margin-left:8px;">&#9660;</span>' +
        '</div>' +
        '<div id="layerPanelBody">' +
            '<div id="mapLayerList" style="margin-top:6px;"></div>' +
            '<div id="history-panel" style="display:none;border-top:1px solid #ddd;margin-top:6px;padding-top:6px;">' +
                '<div id="history-label" class="history-label live" style="font-weight:bold;color:#333;margin-bottom:4px;"></div>' +
                '<div id="history-time" style="color:#666;margin-bottom:3px;"></div>' +
                '<div style="color:#555;font-size:11px;margin-bottom:6px;">' +
                    '<span id="history-distance">0 km</span> | ' +
                    '<span id="history-duration">0m</span> | ' +
                    '<span id="history-speed">0 km/h</span>' +
                '</div>' +
                '<div style="display:flex;justify-content:center;gap:4px;">' +
                    '<button id="history-back10" onclick="navigateHistory(-10)" style="padding:4px 8px;border:1px solid #ccc;border-radius:4px;background:#f5f5f5;cursor:pointer;font-size:12px;" title="Back 10 points">&#171;&#171;</button>' +
                    '<button id="history-back" onclick="navigateHistory(-1)" style="padding:4px 8px;border:1px solid #ccc;border-radius:4px;background:#f5f5f5;cursor:pointer;font-size:12px;" title="Back 1 point">&#171;</button>' +
                    '<button id="history-live" onclick="handleHistoryJumpButton()" style="display:none;padding:4px 10px;border:none;border-radius:4px;background:#4285F4;color:white;cursor:pointer;font-size:11px;font-weight:bold;">LIVE</button>' +
                    '<button id="history-forward" onclick="navigateHistory(1)" style="padding:4px 8px;border:1px solid #ccc;border-radius:4px;background:#f5f5f5;cursor:pointer;font-size:12px;" title="Forward 1 point">&#187;</button>' +
                    '<button id="history-forward10" onclick="navigateHistory(10)" style="padding:4px 8px;border:1px solid #ccc;border-radius:4px;background:#f5f5f5;cursor:pointer;font-size:12px;" title="Forward 10 points">&#187;&#187;</button>' +
                '</div>' +
            '</div>' +
        '</div>' +
        '</div>';
    map.controls[google.maps.ControlPosition.LEFT_TOP].push(controlDiv);
}

function toggleLayerPanel() {
    layerPanelCollapsed = !layerPanelCollapsed;
    var body = document.getElementById('layerPanelBody');
    var arrow = document.getElementById('layerPanelArrow');
    if (body) body.style.display = layerPanelCollapsed ? 'none' : 'block';
    if (arrow) arrow.innerHTML = layerPanelCollapsed ? '&#9654;' : '&#9660;';
}

function updateLayerControl() {
    var layerList = document.getElementById('mapLayerList');
    if (!layerList) return;

    layerList.innerHTML = '';

    Object.keys(activityLayers).forEach(function (activityType) {
        var layer = activityLayers[activityType];
        if (layer.paths.length > 0 || layer.markers.length > 0) {
            var config = activityConfig[activityType] || activityConfig['all'];
            var isVisible = layerVisibility[activityType];
            var stats = layerStats[activityType];

            // Single compact row per layer
            var rowBg = darkModeEnabled ? 'rgba(15, 52, 96, 0.6)' : 'rgba(248,248,248,0.8)';
            var rowBorder = darkModeEnabled ? '1px solid #16213e' : '1px solid #e0e0e0';
            var nameColor = darkModeEnabled ? '#e0e0e0' : '#333';
            var statsColor = darkModeEnabled ? '#a0a0b8' : '#666';

            var row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;padding:4px 6px;background:' + rowBg + ';border-radius:6px;border:' + rowBorder + ';margin:4px 0;gap:6px;';

            var buttonId = activityType === 'live' ? 'id="live-layer-toggle"' : '';

            // Build stats string if available
            var statsHtml = '';
            if (stats) {
                var durationMins = Math.floor(stats.duration / 60);
                var durationStr = durationMins >= 60 ?
                    Math.floor(durationMins / 60) + 'h' + (durationMins % 60) + 'm' :
                    durationMins + 'm';
                var avgSpeed = stats.duration > 0 ? (stats.distance / stats.duration * 3600) : 0;
                statsHtml = '<span style="color:' + statsColor + ';font-size:10px;white-space:nowrap;">' +
                    stats.distance.toFixed(1) + 'km ' + durationStr + ' ' + avgSpeed.toFixed(0) + 'km/h</span>';
            }

            row.innerHTML =
                '<span style="font-size:14px;width:18px;text-align:center;flex-shrink:0;">' + config.icon + '</span>' +
                '<span style="font-weight:500;color:' + nameColor + ';font-size:12px;white-space:nowrap;">' + config.name + '</span>' +
                (statsHtml ? statsHtml : '') +
                '<button ' + buttonId + ' onclick="toggleLayer(\'' + activityType + '\')" style="margin-left:auto;padding:2px 6px;border:none;border-radius:3px;color:white;font-size:9px;font-weight:bold;cursor:pointer;flex-shrink:0;background-color:' + config.color + ';opacity:' + (isVisible ? '1' : '0.5') + ';">' +
                (isVisible ? 'Hide' : 'Show') + '</button>';

            layerList.appendChild(row);
        }
    });
}

// =============================================================================
// Dark Mode Functions
// =============================================================================

function createDarkModeControl() {
    var btn = document.createElement('button');
    btn.id = 'dark-mode-toggle';
    btn.title = 'Toggle dark/light map (Auto)';
    btn.style.cssText = 'margin:8px;width:40px;height:40px;border:none;border-radius:8px;' +
        'background:rgba(22,33,62,0.95);color:white;font-size:16px;cursor:pointer;' +
        'box-shadow:0 2px 6px rgba(0,0,0,0.4);';
    btn.textContent = 'A';
    btn.addEventListener('click', function() {
        cycleDarkMode();
    });
    map.controls[google.maps.ControlPosition.LEFT_BOTTOM].push(btn);
}

function _initDarkModePreference() {
    try { darkModePreference = localStorage.getItem('darkMode') || 'auto'; } catch(e) {}

    var enable;
    if (darkModePreference === 'dark') {
        enable = true;
    } else if (darkModePreference === 'light') {
        enable = false;
    } else {
        // Auto: dark from 8pm to 6am
        var hour = new Date().getHours();
        enable = (hour >= 20 || hour < 6);
    }

    _updateDarkModeButton();
    if (enable) applyDarkMode(true);
}

function cycleDarkMode() {
    // Auto -> Dark -> Light -> Auto
    if (darkModePreference === 'auto') {
        darkModePreference = 'dark';
        applyDarkMode(true);
    } else if (darkModePreference === 'dark') {
        darkModePreference = 'light';
        applyDarkMode(false);
    } else {
        darkModePreference = 'auto';
        var hour = new Date().getHours();
        applyDarkMode(hour >= 20 || hour < 6);
    }

    _updateDarkModeButton();
    try { localStorage.setItem('darkMode', darkModePreference); } catch(e) {}
}

function _updateDarkModeButton() {
    var btn = document.getElementById('dark-mode-toggle');
    if (!btn) return;

    if (darkModePreference === 'auto') {
        btn.textContent = 'A';
        btn.title = 'Map theme: Auto (tap to change)';
    } else if (darkModePreference === 'dark') {
        btn.textContent = '\uD83C\uDF19';  // moon (current: dark)
        btn.title = 'Map theme: Dark (tap for Light)';
    } else {
        btn.textContent = '\u2600\uFE0F';  // sun (current: light)
        btn.title = 'Map theme: Light (tap for Auto)';
    }
}

function applyDarkMode(enable) {
    darkModeEnabled = enable;

    // Apply/remove map styles
    map.setOptions({ styles: enable ? DARK_MAP_STYLES : [] });

    // Update layer panel colors
    var outer = document.getElementById('layerPanelOuter');
    if (outer) {
        outer.style.background = enable ? 'rgba(22, 33, 62, 0.95)' : 'rgba(255,255,255,0.95)';
        outer.style.border = enable ? '2px solid #0f3460' : '2px solid #666';
    }

    // Update layer panel text colors
    _updateLayerPanelTextColors(enable);

    // Rebuild layer rows with correct colors
    updateLayerControl();
}

function _updateLayerPanelTextColors(enable) {
    var textColor = enable ? '#e0e0e0' : '#333';
    var dimColor = enable ? '#a0a0b8' : '#666';
    var borderColor = enable ? '#0f3460' : '#ddd';

    // Header
    var header = document.getElementById('layerPanelHeader');
    if (header) {
        var title = header.querySelector('span');
        if (title) title.style.color = textColor;
    }
    var arrow = document.getElementById('layerPanelArrow');
    if (arrow) arrow.style.color = dimColor;

    // History panel
    var historyPanel = document.getElementById('history-panel');
    if (historyPanel) historyPanel.style.borderTop = '1px solid ' + borderColor;

    var ids = ['history-label', 'history-time'];
    ids.forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.style.color = id === 'history-label' ? textColor : dimColor;
    });

    var statsIds = ['history-distance', 'history-duration', 'history-speed'];
    statsIds.forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.parentElement.style.color = enable ? '#b0b0c8' : '#555';
    });

    // History buttons
    var btnIds = ['history-back10', 'history-back', 'history-forward', 'history-forward10'];
    btnIds.forEach(function(id) {
        var el = document.getElementById(id);
        if (el) {
            el.style.background = enable ? '#0f3460' : '#f5f5f5';
            el.style.border = enable ? '1px solid #1a4a7a' : '1px solid #ccc';
            el.style.color = enable ? '#e0e0e0' : '';
        }
    });
}

// =============================================================================
// Live Mode Layer Functions
// =============================================================================

var livePolyline = null;
var livePolylinePath = null;

function initLiveLayer() {
    // Create a single polyline for live mode that we can append to
    if (livePolyline) {
        // Already initialized
        return;
    }

    livePolylinePath = new google.maps.MVCArray();
    livePolyline = new google.maps.Polyline({
        path: livePolylinePath,
        strokeColor: activityConfig['live'].color,
        strokeWeight: 4,
        strokeOpacity: 0.8,
        map: map
    });

    if (!activityLayers['live']) {
        activityLayers['live'] = { paths: [livePolyline], markers: [], visible: true };
        layerVisibility['live'] = true;
    } else {
        // Layer already exists (e.g., from animation) - add livePolyline to it
        activityLayers['live'].paths.push(livePolyline);
    }

    // Update layer control to show the new Live layer
    updateLayerControl();
}

function appendLivePoint(point) {
    if (!livePolyline) {
        initLiveLayer();
    }

    var latLng = new google.maps.LatLng(point.lat, point.lng);
    livePolylinePath.push(latLng);
}

function clearLiveLayer() {
    // Clear all paths and markers from the map (including animation segments)
    if (activityLayers['live']) {
        var layer = activityLayers['live'];
        layer.paths.forEach(function (p) { p.setMap(null); });
        layer.markers.forEach(function (m) { m.setMap(null); });
        delete activityLayers['live'];
    }
    if (layerVisibility['live']) {
        delete layerVisibility['live'];
    }
    if (layerStats['live']) {
        delete layerStats['live'];
    }
    // Clear the live polyline reference
    livePolyline = null;
    livePolylinePath = null;

    // Clear history navigation state
    clearHistoryState();

    updateLayerControl();
}

function fitMapToLivePoints(points) {
    if (!points || points.length === 0) return;

    var bounds = new google.maps.LatLngBounds();
    points.forEach(function(p) {
        bounds.extend({ lat: p.lat, lng: p.lng });
    });
    map.fitBounds(bounds);

    // Don't zoom in too close
    google.maps.event.addListenerOnce(map, 'bounds_changed', function() {
        if (map.getZoom() > 16) map.setZoom(16);
    });
}

// =============================================================================
// History Navigation - Polyline Manipulation
// =============================================================================

var historyMarker = null;           // Marker showing current history position
var historyPolyline = null;         // Temporary polyline for history view
var livePathsHidden = false;        // Track if live paths are hidden

function truncateLivePolyline(toIndex) {
    // Hide all live layer paths and show a temporary truncated polyline

    // Get points from the history (stored in app.js historyPoints)
    var points = (typeof historyPoints !== 'undefined') ? historyPoints : [];
    if (points.length === 0) return;

    // Hide all live paths if not already hidden
    if (!livePathsHidden) {
        if (activityLayers['live']) {
            var layer = activityLayers['live'];
            layer.paths.forEach(function(p) { p.setMap(null); });
        }
        // Also hide the livePolyline if it exists
        if (livePolyline) {
            livePolyline.setMap(null);
        }
        livePathsHidden = true;
    }

    // Build path up to toIndex
    var pathPoints = [];
    for (var i = 0; i <= toIndex && i < points.length; i++) {
        pathPoints.push({ lat: points[i].lat, lng: points[i].lng });
    }

    // Create or update history polyline
    if (!historyPolyline) {
        historyPolyline = new google.maps.Polyline({
            path: pathPoints,
            strokeColor: activityConfig['live'].color,
            strokeWeight: 4,
            strokeOpacity: 0.8,
            map: map
        });
    } else {
        historyPolyline.setPath(pathPoints);
        historyPolyline.setMap(map);
    }
}

function restoreLivePolyline() {
    // Remove history polyline and restore all live paths
    if (historyPolyline) {
        historyPolyline.setMap(null);
        historyPolyline = null;
    }

    // Show all live paths again
    if (livePathsHidden) {
        if (activityLayers['live']) {
            var layer = activityLayers['live'];
            layer.paths.forEach(function(p) { p.setMap(map); });
        }
        // Also show the livePolyline if it exists
        if (livePolyline) {
            livePolyline.setMap(map);
        }
        livePathsHidden = false;
    }
}

function updateHistoryMarker(lat, lng) {
    if (!map) return;

    if (!historyMarker) {
        historyMarker = new google.maps.Marker({
            position: { lat: lat, lng: lng },
            map: map,
            icon: {
                path: google.maps.SymbolPath.CIRCLE,
                scale: 10,
                fillColor: '#4285F4',
                fillOpacity: 1,
                strokeColor: '#FFFFFF',
                strokeWeight: 3
            },
            zIndex: 2000
        });
    } else {
        historyMarker.setPosition({ lat: lat, lng: lng });
        historyMarker.setMap(map);
    }
}

function removeHistoryMarker() {
    if (historyMarker) {
        historyMarker.setMap(null);
    }
}

function clearHistoryState() {
    // Remove history polyline
    if (historyPolyline) {
        historyPolyline.setMap(null);
        historyPolyline = null;
    }
    livePathsHidden = false;
    removeHistoryMarker();
}
