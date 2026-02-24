var detectionData = null;
var activeLayers = new Set();

// Live mode state
var currentMode = 'datetime';  // 'datetime' | 'live'
var livePollingInterval = null;
var liveData = null;
var LIVE_POLL_INTERVAL_MS = 30000;  // 30 seconds
var lastDrawnTimestamp = 0;  // Track last point drawn to avoid missing any

// Live mode ride tracking - to detect when to redraw rich layers
var liveRideCounts = { car: 0, bike: 0, other: 0 };
var liveRidePoints = { car: 0, bike: 0, other: 0 };

// Store live rides data for current activity display
var liveRidesData = { car: [], bike: [], other: [] };

// Track if live animation was already shown this session (for hybrid animation)
var liveAnimationShown = false;

// Guard against concurrent polls (if a poll takes longer than the interval)
var pollInProgress = false;

// 1-second ticker for last-fix age display in speed overlay
var lastFixInterval = null;

// Screen keep-awake: Wake Lock API (HTTPS) or NoSleep.js fallback (HTTP)
var noSleep = new NoSleep();
var noSleepActive = false;
var wakeLock = null;

// History navigation state
var historyModeActive = false;      // Are we viewing history?
var historyViewIndex = -1;          // Current view point index (-1 = live/latest)
var historyPoints = [];             // All live points for navigation
var historyCumulativeStats = [];    // Pre-calculated stats per point: [{tst, distance, duration, pointCount}]

// Toggle past activities visibility (live mode)
function togglePastActivities() {
    var summary = document.getElementById('live-activity-summary');
    if (summary) {
        summary.classList.toggle('past-activities-collapsed');
    }
}

// Toggle activities visibility (datetime mode)
function toggleDatetimeActivities() {
    var section = document.getElementById('datetime-activities');
    if (section) {
        section.classList.toggle('past-activities-collapsed');
    }
}

