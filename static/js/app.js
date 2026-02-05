var detectionData = null;
var activeLayers = new Set();

document.addEventListener('DOMContentLoaded', function() {
    var startDateInput = document.getElementById('start-date');
    var endDateInput = document.getElementById('end-date');

    // Default to today
    var today = new Date().toISOString().split('T')[0];
    startDateInput.value = today;
    endDateInput.value = today;

    // Sync end date when start date changes
    startDateInput.addEventListener('change', function() {
        endDateInput.value = startDateInput.value;
    });

    document.getElementById('detect-btn').addEventListener('click', detectActivities);
    document.getElementById('start-tracking-btn').addEventListener('click', startTracking);
    document.getElementById('add-layers-btn').addEventListener('click', addSelectedLayers);

    // Sidebar toggle
    var sidebar = document.getElementById('sidebar');
    var sidebarToggle = document.getElementById('sidebar-toggle');
    var backdrop = document.getElementById('sidebar-backdrop');
    var isMobile = window.matchMedia('(max-width: 768px)');

    function updateToggleIcon() {
        var isHidden = sidebar.classList.contains('hidden');
        sidebarToggle.innerHTML = isHidden ? '&#9776;' : '&#10005;';
    }

    function toggleSidebar() {
        var isHidden = sidebar.classList.contains('hidden');
        if (isHidden) {
            sidebar.classList.remove('hidden');
            document.body.classList.add('sidebar-open');
            document.body.classList.remove('sidebar-collapsed');
        } else {
            sidebar.classList.add('hidden');
            document.body.classList.remove('sidebar-open');
            document.body.classList.add('sidebar-collapsed');
        }
        updateToggleIcon();
        // Trigger map resize after transition
        setTimeout(function() {
            if (typeof google !== 'undefined' && map) {
                google.maps.event.trigger(map, 'resize');
            }
        }, 350);
    }

    sidebarToggle.addEventListener('click', toggleSidebar);
    backdrop.addEventListener('click', function() {
        if (!sidebar.classList.contains('hidden')) {
            toggleSidebar();
        }
    });

    // On mobile, start with sidebar hidden
    if (isMobile.matches) {
        sidebar.classList.add('hidden');
        document.body.classList.add('sidebar-collapsed');
        updateToggleIcon();
    }

    // Playback controls
    document.getElementById('pause-play-btn').addEventListener('click', togglePause);
    document.getElementById('step-back-btn').addEventListener('click', stepBack);
    document.getElementById('step-forward-btn').addEventListener('click', stepForward);

    // Spacebar pause/resume, arrow keys for step
    document.addEventListener('keydown', function(e) {
        if (e.code === 'Space' && animationRunning) {
            e.preventDefault();
            togglePause();
        } else if (e.code === 'ArrowLeft' && animationPaused && animationRunning) {
            e.preventDefault();
            stepBack();
        } else if (e.code === 'ArrowRight' && animationPaused && animationRunning) {
            e.preventDefault();
            stepForward();
        }
    });
});

function detectActivities() {
    var startDate = document.getElementById('start-date').value;
    var endDate = document.getElementById('end-date').value;
    var startTime = document.getElementById('start-time').value || '00:00';
    var endTime = document.getElementById('end-time').value || '23:59';

    if (!startDate || !endDate) {
        alert('Please select start and end dates.');
        return;
    }

    var detectBtn = document.getElementById('detect-btn');
    detectBtn.disabled = true;
    detectBtn.textContent = 'Detecting...';

    document.getElementById('activity-summary').style.display = 'none';
    document.getElementById('activity-controls').style.display = 'none';
    document.getElementById('tracking-info').style.display = 'none';

    fetch('/api/detect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            start_date: startDate,
            end_date: endDate,
            start_time: startTime,
            end_time: endTime
        })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        detectBtn.disabled = false;
        detectBtn.textContent = 'Detect Activities';

        if (!data.success) {
            document.getElementById('activity-summary').style.display = 'block';
            document.getElementById('summary-content').textContent = 'Error: ' + data.error;
            return;
        }

        detectionData = data;

        var tzDisplay = document.getElementById('timezone-display');
        tzDisplay.textContent = data.timezone + ' (Detected)';
        tzDisplay.className = 'detected';

        displaySummary(data);
        showActivityControls(data);
    })
    .catch(function(err) {
        detectBtn.disabled = false;
        detectBtn.textContent = 'Detect Activities';
        document.getElementById('activity-summary').style.display = 'block';
        document.getElementById('summary-content').textContent = 'Request failed: ' + err.message;
    });
}

