# iPhone Tracker Project Plan

**Status:** Canonical planning document  
**Last updated:** 2026-07-31

## Purpose

This is the single source of truth for planning future work on iPhone Tracker.
Use this file for active work, priorities, decisions, and short completion notes.
Older documents in this folder are historical references and should not be
extended with new phases.

## Security and Privacy Rules

This file is tracked in Git and must be safe for a public repository.

- Never include API keys, tokens, passwords, webhook URLs, session keys,
  private certificates, or actual environment-variable values.
- Never include private IP addresses, internal hostnames, device identifiers,
  usernames, precise home locations, or raw GPS coordinates.
- Refer to configuration only by environment-variable name, and use placeholders
  such as `<OWNTRACKS_HOST>` when an example needs an infrastructure value.
- Review this file's Git diff for sensitive information before every commit.

## Current Product State

iPhone Tracker is a Flask web application that reads OwnTracks GPS data and
activity markers, classifies travel into car, bike, and other activities, and
displays tracks and statistics on an interactive map.

The application currently includes:

- Date/time-based activity detection and map playback
- Live tracking with periodic GPS polling and session recovery
- Car, bike, and other activity summaries
- Live history navigation and slider-based playback
- Push notifications for activity transitions
- Saved interactive maps and track summary images
- Start/end markers and GPS metadata for saved track images
- Mobile-focused controls, dark mode, screen wake lock, and HTTPS deployment
- Single-process gevent deployment to preserve shared in-memory state

## Active Work

No feature is currently marked as active.

When starting work, add one item here with:

- Goal and user benefit
- Scope and non-goals
- Files or components expected to change
- Implementation steps
- Acceptance criteria and tests
- Status: Planned, In progress, Blocked, or Ready for review

Only one major feature should normally be active at a time.

## Prioritized Backlog

### 1. Trip History and Calendar

Allow users to browse previously detected trips by day, week, or month without
manually entering date ranges. Show distance, duration, activity type, and
frequently visited places.

### 2. Activity Corrections

Allow users to relabel an activity, merge or split trips, exclude incorrect GPS
points, and save corrections so detected results can be trusted and refined.

### 3. Live Tracking Diagnostics

**Status:** Complete and verified on iPhone 2026-07-11

#### Goal and User Benefit

Explain exceptional tracking conditions without duplicating the existing
bottom-center GPS freshness display. Users should be able to distinguish an old
GPS fix from a browser connectivity problem, an application/API failure, or a
delayed batch upload.

#### Existing Behavior to Preserve

- Keep the compact bottom-center speed and last-fix-age panel unchanged.
- Continue calculating freshness from the newest GPS point timestamp.
- Preserve the current colors: green below 2 minutes, orange from 2-5 minutes,
  and red at 5 minutes or more.
- Do not add another persistent "Last GPS update" card during normal operation.

#### Proposed Experience

- Show a compact, exception-only status pill immediately above the existing
  speed/fix panel.
- Keep the pill to one short line, such as `PHONE OFFLINE`, `SERVER UNREACHABLE`,
  or `DELAYED DATA RECEIVED`.
- Make the pill at least 44 pixels tall and respect the iPhone safe area.
- Tapping the pill opens a small bottom sheet with the last GPS fix age, last
  successful poll age, a plain-language explanation, and recovery status.
- Show the same detailed state in the Live sidebar below its current status row.
- Hide the pill automatically after recovery. Normal tracking shows no pill.

#### Diagnostic States

- **Browser offline:** Show immediately when the browser reports that it is
  offline; remove after connectivity returns and a poll succeeds.
- **Application/API unreachable:** Show after two consecutive poll failures to
  avoid flashing on a single transient error.
- **Upstream tracking service unavailable:** The backend must distinguish an
  OwnTracks request failure from a successful request containing no new GPS
  points. Do not label ordinary GPS silence as a server failure.
- **Delayed batch received:** Show a temporary informational pill when multiple
  historical GPS points arrive together and the newest received fix is already
  stale. Return to the normal freshness display when a current fix arrives.
- **No fresh GPS data:** Use only the existing orange/red age indicator when
  polling succeeds but the phone has supplied no newer point.

#### Technical Scope

- `static/js/app.js`: diagnostic state machine, consecutive-failure tracking,
  browser online/offline handling, batch detection, recovery, and bottom sheet.
- `templates/index.html`: exception pill, accessible status text, and diagnostic
  detail container.
- `static/css/style.css`: responsive pill and bottom-sheet styling, including
  safe-area spacing and dark-mode colors.