document.addEventListener('DOMContentLoaded', function() {
    var startDateInput = document.getElementById('start-date');
    var endDateInput = document.getElementById('end-date');

    // Default to today (local time, not UTC)
    var now = new Date();
    var today = now.getFullYear() + '-' +
        String(now.getMonth() + 1).padStart(2, '0') + '-' +
        String(now.getDate()).padStart(2, '0');
    startDateInput.value = today;
    endDateInput.value = today;

    // Sync end date when start date changes
    startDateInput.addEventListener('change', function() {
        endDateInput.value = startDateInput.value;
    });

    document.getElementById('detect-btn').addEventListener('click', detectActivities);
    document.getElementById('start-tracking-btn').addEventListener('click', startTracking);
    document.getElementById('add-layers-btn').addEventListener('click', addSelectedLayers);

    // Mode toggle handlers (with null checks for graceful degradation)
    var modeDatetimeBtn = document.getElementById('mode-datetime');
    var modeLiveBtn = document.getElementById('mode-live');
    if (modeDatetimeBtn) {
        modeDatetimeBtn.addEventListener('click', function() {
            switchToDateTimeMode();
        });
    }
    if (modeLiveBtn) {
        modeLiveBtn.addEventListener('click', function() {
            switchToLiveMode();
        });
    }

    // Live mode button handlers
    var liveStartBtn = document.getElementById('live-start-btn');
    var liveResetBtn = document.getElementById('live-reset-btn');
    if (liveStartBtn) {
        liveStartBtn.addEventListener('click', function() {
            startLiveMode();
        });
    }
    if (liveResetBtn) {
        liveResetBtn.addEventListener('click', function() {
            resetLiveMode();
        });
    }

    var liveAwakeBtn = document.getElementById('live-awake-btn');
    if (liveAwakeBtn) {
        liveAwakeBtn.addEventListener('click', function() {
            toggleKeepAwake();
        });
    }

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
        displayDatetimeActivities(data);
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

function displayDatetimeActivities(data) {
    var activitiesSection = document.getElementById('datetime-activities');
    var contentDiv = document.getElementById('datetime-activities-content');

    if (!activitiesSection || !contentDiv) return;

    // Check if there are any rides
    if (!data.rides || data.rides.length === 0) {
        activitiesSection.style.display = 'none';
        return;
    }

    var icons = { car: '🚗', bike: '🚴', other: '🚶' };
    var names = { car: 'Car', bike: 'Bike', other: 'Walking' };
    var html = '';

    data.rides.forEach(function(ride) {
        var durationMins = Math.floor(ride.duration / 60);
        var durationStr = durationMins >= 60 ?
            Math.floor(durationMins / 60) + 'h ' + (durationMins % 60) + 'm' :
            durationMins + 'm';

        html += '<div class="past-ride-item">' +
            '<span class="past-ride-icon">' + icons[ride.type] + '</span> ' +
            '<strong>' + names[ride.type] + ' ' + ride.ride_number + '</strong><br>' +
            '<span class="past-ride-details">' +
            ride.start_datetime_str + ' • ' +
            ride.distance.toFixed(1) + ' km • ' +
            durationStr + ' • ' +
            ride.avg_speed.toFixed(1) + ' km/h • ' +
            ride.points + ' pts' +
            '</span></div>';
    });

    contentDiv.innerHTML = html;
    activitiesSection.style.display = 'block';
}

function startTracking() {
    var activityType = document.getElementById('primary-activity').value;
    if (!activityType) return;

    stopAnimation();
    clearAllLayers();  // Clear all layers for clean tracking
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

function saveLiveMap() {
    var saveBtn = document.getElementById('live-save-btn');
    var saveStatus = document.getElementById('live-save-status');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    saveStatus.style.display = 'none';

    fetch('/api/live/save-map', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Map';

        if (data.success) {
            saveStatus.textContent = 'Saved: ' + data.filename;
            saveStatus.style.display = 'block';
        } else {
            alert('Save failed: ' + data.error);
        }
    })
    .catch(function(err) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Map';
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

// =============================================================================
// Live Mode Functions
// =============================================================================

var STALE_SESSION_THRESHOLD_DAYS = 7;

function checkLiveStatus() {
    // Check if there's an existing live session
    fetch('/api/live/status')
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (!data.success) {
            console.error('Failed to check live status:', data.error);
            showStartLiveButton();
            return;
        }

        if (!data.has_session) {
            // No existing session - show Start button
            showStartLiveButton();
            return;
        }

        // Session exists - update UI with session info
        updateLiveStartTime(data.start_time_str, data.start_timestamp);

        if (data.is_active) {
            // Session is active in memory (another device or same device)
            // Join the session
            joinLiveSession();
        } else if (data.is_stale) {
            // Session is > 7 days old - prompt user
            showStaleSessionDialog(data);
        } else {
            // Recent session but not active (container restarted)
            // Offer to resume
            showResumeSessionDialog(data);
        }
    })
    .catch(function(err) {
        console.error('Failed to check live status:', err.message);
        showStartLiveButton();
    });
}

function showStartLiveButton() {
    document.getElementById('live-start-btn').style.display = 'block';
    document.getElementById('live-start-btn').textContent = 'Start Live Mode';
    document.getElementById('live-reset-btn').style.display = 'none';
    document.getElementById('live-save-btn').style.display = 'none';
    var awakeBtn = document.getElementById('live-awake-btn');
    if (awakeBtn) awakeBtn.style.display = 'none';
    document.getElementById('live-save-status').style.display = 'none';
    document.getElementById('live-start-time').textContent = '--';
    document.getElementById('live-duration').textContent = '';
    document.getElementById('live-total-points').textContent = '0';
    document.getElementById('live-activity-summary').style.display = 'none';
    updateLiveIndicator(false);
}

function updateLiveStartTime(startTimeStr, startTimestamp) {
    document.getElementById('live-start-time').textContent = startTimeStr;
    if (startTimestamp) {
        var now = Math.floor(Date.now() / 1000);
        var duration = now - startTimestamp;
        var hours = Math.floor(duration / 3600);
        var mins = Math.floor((duration % 3600) / 60);
        document.getElementById('live-duration').textContent = '(' + hours + 'h ' + mins + 'm ago)';
    }
}

function showStaleSessionDialog(statusData) {
    var message = 'Live mode session is ' + statusData.age_days + ' days old.\n' +
                  'Started: ' + statusData.start_time_str + '\n\n' +
                  'OK = Resume from where you left off\n' +
                  'Cancel = Reset and start fresh from now';

    if (confirm(message)) {
        // Resume from saved state (safe default)
        resumeLiveSession();
    } else {
        // Reset - start fresh (destructive, requires deliberate Cancel)
        startLiveMode();
    }
}

function showResumeSessionDialog(statusData) {
    var message = 'Found existing live mode session.\n' +
                  'Started: ' + statusData.start_time_str + '\n' +
                  'Points: ' + statusData.total_points + '\n\n' +
                  'Resume this session?\n\n' +
                  'Click OK to Resume, Cancel to Start Fresh';

    if (confirm(message)) {
        // Resume from saved state
        resumeLiveSession();
    } else {
        // Start fresh
        startLiveMode();
    }
}

function joinLiveSession() {
    // Join an active session (another device is already tracking)
    var startBtn = document.getElementById('live-start-btn');
    startBtn.style.display = 'none';
    document.getElementById('live-reset-btn').style.display = 'block';
    document.getElementById('live-save-btn').style.display = 'block';
    var awakeBtn = document.getElementById('live-awake-btn');
    if (awakeBtn) {
        awakeBtn.style.display = 'block';
        if (window.matchMedia('(max-width: 768px)').matches && !noSleepActive) enableKeepAwake();
    }

    // Decide whether to animate: only if animation hasn't been shown yet this session
    var shouldAnimate = !liveAnimationShown;

    // Reset state for fresh draw
    lastDrawnTimestamp = 0;
    liveRideCounts = { car: 0, bike: 0, other: 0 };
    liveRidePoints = { car: 0, bike: 0, other: 0 };
    liveRidesData = { car: [], bike: [], other: [] };

    // Call start which will return the existing session
    fetch('/api/live/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (!data.success) {
            alert('Failed to join live session: ' + data.error);
            showStartLiveButton();
            return;
        }

        liveData = data;
        updateLiveUI(data);

        // Load existing track on map
        if (data.total_points > 0) {
            if (shouldAnimate) {
                // First time - animate, then start polling after animation completes
                loadLiveTrack(true, function() {
                    liveAnimationShown = true;
                    startLivePolling();
                });
            } else {
                // Already seen animation - draw instantly
                loadLiveTrack(false, function() {
                    startLivePolling();
                });
            }
        } else {
            // No points yet - start polling immediately
            startLivePolling();
        }
    })
    .catch(function(err) {
        alert('Failed to join live session: ' + err.message);
        showStartLiveButton();
    });
}

function resumeLiveSession() {
    // Resume from saved state after container restart
    var startBtn = document.getElementById('live-start-btn');
    startBtn.disabled = true;
    startBtn.textContent = 'Resuming...';

    // Reset state - we'll draw all points from the loaded data
    lastDrawnTimestamp = 0;
    liveRideCounts = { car: 0, bike: 0, other: 0 };
    liveRidePoints = { car: 0, bike: 0, other: 0 };
    liveRidesData = { car: [], bike: [], other: [] };

    fetch('/api/live/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume: true })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        startBtn.disabled = false;
        startBtn.textContent = 'Start Live Mode';

        if (!data.success) {
            alert('Failed to resume live session: ' + data.error);
            showStartLiveButton();
            return;
        }

        liveData = data;
        updateLiveUI(data);

        // Show reset button and save button, hide start button
        startBtn.style.display = 'none';
        document.getElementById('live-reset-btn').style.display = 'block';
        document.getElementById('live-save-btn').style.display = 'block';
        var awakeBtn = document.getElementById('live-awake-btn');
    if (awakeBtn) {
        awakeBtn.style.display = 'block';
        if (window.matchMedia('(max-width: 768px)').matches && !noSleepActive) enableKeepAwake();
    }

        // Load existing track on map (with animation for first view after resume)
        if (data.total_points > 0) {
            // Animate (first view after restart), then start polling
            loadLiveTrack(true, function() {
                liveAnimationShown = true;
                startLivePolling();
            });
        } else {
            // No points yet - start polling immediately
            startLivePolling();
        }
    })
    .catch(function(err) {
        startBtn.disabled = false;
        startBtn.textContent = 'Start Live Mode';
        alert('Failed to resume live session: ' + err.message);
        showStartLiveButton();
    });
}