function displaySummary(data) {
    var lines = [];
    lines.push('MULTI-LAYER ACTIVITY DETECTION RESULTS');
    lines.push('='.repeat(50));
    lines.push('');
    lines.push('Total GPS Points: ' + data.total_points.toLocaleString());
    lines.push('Activity Markers Found: ' + data.activity_markers);
    lines.push('');
    lines.push('AVAILABLE LAYERS:');
    lines.push('-'.repeat(30));

    var icons = { car: 'Car', bike: 'Bike', other: 'Other' };

    ['car', 'bike', 'other'].forEach(function(type) {
        var s = data.stats[type];
        if (!s) return;

        lines.push('');
        lines.push(icons[type].toUpperCase() + ' LAYER:');

        if (s.total_points > 0) {
            if (s.filtered_count > 0) {
                lines.push('  Available - ' + s.count + ' valid rides (' + s.filtered_count + ' filtered), ' + s.total_points.toLocaleString() + ' points');
            } else {
                lines.push('  Available - ' + s.count + ' rides, ' + s.total_points.toLocaleString() + ' points');
            }
            lines.push('  Distance: ' + s.total_distance + ' km');
            lines.push('  Duration: ' + s.total_duration_str);
            if (s.avg_speed > 0) {
                lines.push('  Avg Speed: ' + s.avg_speed + ' km/h');
            }
        } else {
            lines.push('  No data available');
        }
    });

    lines.push('');
    lines.push('ALL POINTS LAYER:');
    lines.push('  Available - ' + data.total_points.toLocaleString() + ' total GPS points');

    if (data.timeline && data.timeline.length > 0) {
        lines.push('');
        lines.push('ACTIVITY TIMELINE:');
        lines.push('-'.repeat(30));
        data.timeline.forEach(function(event) {
            var suffix = event.type === 'generated' ? ' (auto-detected)' : '';
            lines.push('  ' + event.time + ' - ' + event.event + suffix);
        });
    }

    document.getElementById('summary-content').textContent = lines.join('\n');
    document.getElementById('activity-summary').style.display = 'block';
}

function showActivityControls(data) {
    var select = document.getElementById('primary-activity');
    select.innerHTML = '';

    var icons = { car: 'Car', bike: 'Bike', other: 'Other' };

    ['car', 'bike', 'other'].forEach(function(type) {
        var s = data.stats[type];
        if (s && s.count > 0) {
            var opt = document.createElement('option');
            opt.value = type;
            opt.textContent = icons[type] + ' (' + s.count + ' rides, ' + s.total_points + ' points)';
            select.appendChild(opt);
        }
    });

    // Add "All" option
    var allOpt = document.createElement('option');
    allOpt.value = 'all';
    allOpt.textContent = 'All Activities (' + data.total_points + ' points)';
    select.appendChild(allOpt);

    document.getElementById('activity-controls').style.display = 'block';
    document.getElementById('start-tracking-btn').disabled = false;

    // Setup layer checkboxes
    setupLayerCheckboxes(data);
}

function setupLayerCheckboxes(data) {
    var container = document.getElementById('layer-checkboxes');
    container.innerHTML = '';

    var icons = { car: 'Car', bike: 'Bike', other: 'Other', all: 'All Points' };

    ['car', 'bike', 'other', 'all'].forEach(function(type) {
        if (activeLayers.has(type)) return;

        var hasData = type === 'all' || (data.stats[type] && data.stats[type].count > 0);
        if (!hasData) return;

        var label = document.createElement('label');
        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = type;
        label.appendChild(checkbox);
        label.appendChild(document.createTextNode(' ' + icons[type]));
        container.appendChild(label);
    });
}

function startTracking() {
    var activityType = document.getElementById('primary-activity').value;
    if (!activityType) return;

    stopAnimation();
    clearAllLayers();
    activeLayers.clear();

    document.getElementById('start-tracking-btn').disabled = true;
    document.getElementById('start-tracking-btn').textContent = 'Tracking...';

    // Show tracking info panel immediately so user sees live updates
    document.getElementById('tracking-info').style.display = 'block';
    document.getElementById('stat-distance').textContent = '0.00 km';
    document.getElementById('stat-duration').textContent = '0h 0m';
    document.getElementById('stat-speed').textContent = '0.0 km/h';
    document.getElementById('stat-points').textContent = '0';
    document.getElementById('stat-time').textContent = '--:--:--';

    // Hook up live stats callback
    onAnimationProgress = function(info) {
        document.getElementById('stat-distance').textContent = info.distance.toFixed(2) + ' km';

        var hours = Math.floor(info.duration / 3600);
        var mins = Math.floor((info.duration % 3600) / 60);
        var secs = info.duration % 60;
        document.getElementById('stat-duration').textContent = hours + 'h ' + mins + 'm ' + secs + 's';

        document.getElementById('stat-speed').textContent = info.speed.toFixed(1) + ' km/h';
        document.getElementById('stat-points').textContent = info.pointIndex.toLocaleString() + ' / ' + info.totalPoints.toLocaleString();

        if (info.timestamp) {
            var d = new Date(info.timestamp * 1000);
            document.getElementById('stat-time').textContent = d.toLocaleTimeString();
        }
    };

    loadLayerAnimated(activityType, function() {
        activeLayers.add(activityType);
        onAnimationProgress = null;
        document.getElementById('start-tracking-btn').disabled = false;
        document.getElementById('start-tracking-btn').textContent = 'Start Tracking';
        updateTrackingInfo();
        setupLayerCheckboxes(detectionData);
    });
}

