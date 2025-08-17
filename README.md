# Work Time Tracker

Track work and breaks in Blender, organized by sessions. Idle time is automatically detected and excluded, so only focused work is counted. Review how long each task took at a glance.

## Features

- Start automatically
  - Timing begins as soon as you open a file and keeps updating in the background.
- Segment by task
  - Use `New Session` to switch per task for cleaner summaries later.
- Breaks by inactivity
  - Detects idle beyond a threshold and excludes it. Resumes automatically on activity.
- Always know where you are
  - Status bar shows `HH:MM | HH:MM (#ID)` (total | session | session id). Click to open details. Unsaved reminder included.
- Useful for review
  - Per‑session notes and `Export Report` to a Markdown text block.

## UI / Operations

<!-- ![Status Bar](docs/images/statusbar.png) -->
- Status Bar
  - Displays `HH:MM | HH:MM (#ID)` (total | session | session id)
  - Unsaved warning and on‑break indicator

<!-- ![Panel](docs/images/panel.png) -->
- Panel (View3D > Sidebar > Time > Time Tracker)
  - Total, current session, and time since last save
  - Session/Break lists (index, time, comment)

- Operators
  - `New Session`: Switch to a new session
  - `Export Report`: Generate a Markdown report in the Text Editor
  - `Clear Breaks`: Clear break history
  - `Reset Current Session`: Restart current session timing from zero
  - `Reset All Session`: Delete all sessions and start a new one

## Location

- Click the status bar display to open a popover panel
- 3D Viewport Sidebar: `N` → `Time` → `Time Tracker`

## Preferences

Edit → Preferences → Add-ons → Work Time Tracker

- Unsaved Warning Threshold (sec): Warn when unsaved duration exceeds this (default 600)
- Break Threshold (sec): Consider inactivity as break after this (default 300)

## Notes

- Save does not end the session; it only updates elapsed metrics
- On `Save As` (file path change), the current session ends and a new one starts
- Total time = closed sessions sum + current session elapsed (minus breaks)

## For Team Managers

This add‑on is intended for personal self‑management. Enforcing usage or using it for monitoring is out of scope.

## License

GPL-3.0