function switchToDateTimeMode() {
    if (currentMode === 'datetime') return;

    currentMode = 'datetime';
    stopLivePolling();

    // Stop any ongoing animation from live mode
    if (typeof stopAnimation === 'function') {
        stopAnimation();
    }

    // Clear history navigation state when leaving live mode
    resetHistoryState();

    // Update mode toggle buttons
    document.getElementById('mode-datetime').classList.add('active');
    document.getElementById('mode-live').classList.remove('active');

    // Show datetime panel, hide live panel
    document.getElementById('datetime-panel').style.display = 'block';
    document.getElementById('live-panel').style.display = 'none';

    // Clear all layers
    if (typeof clearAllLayers === 'function') {
        clearAllLayers();
    }

    // Restore previously active datetime layers (if any)
    if (activeLayers.size > 0 && detectionData) {
        activeLayers.forEach(function(type) {
            loadLayer(type);  // Draw instantly without animation
        });
    }
}

function switchToLiveMode() {
    if (currentMode === 'live') return;

    currentMode = 'live';

    // Stop any ongoing animation from datetime mode
    if (typeof stopAnimation === 'function') {
        stopAnimation();
    }

    // Clear any stale history navigation state
    resetHistoryState();

    // Update mode toggle buttons
    document.getElementById('mode-live').classList.add('active');
    document.getElementById('mode-datetime').classList.remove('active');

    // Hide datetime panel, show live panel
    document.getElementById('datetime-panel').style.display = 'none';
    document.getElementById('live-panel').style.display = 'block';

    // Clear all layers - live mode will redraw its own layers
    if (typeof clearAllLayers === 'function') {
        clearAllLayers();
    }

    // Check live status to see if there's an existing session
    checkLiveStatus();
}

function hideDatetimeLayers() {
    // Hide all non-live layers
    if (typeof activityLayers !== 'undefined') {
        Object.keys(activityLayers).forEach(function(key) {
            if (key !== 'live') {
                var layer = activityLayers[key];
                layer.paths.forEach(function(p) { p.setMap(null); });
                layer.markers.forEach(function(m) { m.setMap(null); });
            }
        });
    }
}

function showDatetimeLayers() {
    // Show all non-live layers that were previously visible
    if (typeof activityLayers !== 'undefined') {
        Object.keys(activityLayers).forEach(function(key) {
            if (key !== 'live' && layerVisibility[key]) {
                var layer = activityLayers[key];
                layer.paths.forEach(function(p) { p.setMap(map); });
                layer.markers.forEach(function(m) { m.setMap(map); });
            }
        });
    }
}

function hideLiveLayer() {
    if (typeof livePolyline !== 'undefined' && livePolyline) {
        livePolyline.setMap(null);
    }
}

function showLiveLayer() {
    if (typeof livePolyline !== 'undefined' && livePolyline) {
        livePolyline.setMap(map);
    }
}

function startLiveMode() {
    var startBtn = document.getElementById('live-start-btn');
    startBtn.disabled = true;
    startBtn.textContent = 'Starting...';

    // Clear any existing live layer for fresh start
    if (typeof clearLiveLayer === 'function') {
        clearLiveLayer();
    }

    // Clear any existing activity layers from previous live session
    if (typeof clearActivityLayer === 'function') {
        clearActivityLayer('car');
        clearActivityLayer('bike');
    }

    // Reset state for fresh start
    lastDrawnTimestamp = 0;
    liveRideCounts = { car: 0, bike: 0, other: 0 };
    liveRidePoints = { car: 0, bike: 0, other: 0 };
    liveRidesData = { car: [], bike: [], other: [] };
    liveAnimationShown = false;  // Reset so next entry will animate

    // Hide tracking info until we have data
    var trackingInfo = document.getElementById('live-tracking-info');
    if (trackingInfo) trackingInfo.style.display = 'none';

    fetch('/api/live/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        startBtn.disabled = false;
        startBtn.textContent = 'Start Live Mode';

        if (!data.success) {
            alert('Failed to start live mode: ' + data.error);
            return;
        }

        liveData = data;
        updateLiveUI(data);

        // Clear activity summary since we're starting fresh
        document.getElementById('live-activity-summary').style.display = 'none';

        // Show reset button and save button, hide start button
        startBtn.style.display = 'none';
        document.getElementById('live-reset-btn').style.display = 'block';
        document.getElementById('live-save-btn').style.display = 'block';
        var awakeBtn = document.getElementById('live-awake-btn');
    if (awakeBtn) {
        awakeBtn.style.display = 'block';
        if (window.matchMedia('(max-width: 768px)').matches && !noSleepActive) enableKeepAwake();
    }

        // Start polling
        startLivePolling();
    })
    .catch(function(err) {
        startBtn.disabled = false;
        startBtn.textContent = 'Start Live Mode';
        alert('Failed to start live mode: ' + err.message);
    });
}

function startLivePolling() {
    if (livePollingInterval) return;  // Already polling

    updateLiveIndicator(true);
    showSpeedOverlay(true);
    livePollingInterval = setInterval(pollLiveData, LIVE_POLL_INTERVAL_MS);

    // 1-second ticker for last-fix age in speed overlay
    lastFixInterval = setInterval(updateLastFixAge, 1000);
    updateLastFixAge();  // immediate first paint

    // Also poll immediately
    pollLiveData();
}

function stopLivePolling() {
    if (livePollingInterval) {
        clearInterval(livePollingInterval);
        livePollingInterval = null;
    }
    if (lastFixInterval) {
        clearInterval(lastFixInterval);
        lastFixInterval = null;
    }
    pollInProgress = false;
    updateLiveIndicator(false);
    showSpeedOverlay(false);
    disableKeepAwake();
}

function toggleKeepAwake() {
    if (noSleepActive) {
        disableKeepAwake();
    } else {
        enableKeepAwake();
    }
}

function enableKeepAwake() {
    if (navigator.wakeLock) {
        // HTTPS — use native Wake Lock (no media session conflict with CarPlay)
        navigator.wakeLock.request('screen').then(function(lock) {
            wakeLock = lock;
            noSleepActive = true;
            updateAwakeButton(true);
            console.log('[WakeLock] Native Wake Lock acquired');
            lock.addEventListener('release', function() {
                console.log('[WakeLock] Released');
                wakeLock = null;
                // Re-acquire if still supposed to be active
                if (noSleepActive) enableKeepAwake();
            });
        }).catch(function(err) {
            console.log('[WakeLock] Failed, falling back to NoSleep:', err.message);
            enableNoSleepFallback();
        });
    } else {
        enableNoSleepFallback();
    }
}