function addSelectedLayers() {
    var checkboxes = document.querySelectorAll('#layer-checkboxes input[type="checkbox"]:checked');
    var toLoad = [];
    checkboxes.forEach(function(cb) { toLoad.push(cb.value); });

    if (toLoad.length === 0) return;

    var loaded = 0;
    toLoad.forEach(function(type) {
        loadLayer(type, function() {
            activeLayers.add(type);
            loaded++;
            if (loaded === toLoad.length) {
                updateTrackingInfo();
                setupLayerCheckboxes(detectionData);
            }
        });
    });
}

function loadLayer(activityType, callback) {
    fetch('/api/track/' + activityType)
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (!data.success) {
                alert('Error loading ' + activityType + ': ' + data.error);
                return;
            }

            if (data.mode === 'rich') {
                addRichLayer(activityType, data.rides, data.stats);
            } else {
                addBasicLayer(activityType, data.points, data.stats, data.start_time_str, data.end_time_str);
            }

            if (callback) callback();
        })
        .catch(function(err) {
            alert('Failed to load ' + activityType + ' layer: ' + err.message);
        });
}

function loadLayerAnimated(activityType, callback) {
    fetch('/api/track/' + activityType)
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (!data.success) {
                alert('Error loading ' + activityType + ': ' + data.error);
                return;
            }

            if (data.mode === 'rich') {
                addRichLayerAnimated(activityType, data.rides, data.stats, callback);
            } else {
                addBasicLayerAnimated(activityType, data.points, data.stats, data.start_time_str, data.end_time_str, callback);
            }
        })
        .catch(function(err) {
            alert('Failed to load ' + activityType + ' layer: ' + err.message);
        });
}

function saveInteractiveMap() {
    if (activeLayers.size === 0) {
        alert('No active layers to save. Start tracking first.');
        return;
    }

    var saveBtn = document.getElementById('save-map-btn');
    var saveStatus = document.getElementById('save-status');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    saveStatus.style.display = 'none';

    var startDate = document.getElementById('start-date').value;
    var endDate = document.getElementById('end-date').value;

    fetch('/api/save-map', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            active_layers: Array.from(activeLayers),
            start_date: startDate,
            end_date: endDate
        })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Interactive Map';

        if (data.success) {
            saveStatus.textContent = 'Saved: ' + data.filename;
            saveStatus.style.display = 'block';
        } else {
            alert('Save failed: ' + data.error);
        }
    })
    .catch(function(err) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Interactive Map';
        alert('Save failed: ' + err.message);
    });
}

function updateTrackingInfo() {
    var icons = { car: 'Car', bike: 'Bike', other: 'Other', all: 'All' };
    var layerText = Array.from(activeLayers).map(function(type) {
        return icons[type] || type;
    }).join(', ');

    document.getElementById('active-layers-text').textContent = layerText || 'None';

    if (detectionData) {
        // If 'all' layer is active, keep its stats (from animation) - individual layers
        // are subsets of 'all', so we shouldn't add them to avoid double-counting.
        if (activeLayers.has('all')) {
            // Just update points count, keep distance/duration/speed from animation
            document.getElementById('stat-points').textContent = detectionData.total_points.toLocaleString();
            return;
        }

        // Only individual layers active (no 'all') - sum their stats
        var totalDist = 0;
        var totalDur = 0;
        var totalPts = 0;

        activeLayers.forEach(function(type) {
            var s = detectionData.stats[type];
            if (s) {
                totalDist += s.total_distance;
                totalDur += s.total_duration;
                totalPts += s.total_points;
            }
        });

        document.getElementById('stat-distance').textContent = totalDist.toFixed(2) + ' km';

        var hours = Math.floor(totalDur / 3600);
        var mins = Math.floor((totalDur % 3600) / 60);
        document.getElementById('stat-duration').textContent = hours + 'h ' + mins + 'm';

        document.getElementById('stat-points').textContent = totalPts.toLocaleString();

        var avgSpeed = totalDur > 0 ? (totalDist / totalDur * 3600) : 0;
        document.getElementById('stat-speed').textContent = avgSpeed.toFixed(1) + ' km/h';
    }
}
