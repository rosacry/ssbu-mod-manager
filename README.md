# SSBU Mod Manager

Desktop manager for **Super Smash Bros. Ultimate** mod setups on emulator SDMC paths.
Current release version: **1.1.0**.

One place to manage mods, Skyline plugins, music assignments, CSS edits, conflict resolution, profiles, and emulator migration.

## Download

Grab the latest zip from the [Releases](https://github.com/rosacry/ssbu-mod-manager/releases) page, extract it, and run `SSBUModManager.exe`.

## What's New in 1.1.0

### Multi-Monitor DPI Scaling
- Seamless Per-Monitor V2 DPI awareness — no more glitches when dragging between 1440p and 4K monitors.
- Eliminated the alpha-flash/flicker during DPI transitions.
- Proactive DPI change detection during window drag for smoother scaling.

### Disabled-Mods Track Browsing
- The Music page now scans the `disabled_mods` folder automatically so you can browse, favorite, and assign tracks from disabled mods without re-enabling them.
- Disabled tracks are clearly labeled "(disabled)" in the track list.

### Music Playback Fixes
- Fixed a bug where saved music assignments were silently dropped if the source mod was in `disabled_mods`, causing all stage/menu music to stop.
- Added warning logging when saved assignments reference missing tracks.

### Thread Safety & Stability
- Audio player is now fully thread-safe — all public methods guarded by a reentrant lock, eliminating race conditions during concurrent play/stop/seek from background threads.
- Configuration manager is now thread-safe with a lock on load/save/update operations.
- Mixer initialization protected against double-init from concurrent threads.
- All music preference and assignment saves (library, replacements, assignments) now use atomic writes (temp-file + rename) to prevent corruption on crash or power loss.

### UI Reliability
- Fixed spinner animation not being cancelled on stale scan generations, preventing ghost spinners.
- Spinner `after` IDs are now tracked and properly cancelled on page hide.
- Playback polling and seek-bar timers are now cancelled when navigating away from the Music page.
- `ffplay` stderr is now captured and logged for debugging instead of being silently discarded.
- Config parse errors are now logged with a warning instead of silently resetting to defaults.

## Features

### Mods
- Search, status filter, category grouping, and bulk enable/disable.
- One-click folder import from extracted mod folders or archives (`.zip` / `.7z` / `.rar`).
- Smart skin-slot detection: auto-shifts skins into open default slots, resolves overlaps, and distinguishes skin slots from voice/effect-only packs.
- Multi-slot skin packs can be split during import with a picker for individual slot variants.
- Support-pack retargeting: move voice, effect, or camera packs to other costume slots via right-click.
- Import repair: normalizes `config.txt` to `config.json`, synthesizes missing manifests, prunes stale entries, quarantines incomplete model packs.
- BNTX portrait patching: fixes mismatched internal texture names from reslotting.
- `Wi-Fi Safe` mode: one-click enable of only client-side-safe mods.
- `Repair Installed`: audits all mod folders, fixes safe issues in-place, reports remaining conflicts.
- `Repair Runtime`: resets Yuzu runtime state (renderer profile, shader cache, ARCropolis cache).
- Right-click renaming with app-only alias or on-disk folder rename.

### Plugins
- Skyline `.nro` plugin management with required-plugin safety checks.
- Custom plugin name/description overrides via right-click.
- `Stable Mode`: disables non-essential plugins while keeping core and safe cosmetic helpers active.
- Folder-based disable storage (`disabled_plugins`).

### CSS Editor
- Edit `ui_chara_db.prc` and `msg_name.msbt` to customize the Character Select Screen.

### Music
- PRC-backed stage slot discovery with a safe Main Menu replacement slot.
- Wi-Fi-safer existing-slot replacement overlays.
- Standalone library player with queue, favorites, and preview playback.
- `.nus3audio` Opus stream playback via `ffplay` when available.
- Legacy stage-playlist editing.
- Experimental Spotify playlist export (opt-in via Settings).

### Conflicts
- Scan for XMSBT, MSBT, PRC, and stage-data conflicts.
- Filter and group by type or by fighter/form/slot.
- Friendly slot and form names in conflict cards.
- Locale MSBT rename safety tools.

### Online Compatibility
- Check mod setups for online desync risk.
- Shareable profile codes for comparing setups.
- Optional strict audio/environment policy modes.

### Migration
- Copy, export/import, and upgrade flows between emulator SDMC paths.

### General
- Global undo/redo with save/discard toolbar.
- `Ctrl +` / `Ctrl -` / `Ctrl 0` zoom controls.
- Dashboard with quick stats and conflict overview.

## Requirements

- Windows 10/11
- Optional: `ffmpeg` / `ffplay` in `PATH` for audio preview support

## Install (Dev)

```powershell
git clone https://github.com/rosacry/ssbu-mod-manager.git
cd ssbu-mod-manager
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Requires Python 3.11+.

## Build

```powershell
python build.py
```

Output: `dist/SSBUModManager-1.1.0-windows.zip`

## First-Run Setup

1. Open **Settings** and set your emulator SDMC path (or use Auto-Detect).
2. Confirm Mods/Plugins paths are populated.
3. Go to **Mods** and **Plugins** to validate discovery.
4. Open **Conflicts** and run an initial scan.

## Repository Layout

```text
src/
  app.py                 # App bootstrap, navigation, global input/scroll/zoom
  config.py              # Persistent settings
  core/                  # Domain logic and managers
  models/                # Dataclasses and enums
  ui/
    theme.py             # Centralized colors, fonts, spacing, timing
    main_window.py       # Shell layout (toolbar/content/status)
    sidebar.py           # Left navigation
    pages/               # Page implementations
    widgets/             # Reusable UI widgets
  utils/                 # Logging, audio, hashing, file helpers
main.py                  # Entrypoint + crash logging
build.py                 # PyInstaller build script
```

## Troubleshooting

- **No mods/plugins found**: Re-check SDMC path in Settings.
- **Music page shows no safe slots**: Point the app at a mod containing `ui_stage_db.prc` and `ui_bgm_db.prc`.
- **Audio preview fails**: Ensure `ffmpeg` is installed and in `PATH`.
- **Startup diagnostics**: Set `SSBUMM_HEARTBEAT=1` before launch to enable heartbeat logging in `crash.log`.