function enableNoSleepFallback() {
    noSleep.enable().then(function() {
        noSleepActive = true;
        updateAwakeButton(true);
        console.log('[KeepAwake] NoSleep.js fallback activated');
        // Hide from CarPlay / Now Playing so it doesn't interfere with Spotify/radio
        if ('mediaSession' in navigator) {
            navigator.mediaSession.metadata = null;
            navigator.mediaSession.playbackState = 'none';
        }
    }).catch(function(err) {
        console.log('[KeepAwake] NoSleep fallback failed:', err.message);
    });
}

function disableKeepAwake() {
    // Set false BEFORE releasing the lock. The Wake Lock API fires its 'release'
    // event synchronously in some browsers; if noSleepActive were still true at
    // that point, the listener in enableKeepAwake() would immediately re-acquire
    // the lock, making it impossible to turn off.
    noSleepActive = false;
    if (wakeLock) {
        wakeLock.release();
        wakeLock = null;
    }
    noSleep.disable();
    updateAwakeButton(false);
}

function updateAwakeButton(isOn) {
    var btn = document.getElementById('live-awake-btn');
    if (!btn) return;
    btn.textContent = 'Screen Awake: ' + (isOn ? 'ON' : 'OFF');
    btn.style.backgroundColor = isOn ? '#53cf6e' : '';
}

function updateLastFixAge() {
    var el = document.getElementById('last-fix-age');
    if (!el) return;

    if (!lastDrawnTimestamp) {
        el.textContent = '\u2299 --';
        el.style.color = '';
        return;
    }

    var ageSecs = Math.floor(Date.now() / 1000) - lastDrawnTimestamp;
    var text;
    if (ageSecs >= 3600) {
        text = Math.floor(ageSecs / 3600) + 'h';
    } else {
        var mins = Math.floor(ageSecs / 60);
        var secs = ageSecs % 60;
        text = mins > 0 ? mins + 'm ' + secs + 's' : secs + 's';
    }
    el.textContent = '\u2299 ' + text;

    if (ageSecs < 120) {
        el.style.color = '#53cf6e';   // green — normal
    } else if (ageSecs < 300) {
        el.style.color = '#f0a500';   // orange — stale
    } else {
        el.style.color = '#e05252';   // red — phone likely offline
    }
}

function showSpeedOverlay(visible) {
    var overlay = document.getElementById('speed-overlay');
    if (overlay) overlay.style.display = visible ? 'block' : 'none';
}

function updateSpeedOverlay() {
    var overlay = document.getElementById('speed-overlay');
    var valueEl = document.getElementById('speed-value');
    if (!overlay || !valueEl) return;

    // Find latest ride across all activity types
    var latestRide = null;
    ['car', 'bike', 'other'].forEach(function(type) {
        var rides = liveRidesData[type];
        if (rides && rides.length > 0) {
            var lastRide = rides[rides.length - 1];
            if (!latestRide || lastRide.end_timestamp > latestRide.end_timestamp) {
                latestRide = lastRide;
            }
        }
    });

    if (latestRide && latestRide.avg_speed !== undefined) {
        var spd = latestRide.avg_speed;
        valueEl.textContent = spd < 10 ? spd.toFixed(1) : Math.round(spd);
    } else {
        valueEl.textContent = '--';
    }
}

function pollLiveData() {
    if (pollInProgress) return;  // Skip if previous poll still in-flight
    pollInProgress = true;

    // Re-enable NoSleep.js if interrupted (e.g. by pinch-to-zoom on iOS)
    // Wake Lock doesn't need this — it re-acquires via its own release event
    if (noSleepActive && !wakeLock && noSleep && !noSleep.isEnabled) {
        noSleep.enable().then(function() {
            if ('mediaSession' in navigator) {
                navigator.mediaSession.metadata = null;
                navigator.mediaSession.playbackState = 'none';
            }
        }).catch(function() {});
    }

    fetch('/api/live/poll', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ last_drawn_timestamp: lastDrawnTimestamp })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        pollInProgress = false;

        if (!data.success) {
            console.error('Poll failed:', data.error);
            return;
        }

        // Update cached data
        liveData = Object.assign(liveData || {}, data);
        updateLiveUI(data);

        // Update last poll time
        var now = new Date();
        document.getElementById('live-last-update').textContent = now.toLocaleTimeString();

        // Check if ride counts or points changed - need to redraw rich layers
        var newCarCount = (data.stats && data.stats.car) ? data.stats.car.count : 0;
        var newBikeCount = (data.stats && data.stats.bike) ? data.stats.bike.count : 0;
        var newOtherCount = (data.stats && data.stats.other) ? data.stats.other.count : 0;
        var newCarPoints = (data.stats && data.stats.car) ? data.stats.car.total_points : 0;
        var newBikePoints = (data.stats && data.stats.bike) ? data.stats.bike.total_points : 0;
        var newOtherPoints = (data.stats && data.stats.other) ? data.stats.other.total_points : 0;
        var ridesChanged = (newCarCount !== liveRideCounts.car) ||
                           (newBikeCount !== liveRideCounts.bike) ||
                           (newOtherCount !== liveRideCounts.other) ||
                           (newCarPoints !== liveRidePoints.car) ||
                           (newBikePoints !== liveRidePoints.bike) ||
                           (newOtherPoints !== liveRidePoints.other);

        if (ridesChanged) {
            // Update counts and points
            liveRideCounts.car = newCarCount;
            liveRideCounts.bike = newBikeCount;
            liveRideCounts.other = newOtherCount;
            liveRidePoints.car = newCarPoints;
            liveRidePoints.bike = newBikePoints;
            liveRidePoints.other = newOtherPoints;
            // Fetch and redraw rich layers for activities
            refreshLiveActivityLayers();
        }

        // Draw points to the simple live polyline (for real-time updates)
        // Note: Activity points will be redrawn by refreshLiveActivityLayers
        if (data.points_to_draw && data.points_to_draw.length > 0) {
            // Only append to map if not in history mode
            if (!historyModeActive) {
                appendLivePoints(data.points_to_draw);
            }
            // Update lastDrawnTimestamp to the last point we drew
            var lastPoint = data.points_to_draw[data.points_to_draw.length - 1];
            lastDrawnTimestamp = lastPoint.tst;

            // Add points to history tracking and calculate cumulative stats
            addPointsToHistory(data.points_to_draw);
        }

        // Update history panel display
        updateHistoryPanel();
    })
    .catch(function(err) {
        pollInProgress = false;
        console.error('Poll error:', err.message);
    });
}