- `lib/owntracks.py` and `app.py`: preserve upstream request outcome separately
  from an empty successful result and return non-sensitive health metadata.

#### Implementation and Verification

Implemented an exception-only map pill, matching Live sidebar status, and a
tap-open detail sheet. Live polling now distinguishes browser connectivity,
application/API failures, OwnTracks availability, delayed batches, and ordinary
GPS silence without duplicating the existing freshness indicator.

During iPhone testing, landscape mode exposed a pre-existing responsive-layout
problem: the wider landscape viewport selected desktop sidebar rules, `100vh`
did not match Safari's visible height, and the hamburger position used `85vw`
even though the sidebar was capped at 380 pixels. Later fixes initially appeared
ineffective because iPhone retained older CSS and JavaScript.

The verified fix:

- Treat short, coarse-pointer landscape screens as mobile layouts
- Synchronize layout height with the Visual Viewport API
- Respect safe areas and raise/compact bottom overlays in landscape
- Keep the hamburger aligned with the capped sidebar and handle `touchend`
- Let both `touchend` and `click` satisfy pending iPhone Wake Lock acquisition
- Trigger a Google Maps resize after rotation
- Version static assets by modification time and disable caching for the HTML shell

Verified manually on iPhone in portrait and landscape: full-width map, complete
speed/freshness panel, responsive hamburger, offline warning, detail sheet, and
recovery behavior.

#### Non-Goals

- Changing the existing freshness thresholds or colors
- Replacing the bottom-center speed/fix panel
- Showing a permanent healthy/current status message on the map
- Sending Pushcut notifications in the first version
- Displaying server addresses, private hostnames, device identifiers, or other
  sensitive infrastructure details

#### Acceptance Criteria

1. Normal tracking looks exactly as it does today, with no additional banner.
2. A stale GPS fix with successful polling shows only the existing age color.
3. Browser offline and repeated API failures produce distinct, accurate labels.
4. An OwnTracks failure is not reported as ordinary "no new data," and ordinary
   GPS silence is not reported as a server failure.
5. A delayed batch produces a temporary informational state and does not reset
   freshness to green unless the newest GPS timestamp is actually current.
6. Tapping the pill opens readable details and recovery information.
7. The pill and detail sheet work on iPhone without covering playback controls,
   map controls, or the safe area.
8. All messages avoid credentials and sensitive infrastructure information.

### 4. Export and Privacy Controls

Add GPX, GeoJSON, or CSV export and an option to hide the beginning and end of
a route near sensitive locations such as home.

### 5. Active Layer Panel Readability

**Status:** Complete and visually verified 2026-07-11

#### Goal

Improve readability of distance, duration, and speed in the Live map's Active
Layers panel without making the panel wider.

#### Design

- Keep one compact row per active layer.
- Preserve each activity icon but remove the visible activity name.
- Give Live a unique magenta dot instead of sharing the All-layer pin icon.
- Reuse the pulsing magenta dot for the history status only when it is `LIVE`;
  retain the static pin and orange treatment when reviewing `VIEWING` history.
- Apply a subtle pulse to the Live dot, disabled when reduced motion is preferred.
- Increase layer-row statistics from 10px to a responsive 12-14px and retain
  compact separators.
- Increase the history label, timestamp, and summary statistics to 14px while
  preserving the existing panel width.
- Preserve Hide/Show controls and the panel's approximate current width.
- Keep activity identity available through `title` and `aria-label` attributes.
- Keep All, Car, Bike, and Other icons unchanged.

#### Acceptance Criteria

1. Distance, duration, and speed are noticeably easier to read.
2. The panel does not become wider than its current visual footprint.
3. Activity names are not displayed in layer rows.
4. Live is clearly distinct from All without relying on visible text.
5. Every icon and visibility button retains an accessible activity label.
6. Long statistics remain on one line without overlapping Hide/Show controls.
7. The layout remains usable in iPhone portrait and landscape modes.

## Technical Decisions

### Ride statistics are measured over the GPS point span

**Decided:** 2026-07-31

A ride's distance is computed entirely from GPS fixes, so its duration and
average speed are only meaningful over the interval those fixes cover. Every
ride therefore reports statistics over a **stat window**: the intersection of
the ride's declared window with the span of its GPS points, produced by
`ride_stat_window()` in `lib/activities.py`.

This matters because `ride['start']` and `ride['end']` mean different things
per activity type:

| Type | Declared window | GPS points | Intersection resolves to |
| --- | --- | --- | --- |
| car, bike | External marker times, wider than the track | Filtered to the marker window | First and last fix |
| other | Movement boundaries, narrower than the track | Untrimmed, keeps stationary head and tail | The movement boundaries |

Car and bike markers do not come from the phone being tracked. Bike markers are
emitted by a motion classifier with activity/inactivity confirmation delays, and
car markers are driven by the vehicle's own GPS unit through a 240-second
inactivity trigger. Both bracket the phone's track on either side, so a ride
measured from marker to marker mixes two independent clocks and consistently
inflates duration while deflating average speed. Observed marker lead on car
trips is roughly 45 seconds at the start; on a bike ride it reached 2m38s.

Walking rides have no markers. `find_movement_boundaries()` already trims
`ride['start']` and `ride['end']` back to real movement, but `ride['points']`
deliberately keeps the stationary head and tail because walking end detection
depends on them. Measuring to `points[-1]` therefore re-added a stationary tail
of up to the 30-minute ride-split threshold; one real walk was reported as 37
minutes instead of 6.

Consequences of this convention:

- Date/time mode and Live mode report identical figures for the same ride. They
  previously disagreed because the Live history panel already measured fix to
  fix while date/time mode measured from the marker.
- Ride segmentation is unaffected. Declared windows still assign points to
  rides, and the minimum-duration and minimum-point filters are unchanged.
- `ride['points']` is never trimmed, so walking start/end detection in
  `lib/notifications.py` keeps working.
- The activity timeline keeps raw marker timestamps. It is an event log, not a
  statistic.

Related history: a 2026-03 change moved the ride **end** off the marker and onto
the last GPS fix for the same reason, but left the start on the marker and did
not account for the walking case. This decision completes that work and is
recorded here because the earlier rationale survived only in a commit message.

Known residual differences between the two modes, accepted for now:

- A Live session started mid-ride holds fewer points than a later date/time
  query, so distance itself can differ for that ride.
- The Live history panel is session-scoped, not ride-scoped. A session
  containing more than one activity shows a session total there.

**Verified end to end on 2026-07-31.** A controlled ride recorded with the Live
session started before departure produced identical figures in both modes: same
point count, same distance, same duration to the second, same average speed.
Marker lead measured across three car trips that day was consistently 42 to 45
seconds at the start, and the end marker trailed the last GPS fix by just under
the vehicle trigger's 240-second timeout.

### TLS uses a private CA whose signing key is kept off the shared tree

**Decided:** 2026-07-31

The application is served over HTTPS so that the browser Wake Lock API is
available. Its certificate was originally a long-lived, self-signed **CA**
certificate whose private key sat inside the bind-mounted source tree and was
world-readable over the file share. No client could verify it, so browsers
relied on click-through exceptions while their speculative preconnect sockets
failed the handshake continuously and filled the container log with stack
traces.

Two properties made that certificate unsafe to fix by simply trusting it: it was
a CA, so anything signed with it would be trusted for *any* host name, and its
key was readable by anyone who could reach the file share.

The current arrangement:

- A private CA lives outside the shared tree in a root-owned directory, with the
  key at mode 600. Nothing reachable over the file share can sign with it.
- The CA carries `pathlen:0` and a critical `nameConstraints` extension limiting
  it to the application host's two DNS names and its single address.
- The server certificate is a separate 825-day leaf, `CA:FALSE`, `serverAuth`
  only, with the host names in `subjectAltName`.
- Devices install and trust **only the CA certificate**, so reissuing the server
  certificate needs no change on any device.

Notes for whoever renews it:

- iOS offers its "Certificate Trust Settings" toggle only for **root CA**
  certificates. A self-signed leaf can be installed but never trusted, so the CA
  layer is required for iPhone support even though a bare leaf is sufficient on
  Windows. This is not obvious and cost an extra round trip to discover.
- Apple's 398-day certificate lifetime limit does not apply to certificates
  issued by user-added root CAs, so an 825-day server certificate is accepted
  and yearly renewals are not required.
- A private CA publishes no CRL. Browsers soft-fail unknown revocation for
  locally installed roots, but some command-line tools treat it as fatal and
  need an explicit flag to skip the check. A tool failing this way does not
  indicate a broken chain.
- The server certificate expires in November 2028. Renewal is a server-side
  reissue plus a container restart; devices are unaffected.

## Runbooks

### The app stops loading with a certificate error on every device at once

Almost certainly the server certificate has expired. It is valid until
**November 2028**. Renewal is deliberately not automated: the failure is loud,
self-announcing, and costs nothing while it waits, so it is fixed on demand
rather than guarded by a scheduled job.

