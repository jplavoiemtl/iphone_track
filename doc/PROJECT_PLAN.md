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

### 3. Live Tracking Health

Make connection state explicit by showing the age of the latest GPS fix,
whether points arrived late or in a batch, and a clear warning when the phone
has stopped reporting.

### 4. Export and Privacy Controls

Add GPX, GeoJSON, or CSV export and an option to hide the beginning and end of
a route near sensitive locations such as home.

## Completed Milestones

- 2026-02: Converted the original tracker into a Flask web application
- 2026-02: Added Live Mode, session persistence, history, and activity layers
- 2026-02: Added push notifications and live-mode resilience improvements
- 2026-03: Added synchronized polling, visual poll status, and slider navigation
- 2026-03: Added track-art images, start/end markers, and EXIF GPS metadata
- 2026-03: Added HTTPS wake lock support and gevent-based deployment
- 2026-03: Made Live Mode the default and improved mobile startup behavior

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