function refreshLiveActivityLayers() {
    // Fetch and draw rich layers for car, bike, and other activities
    // This gives us markers and colored rides like datetime mode

    // Fetch car rides if any
    if (liveRideCounts.car > 0) {
        fetch('/api/live/track/car')
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success && data.rides && data.rides.length > 0) {
                liveRidesData.car = data.rides;
                var wasVisible = layerVisibility['car'] !== false;
                clearActivityLayer('car');
                addRichLayer('car', data.rides, data.stats, true);
                if (!wasVisible) toggleLayer('car');
                updateCurrentActivityDisplay();
            }
        })
        .catch(function(err) {
            console.error('Failed to fetch car rides:', err.message);
        });
    } else {
        liveRidesData.car = [];
    }

    // Fetch bike rides if any
    if (liveRideCounts.bike > 0) {
        fetch('/api/live/track/bike')
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success && data.rides && data.rides.length > 0) {
                liveRidesData.bike = data.rides;
                var wasVisible = layerVisibility['bike'] !== false;
                clearActivityLayer('bike');
                addRichLayer('bike', data.rides, data.stats, true);
                if (!wasVisible) toggleLayer('bike');
                updateCurrentActivityDisplay();
            }
        })
        .catch(function(err) {
            console.error('Failed to fetch bike rides:', err.message);
        });
    } else {
        liveRidesData.bike = [];
    }

    // Fetch other (walking) rides if any
    if (liveRideCounts.other > 0) {
        fetch('/api/live/track/other')
        .then(function(response) { return response.json(); })
        .then(function(data) {
            if (data.success && data.rides && data.rides.length > 0) {
                liveRidesData.other = data.rides;
                var wasVisible = layerVisibility['other'] !== false;
                clearActivityLayer('other');
                addRichLayer('other', data.rides, data.stats, true);
                if (!wasVisible) toggleLayer('other');
                updateCurrentActivityDisplay();
            }
        })
        .catch(function(err) {
            console.error('Failed to fetch other rides:', err.message);
        });
    } else {
        liveRidesData.other = [];
    }

    // Update current activity after all fetches
    updateCurrentActivityDisplay();
}

function updateCurrentActivityDisplay() {
    // Find the most recent ride across all activity types
    var latestRide = null;
    var latestType = null;
    var icons = { car: '🚗', bike: '🚴', other: '🚶' };
    var names = { car: 'Car', bike: 'Bike', other: 'Walking' };

    ['car', 'bike', 'other'].forEach(function(type) {
        var rides = liveRidesData[type];
        if (rides && rides.length > 0) {
            var lastRide = rides[rides.length - 1];
            if (!latestRide || lastRide.end_timestamp > latestRide.end_timestamp) {
                latestRide = lastRide;
                latestType = type;
            }
        }
    });

    var currentActivityDiv = document.getElementById('live-current-activity');
    var contentDiv = document.getElementById('current-activity-content');

    if (!latestRide || !currentActivityDiv || !contentDiv) {
        if (currentActivityDiv) currentActivityDiv.style.display = 'none';
        return;
    }

    // Format duration
    var durationMins = Math.floor(latestRide.duration / 60);
    var durationStr = durationMins >= 60 ?
        Math.floor(durationMins / 60) + 'h ' + (durationMins % 60) + 'm' :
        durationMins + 'm';

    // Build the display
    var html = '<div class="current-activity-type">' +
        '<span class="activity-icon">' + icons[latestType] + '</span>' +
        names[latestType] + ' Ride ' + latestRide.ride_number +
        '</div>' +
        '<div class="current-activity-stats">' +
        '<span class="stat-label">Started:</span><span class="stat-value">' + (latestRide.start_datetime_str || latestRide.start_time_str) + '</span>' +
        '<span class="stat-label">Distance:</span><span class="stat-value">' + latestRide.distance.toFixed(2) + ' km</span>' +
        '<span class="stat-label">Duration:</span><span class="stat-value">' + durationStr + '</span>' +
        '<span class="stat-label">Avg Speed:</span><span class="stat-value">' + latestRide.avg_speed.toFixed(1) + ' km/h</span>' +
        '<span class="stat-label">Points:</span><span class="stat-value">' + latestRide.points.length + '</span>' +
        '</div>';

    contentDiv.innerHTML = html;
    currentActivityDiv.style.display = 'block';

    // Update speed overlay with current ride's avg speed
    updateSpeedOverlay();
}

function resetLiveMode() {
    if (!confirm('Reset live mode? This will clear all accumulated data and start fresh from now.')) {
        return;
    }

    // Stop any running animation immediately
    if (typeof stopAnimation === 'function') {
        stopAnimation();
    }

    // Remember keep-awake state before stopLivePolling() disables it, so we
    // can restore it after polling resumes (Reset should not change awake state)
    var keepAwakeWasActive = noSleepActive;
    stopLivePolling();

    // Clear live layer and activity layers from live mode
    if (typeof clearLiveLayer === 'function') {
        clearLiveLayer();
    }
    if (typeof clearActivityLayer === 'function') {
        clearActivityLayer('car');
        clearActivityLayer('bike');
        clearActivityLayer('other');
    }

    // Reset state for fresh start
    lastDrawnTimestamp = 0;
    liveRideCounts = { car: 0, bike: 0, other: 0 };
    liveRidePoints = { car: 0, bike: 0, other: 0 };
    liveRidesData = { car: [], bike: [], other: [] };
    liveAnimationShown = false;  // Reset so next data will animate
    resetHistoryState();  // Clear history navigation state

    // Hide tracking info and current activity until we have data
    var trackingInfo = document.getElementById('live-tracking-info');
    if (trackingInfo) trackingInfo.style.display = 'none';
    var currentActivity = document.getElementById('live-current-activity');
    if (currentActivity) currentActivity.style.display = 'none';
    var activitySummary = document.getElementById('live-activity-summary');
    if (activitySummary) activitySummary.style.display = 'none';

    var resetBtn = document.getElementById('live-reset-btn');
    resetBtn.disabled = true;
    resetBtn.textContent = 'Resetting...';

    fetch('/api/live/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reset: true })
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        resetBtn.disabled = false;
        resetBtn.textContent = 'Reset to Now';

        if (!data.success) {
            alert('Failed to reset: ' + data.error);
            return;
        }

        liveData = data;
        updateLiveUI(data);

        // Clear activity summary since we're starting fresh
        document.getElementById('live-activity-summary').style.display = 'none';

        startLivePolling();

        // Restore keep-awake if it was active before the reset
        if (keepAwakeWasActive) enableKeepAwake();
    })
    .catch(function(err) {
        resetBtn.disabled = false;
        resetBtn.textContent = 'Reset to Now';
        alert('Failed to reset: ' + err.message);
    });
}