**Nothing needs to be done on any phone or computer.** Devices trust the CA, not
the server certificate, and the CA is valid until 2036. Reissuing from the same
CA is accepted immediately.

**Prerequisite:** shell access to the application host as a user who can `sudo`,
plus the ability to restart the web container. Connection details are
deliberately not recorded in this file, which is tracked in a public repository.

Confirm the diagnosis first:

```
openssl x509 -in <APP_DIR>/certs/cert.pem -noout -subject -issuer -enddate
```

Then, on the host, as root. Substitute the two DNS names and the address the
devices actually use; they must match the previous certificate exactly:

```
CA=<CA_DIR>                 # holds ca.key and ca.crt, outside the shared tree
APP=<APP_DIR>/certs
S=$(mktemp -d)

openssl genrsa -out "$S/server.key" 2048
openssl req -new -key "$S/server.key" -subj "/CN=<HOST_DNS>" -out "$S/server.csr"

cat > "$S/ext.cnf" <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:<HOST_DNS>,DNS:<HOST_DNS_ALT>,IP:<HOST_IP>
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF

openssl x509 -req -in "$S/server.csr" -CA "$CA/ca.crt" -CAkey "$CA/ca.key" \
  -CAcreateserial -days 825 -sha256 -extfile "$S/ext.cnf" -out "$S/server.crt"

openssl verify -CAfile "$CA/ca.crt" "$S/server.crt"      # must print: OK

cp "$S/server.crt" "$APP/cert.pem"
cp "$S/server.key" "$APP/key.pem"
chown root:root "$APP/cert.pem" "$APP/key.pem"
chmod 644 "$APP/cert.pem"
chmod 600 "$APP/key.pem"
rm -rf "$S"

docker restart <WEB_CONTAINER>
```

Verify, then reload the app on a device:

