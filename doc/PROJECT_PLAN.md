# iPhone Tracker Project Plan

**Status:** Canonical planning document  
**Last updated:** 2026-07-11

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