function updateLiveUI(data) {
    // Update start time
    if (data.start_time_str) {
        document.getElementById('live-start-time').textContent = data.start_time_str;
    }

    // Update session duration
    if (data.start_timestamp) {
        var now = Math.floor(Date.now() / 1000);
        var duration = now - data.start_timestamp;
        var hours = Math.floor(duration / 3600);
        var mins = Math.floor((duration % 3600) / 60);
        document.getElementById('live-duration').textContent = '(' + hours + 'h ' + mins + 'm ago)';
    }

    // Update total points
    document.getElementById('live-total-points').textContent = (data.total_points || 0).toLocaleString();

    // Update tracking stats (distance, duration, speed, time)
    if (data.total_points > 0) {
        updateLiveTrackingStats(data.total_distance, data.total_duration, data.last_point_time);
    }

    // Update activity stats (past rides - excluding current)
    if (data.stats && Object.keys(data.stats).length > 0) {
        var statsContent = document.getElementById('live-stats-content');
        var html = '';
        var icons = { car: '🚗', bike: '🚴', other: '🚶' };
        var names = { car: 'Car', bike: 'Bike', other: 'Walking' };

        // Get all past rides (all except the most recent one which is shown in Current Activity)
        var allRides = [];
        ['car', 'bike', 'other'].forEach(function(type) {
            var rides = liveRidesData[type] || [];
            rides.forEach(function(ride) {
                allRides.push({ type: type, ride: ride });
            });
        });

        // Sort by end timestamp descending (most recent first), skip the first one (current)
        allRides.sort(function(a, b) { return b.ride.end_timestamp - a.ride.end_timestamp; });
        var pastRides = allRides.slice(1);  // Skip current activity

        if (pastRides.length > 0) {
            pastRides.forEach(function(item) {
                var ride = item.ride;
                var type = item.type;
                var durationMins = Math.floor(ride.duration / 60);
                var durationStr = durationMins >= 60 ?
                    Math.floor(durationMins / 60) + 'h ' + (durationMins % 60) + 'm' :
                    durationMins + 'm';

                html += '<div class="past-ride-item">' +
                    '<span class="past-ride-icon">' + icons[type] + '</span> ' +
                    '<strong>' + names[type] + ' ' + ride.ride_number + '</strong><br>' +
                    '<span class="past-ride-details">' +
                    (ride.start_datetime_str || ride.start_time_str) + ' • ' +
                    ride.distance.toFixed(1) + ' km • ' +
                    durationStr + ' • ' +
                    ride.avg_speed.toFixed(1) + ' km/h' +
                    '</span></div>';
            });
        } else {
            // Show summary if no detailed ride data yet
            ['car', 'bike', 'other'].forEach(function(type) {
                var s = data.stats[type];
                if (s && s.total_points > 0) {
                    html += '<div>' + icons[type] + ' ' + names[type] + ': ' +
                            '<span class="stat-value">' + s.count + ' rides, ' +
                            s.total_distance + ' km</span></div>';
                }
            });
        }

        if (html) {
            statsContent.innerHTML = html;
            document.getElementById('live-activity-summary').style.display = 'block';
        }
    }
}

function updateLiveTrackingStats(distance, duration, timeStr) {
    // Show the tracking info section
    var trackingInfo = document.getElementById('live-tracking-info');
    if (trackingInfo) {
        trackingInfo.style.display = 'block';
    }

    // Update distance
    var distEl = document.getElementById('live-stat-distance');
    if (distEl && distance !== undefined) {
        distEl.textContent = distance.toFixed(2) + ' km';
    }

    // Update duration
    var durEl = document.getElementById('live-stat-duration');
    if (durEl && duration !== undefined) {
        var hours = Math.floor(duration / 3600);
        var mins = Math.floor((duration % 3600) / 60);
        durEl.textContent = hours + 'h ' + mins + 'm';
    }

    // Update avg speed
    var speedEl = document.getElementById('live-stat-speed');
    if (speedEl && distance !== undefined && duration !== undefined && duration > 0) {
        var speed = distance / duration * 3600;
        speedEl.textContent = speed.toFixed(1) + ' km/h';
    }

    // Update time
    var timeEl = document.getElementById('live-stat-time');
    if (timeEl && timeStr) {
        timeEl.textContent = timeStr;
    }
}

function setupLiveAnimationProgress() {
    // Hook into animation progress callback for live mode
    onAnimationProgress = function(info) {
        updateLiveTrackingStats(info.distance, info.duration, null);

        // Format timestamp if available
        if (info.timestamp) {
            var date = new Date(info.timestamp * 1000);
            var timeStr = date.toLocaleTimeString();
            var timeEl = document.getElementById('live-stat-time');
            if (timeEl) {
                timeEl.textContent = timeStr;
            }
        }

        // Update points count
        var pointsEl = document.getElementById('live-total-points');
        if (pointsEl) {
            pointsEl.textContent = info.pointIndex.toLocaleString();
        }
    };
}

function clearLiveAnimationProgress() {
    onAnimationProgress = null;
}