```
openssl s_client -connect <HOST>:5000 </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

Notes:

- The SAN list must cover every name and address used to reach the app. A name
  missing here produces a certificate error on exactly the devices that use it.
- `key.pem` must end up mode 600 and owned by root. The web container runs as
  root and can still read it; the file share cannot. Leaving it world-readable
  reintroduces the problem this design exists to prevent.
- The restart clears the in-memory live session. The saved session survives, so
  the next page load offers to resume it.
- A command-line tool may still refuse the new certificate over unknown
  revocation. That is expected for a private CA and does not indicate a bad
  chain; see the TLS decision above.

### The CA certificate expires (2036)

A different and larger job. Generating a new CA means the new server certificate
no longer chains to anything the devices trust, so **every device must install
and trust the new CA** before it will connect. Plan for hands-on time with each
phone and computer, and keep the old CA in place until every device has been
migrated. The original CA and server certificates were created on 2026-07-31;
the commands used are recoverable from the repository history.

## Known Issues

### Discarding a live session is the default answer to a dismissed prompt

**Observed:** 2026-07-31. **Status:** the destructive default is confirmed by
inspection and by testing. The incident that prompted the investigation remains
unexplained, but the app is not silently discarding sessions.

A live session was replaced by a new one at the moment the app was opened on a
phone, its start timestamp rewritten and everything accumulated before it
discarded. The user recalled taking no reset action and seeing no prompt.

**What controlled testing showed.** Two tests were run the same day. With a warm
in-memory cache, opening the app on a second device joined the existing session
and preserved it, and both display modes then agreed exactly. With the cache
deliberately emptied by a worker reload and no client polling in between,
opening the app on the phone **did** present the resume prompt, and choosing to
resume restored the session intact, including every accumulated point. So the
destructive branch is not reachable without either dismissing that prompt or
pressing Reset to Now. The remaining explanations for the original incident are
a reflexively dismissed prompt or an unremembered reset, neither of which can be
distinguished after the fact.

The durable finding behind it is an asymmetry between two endpoints facing the
same situation, a saved session on disk with an empty in-memory cache:

| Endpoint | Behaviour |
| --- | --- |
| `/api/live/poll` | auto-recovers, keeping the original start timestamp |
| `/api/live/start` | discards the saved session and starts fresh from now |

`live_start` resumes only when the caller passes `resume: true`. Both
`joinLiveSession()` and `startLiveMode()` post an empty body, so the backend
cannot distinguish a rejoin from a deliberate fresh start, and the fallback is
the destructive branch.

Two things keep this rare. The in-memory cache is emptied only by a worker
restart, and any client that is polling repairs the session through
`/api/live/poll` within one poll interval, usually before another client calls
`/api/live/start`. That is the likely reason the resume prompt is almost never
seen in practice.

The core hazard is the prompt's polarity. It asks whether to resume, so the
answer that **discards** the session is the one a user taps to make a popup go
away, and a browser that suppresses the dialog returns the same value. The Reset
to Now prompt is the opposite way round: a dismissed dialog there does nothing.
A prompt whose safe answer is "confirm" and whose destructive answer is
"dismiss" is backwards regardless of how the original incident is explained.

**What the container logs establish.** On the day of the incident the only
worker restarts were the six caused by a deployment, within a single 30-second
window, and no `AUTO-RECOVERING` line appears anywhere that day. The in-memory
cache was therefore empty continuously from that deployment until the session
was replaced, several hours later. Two explanations remain, and the logs cannot
separate them because gunicorn runs without `--access-logfile` and so records no
request line: either the app replaced the session on page load, or the user
pressed Reset to Now at that moment. Enabling access logging would make any
future occurrence unambiguous.

**Reproduction:** start a live session; restart the worker, for which touching
any source file the app imports is enough; ensure no client polls in between;
then open the app on another device. The resume prompt appears, and resuming
preserves the session.

**Recommended fix.** Remove the choice rather than re-word it: resume a
non-stale session automatically instead of prompting. Reset to Now already
exists for discarding one deliberately and carries its own correctly-polarised
confirmation, so the prompt asks a question the user has already been given a
better way to answer. This is a small frontend change and is sufficient on its
own.

An earlier, broader proposal to restructure `live_start` and to have
`joinLiveSession()` declare its intent is **not** needed: testing showed those
paths behave correctly. The backend fallback is still destructive for a caller
that passes neither flag, so making it resume instead remains a cheap
belt-and-braces improvement, but it is no longer load-bearing.

**Worth doing regardless:** gunicorn runs without `--access-logfile`, so there
is no record of which request replaced a session. Adding it would make any
future occurrence unambiguous and cost nothing.

### The push worker does not pick up code changes

Only the web container runs with auto-reload. The push worker container loads
its modules once at start, so changes to `lib/notifications.py` and anything
else it imports take effect only when that container is restarted. After the
2026-07-31 statistics change, the worker kept sending notifications computed
with the previous formula until it was restarted.

## Completed Milestones

- 2026-02: Converted the original tracker into a Flask web application
- 2026-02: Added Live Mode, session persistence, history, and activity layers
- 2026-02: Added push notifications and live-mode resilience improvements
- 2026-03: Added synchronized polling, visual poll status, and slider navigation
- 2026-03: Added track-art images, start/end markers, and EXIF GPS metadata
- 2026-03: Added HTTPS wake lock support and gevent-based deployment
- 2026-03: Made Live Mode the default and improved mobile startup behavior
- 2026-07: Added verified Live Tracking Diagnostics and iPhone landscape fixes
- 2026-07: Improved Active Layers readability with larger statistics and a unique Live icon
- 2026-07: Restored verified iPhone Screen Awake behavior after mobile touch handling changes
- 2026-07: Fixed multi-day activity detection by fetching OwnTracks data in chunks
- 2026-07: Fixed map recentering during dense multi-day track playback
- 2026-07: Reconciled Live and date/time ride statistics on a shared GPS stat window
- 2026-07: Replaced the exposed self-signed TLS certificate with a name-constrained private CA

## Planning Workflow

1. Choose the highest-priority backlog item or add a newly agreed item.
2. Move its full specification into **Active Work** before changing code.
3. Record material technical decisions in the active item as they are made.
4. Keep implementation notes concise; Git commits remain the detailed history.
5. After verification, add a dated line to **Completed Milestones**.
6. Clear **Active Work** and select the next item.

Do not create additional `Phase_*_Plan.md` files for normal feature work. A
separate document is appropriate only for durable architecture, operations, or
reference material that does not belong in a project plan.

## Historical References

- `Live_Mode_Implementation_Plan.md` - detailed implementation history through Phase 23
- `Phase_22_Track_Art_Image_Plan.md` - track summary image implementation
- `Phase_22b_Track_Image_Start_End_Markers_Plan.md` - image marker enhancement
- `Phase_22c_Track_Image_EXIF_GPS_Plan.md` - image GPS metadata enhancement
- `HTTPS_Wake_Lock_Plan.md` - HTTPS and Wake Lock deployment work
- `Move_to_labpi_Implementation_Plan.md` - Raspberry Pi deployment plan
- `architecture.md` - original application architecture