function updateLiveIndicator(active) {
    var indicator = document.getElementById('live-indicator');
    var statusText = document.getElementById('live-status-text');

    if (active) {
        indicator.classList.add('active');
        statusText.classList.add('active');
        statusText.textContent = 'Live';
    } else {
        indicator.classList.remove('active');
        statusText.classList.remove('active');
        statusText.textContent = 'Stopped';
    }
}

function loadLiveTrack(animate, onComplete) {
    // Default to true for animation on first load
    if (animate === undefined) animate = true;

    // Show tracking info section
    var trackingInfo = document.getElementById('live-tracking-info');
    if (trackingInfo) {
        trackingInfo.style.display = 'block';
    }

    fetch('/api/live/track/all')
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (!data.success) {
            console.log('No live track data yet');
            if (onComplete) onComplete();
            return;
        }

        if (data.points && data.points.length > 0) {
            // Initialize history with existing points
            initializeHistoryFromPoints(data.points);

            if (animate && typeof addBasicLayerAnimated === 'function') {
                // Set up animation progress callback for live stats
                setupLiveAnimationProgress();

                // Animate the initial track playback
                addBasicLayerAnimated('live', data.points, data.stats,
                    data.start_time_str, data.end_time_str, function() {
                        // Animation complete - clear callback and update timestamp
                        clearLiveAnimationProgress();
                        lastDrawnTimestamp = data.points[data.points.length - 1].tst;
                        updateHistoryPanel();  // Show history panel after animation
                        if (onComplete) onComplete();
                    });
            } else {
                // Draw instantly (for resume or when animation not available)
                drawLiveTrackInstant(data.points);
                lastDrawnTimestamp = data.points[data.points.length - 1].tst;
                // Update tracking stats from data
                if (data.stats) {
                    updateLiveTrackingStats(data.stats.distance, data.stats.duration, data.end_time_str);
                }
                updateHistoryPanel();  // Show history panel
                if (onComplete) onComplete();
            }
        } else {
            if (onComplete) onComplete();
        }
    })
    .catch(function(err) {
        console.error('Failed to load live track:', err.message);
        if (onComplete) onComplete();
    });
}

function drawLiveTrackInstant(points) {
    // Use map.js functions to draw track
    if (typeof initLiveLayer === 'function') {
        initLiveLayer();
        for (var i = 0; i < points.length; i++) {
            appendLivePoint(points[i]);
        }
        fitMapToLivePoints(points);
        // Update lastDrawnTimestamp to the last point
        if (points.length > 0) {
            lastDrawnTimestamp = points[points.length - 1].tst;
        }
    } else {
        // Fallback - draw using basic layer
        addBasicLayer('live', points, {}, '', '');
    }
}

function appendLivePoints(newPoints) {
    // Append new points to map
    if (typeof appendLivePoint === 'function') {
        for (var i = 0; i < newPoints.length; i++) {
            appendLivePoint(newPoints[i]);
        }
        // Pan to latest point (only if not in history mode)
        if (newPoints.length > 0 && !historyModeActive) {
            var last = newPoints[newPoints.length - 1];
            if (typeof map !== 'undefined' && map) {
                map.panTo({ lat: last.lat, lng: last.lng });
            }
        }
    } else {
        // Fallback - reload entire track (no animation since we're already tracking)
        loadLiveTrack(false);
    }
}

// =============================================================================
// History Navigation Functions
// =============================================================================

function addPointsToHistory(newPoints) {
    // Add points to history array and calculate cumulative stats
    for (var i = 0; i < newPoints.length; i++) {
        var point = newPoints[i];
        historyPoints.push(point);

        // Calculate cumulative stats
        var pointIndex = historyPoints.length - 1;
        var cumulativeDistance = 0;
        var duration = 0;

        if (pointIndex > 0) {
            // Get previous cumulative distance
            cumulativeDistance = historyCumulativeStats[pointIndex - 1].distance;

            // Add distance from previous point to this one
            var prevPoint = historyPoints[pointIndex - 1];
            var segmentDist = haversineDistance(
                prevPoint.lat, prevPoint.lng,
                point.lat, point.lng
            );
            if (segmentDist >= 0.01) {  // Only count if >= 10 meters
                cumulativeDistance += segmentDist * 1.05;  // 5% road factor
            }

            // Duration from first point
            duration = point.tst - historyPoints[0].tst;
        }

        historyCumulativeStats.push({
            tst: point.tst,
            distance: cumulativeDistance,
            duration: duration,
            pointCount: pointIndex + 1
        });
    }
}

function haversineDistance(lat1, lng1, lat2, lng2) {
    // Calculate distance between two points in km
    var R = 6371;
    var dLat = (lat2 - lat1) * Math.PI / 180;
    var dLng = (lng2 - lng1) * Math.PI / 180;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLng / 2) * Math.sin(dLng / 2);
    var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

function updateHistoryPanel() {
    var panel = document.getElementById('history-panel');
    if (!panel) return;

    var totalPoints = historyPoints.length;
    if (totalPoints === 0) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';

    // Determine current view index
    var viewIndex = historyModeActive ? historyViewIndex : totalPoints - 1;
    var stats = historyCumulativeStats[viewIndex];
    var point = historyPoints[viewIndex];

    if (!stats || !point) return;

    // Update label (LIVE vs VIEWING)
    var label = document.getElementById('history-label');
    if (label) {
        if (historyModeActive) {
            label.textContent = '📍 VIEWING • Point ' + (viewIndex + 1) + '/' + totalPoints;
            label.className = 'history-label viewing';
        } else {
            label.textContent = '📍 LIVE • Point ' + totalPoints + '/' + totalPoints;
            label.className = 'history-label live';
        }
    }

    // Update timestamp
    var timeEl = document.getElementById('history-time');
    if (timeEl) {
        var d = new Date(point.tst * 1000);
        var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        timeEl.textContent = months[d.getMonth()] + ' ' + d.getDate() + ', ' +
            d.getHours().toString().padStart(2, '0') + ':' +
            d.getMinutes().toString().padStart(2, '0');
    }

    // Update stats
    var distanceEl = document.getElementById('history-distance');
    if (distanceEl) {
        distanceEl.textContent = stats.distance.toFixed(2) + ' km';
    }

    var durationEl = document.getElementById('history-duration');
    if (durationEl) {
        var hours = Math.floor(stats.duration / 3600);
        var mins = Math.floor((stats.duration % 3600) / 60);
        var secs = stats.duration % 60;
        if (hours > 0) {
            durationEl.textContent = hours + 'h ' + mins + 'm';
        } else {
            durationEl.textContent = mins + 'm ' + secs + 's';
        }
    }

    var speedEl = document.getElementById('history-speed');
    if (speedEl) {
        var avgSpeed = stats.duration > 0 ? (stats.distance / stats.duration * 3600) : 0;
        speedEl.textContent = avgSpeed.toFixed(1) + ' km/h';
    }

    // Update button states
    updateHistoryButtons();
}

function updateHistoryButtons() {
    var totalPoints = historyPoints.length;
    var viewIndex = historyModeActive ? historyViewIndex : totalPoints - 1;

    var backBtn = document.getElementById('history-back');
    var back10Btn = document.getElementById('history-back10');
    var fwdBtn = document.getElementById('history-forward');
    var fwd10Btn = document.getElementById('history-forward10');
    var liveBtn = document.getElementById('history-live');

    // Back buttons: disabled at first point
    var atStart = viewIndex <= 0;
    if (backBtn) backBtn.disabled = atStart;
    if (back10Btn) back10Btn.disabled = atStart;

    // Forward buttons: disabled at last point (live mode)
    var atEnd = viewIndex >= totalPoints - 1;
    if (fwdBtn) fwdBtn.disabled = atEnd;
    if (fwd10Btn) fwd10Btn.disabled = atEnd;

    // Live/Old button: show "Old" when at live position, "LIVE" when in history
    if (liveBtn) {
        if (historyModeActive) {
            liveBtn.textContent = 'LIVE';
            liveBtn.style.display = 'inline-block';
        } else if (totalPoints > 1) {
            liveBtn.textContent = 'OLD';
            liveBtn.style.display = 'inline-block';
        } else {
            liveBtn.style.display = 'none';
        }
    }

    // Disable Live layer toggle button when in history mode
    var liveLayerToggle = document.getElementById('live-layer-toggle');
    if (liveLayerToggle) {
        liveLayerToggle.disabled = historyModeActive;
        liveLayerToggle.style.opacity = historyModeActive ? '0.4' : '1';
        liveLayerToggle.style.cursor = historyModeActive ? 'not-allowed' : 'pointer';
    }
}

function navigateHistory(delta) {
    var totalPoints = historyPoints.length;
    if (totalPoints === 0) return;

    if (!historyModeActive) {
        // Entering history mode
        historyModeActive = true;
        historyViewIndex = totalPoints - 1;
    }

    // Apply delta
    historyViewIndex += delta;

    // Clamp to valid range
    if (historyViewIndex < 0) historyViewIndex = 0;
    if (historyViewIndex >= totalPoints) {
        // Reached the end - exit history mode
        exitHistoryMode();
        return;
    }

    // Update polyline display
    if (typeof truncateLivePolyline === 'function') {
        truncateLivePolyline(historyViewIndex);
    }

    // Update position marker
    var point = historyPoints[historyViewIndex];
    if (point && typeof updateHistoryMarker === 'function') {
        updateHistoryMarker(point.lat, point.lng);
    }

    // Pan map to current position
    if (point && typeof map !== 'undefined' && map) {
        map.panTo({ lat: point.lat, lng: point.lng });
    }

    // Update panel display
    updateHistoryPanel();
}

function exitHistoryMode() {
    historyModeActive = false;
    historyViewIndex = -1;

    // Restore full polyline
    if (typeof restoreLivePolyline === 'function') {
        restoreLivePolyline();
    }

    // Remove position marker
    if (typeof removeHistoryMarker === 'function') {
        removeHistoryMarker();
    }

    // Pan to latest point
    if (historyPoints.length > 0) {
        var last = historyPoints[historyPoints.length - 1];
        if (typeof map !== 'undefined' && map) {
            map.panTo({ lat: last.lat, lng: last.lng });
        }
    }

    // Update panel display
    updateHistoryPanel();
}

function handleHistoryJumpButton() {
    // Handles both "Old" (jump to start) and "Live" (jump to end) button clicks
    if (historyModeActive) {
        // In history mode - jump to live (latest point)
        exitHistoryMode();
    } else {
        // At live position - jump to first point (oldest)
        var totalPoints = historyPoints.length;
        if (totalPoints <= 1) return;

        historyModeActive = true;
        historyViewIndex = 0;

        // Update polyline display
        if (typeof truncateLivePolyline === 'function') {
            truncateLivePolyline(0);
        }

        // Update position marker
        var point = historyPoints[0];
        if (point && typeof updateHistoryMarker === 'function') {
            updateHistoryMarker(point.lat, point.lng);
        }

        // Pan map to first point
        if (point && typeof map !== 'undefined' && map) {
            map.panTo({ lat: point.lat, lng: point.lng });
        }

        // Update panel display
        updateHistoryPanel();
    }
}

function resetHistoryState() {
    // Called when resetting live mode or switching modes
    historyModeActive = false;
    historyViewIndex = -1;
    historyPoints = [];
    historyCumulativeStats = [];
    // Clear map.js history state (polyline, marker, livePathsHidden flag)
    if (typeof clearHistoryState === 'function') {
        clearHistoryState();
    }
    var panel = document.getElementById('history-panel');
    if (panel) panel.style.display = 'none';
}

function initializeHistoryFromPoints(points) {
    // Initialize history arrays from existing points (when joining/resuming)
    historyPoints = [];
    historyCumulativeStats = [];
    historyModeActive = false;
    historyViewIndex = -1;

    if (!points || points.length === 0) return;

    var cumulativeDistance = 0;

    for (var i = 0; i < points.length; i++) {
        var point = points[i];
        historyPoints.push(point);

        if (i > 0) {
            var prevPoint = points[i - 1];
            var segmentDist = haversineDistance(
                prevPoint.lat, prevPoint.lng,
                point.lat, point.lng
            );
            if (segmentDist >= 0.01) {
                cumulativeDistance += segmentDist * 1.05;
            }
        }

        var duration = i > 0 ? (point.tst - points[0].tst) : 0;

        historyCumulativeStats.push({
            tst: point.tst,
            distance: cumulativeDistance,
            duration: duration,
            pointCount: i + 1
        });
    }
}
