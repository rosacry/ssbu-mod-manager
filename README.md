# SSBU Mod Manager

Desktop manager for **Super Smash Bros. Ultimate** mod setups on emulator SDMC paths.
Current release version: **1.0.3**.

One place to manage mods, Skyline plugins, music assignments, CSS edits, conflict resolution, profiles, and emulator migration.

## Download

Grab the latest zip from the [Releases](https://github.com/rosacry/ssbu-mod-manager/releases) page, extract it, and run `SSBUModManager.exe`.

## What's New in 1.0.3

- Fixed menu song replacement: Wi-Fi-safe replacements for the main menu slot now persist correctly instead of being silently deleted during save.
- Replacement save now validates source files exist before copying and reports failures in the save dialog instead of silently skipping.
- Removed redundant Favorites button from queue controls (the "Favorites only" checkbox already provides this).
- Single-click on a track now only selects it; double-click plays the track.
- Spotify export button is now hidden entirely when the feature is disabled in Settings.

## What's New in 1.0.2

- Removed the unintuitive "Play All" button from the music player queue controls.
- Fixed text truncation on Wi-Fi Safe and Legacy tabs, summary labels, and other panel elements throughout the app.
- Volume slider now uses an exponential perception curve so mid-range values feel naturally quieter.
- IDSP and BWAV audio decoding now tries ffmpeg first, reducing preview load time from ~10 seconds to under 1 second.
- Optimised the pure-Python DSP ADPCM fallback decoder with local-variable hoisting and bytearray indexing.
- Page loading improved: migration page added to background warmup queue, batch render sizes doubled, widget teardown optimised.
- Fixed critical bug where a missing replacement source file could abort the entire music save and corrupt the manifest.
- Replacement manifest and metadata writes now use atomic temp-file-then-rename to prevent corruption on crash.
- Fixed thread-safety issue in audio player `toggle_pause()`.
- `flatten_mod()` now logs a warning when files are skipped due to name conflicts.
- ffplay stderr pipe changed to DEVNULL to prevent file-descriptor leaks across many play cycles.

## What's New in 1.0.1

- Music Wi-Fi safety now distinguishes vanilla-slot replacements from unsafe added-track / tracklist-extension mods.
- Online compatibility codes now include unsafe added-track music edits by default, with strict audio reserved for full replacement-audio parity.
- Music page messaging now warns before saving Wi-Fi-unsafe legacy playlist edits.
- Migration, Mods, and Plugins pages stay more responsive during heavy scans and large list renders.
- Audio preview decoding received IDSP / DSP ADPCM handling improvements and cache rev updates.

## Features

### Mods
- Search, status filter, category grouping, and bulk enable/disable.
- One-click folder import from extracted mod folders or archives (`.zip` / `.7z` / `.rar`).
- Smart skin-slot detection: auto-shifts skins into open default slots, resolves overlaps, and distinguishes skin slots from voice/effect-only packs.
- Multi-slot skin packs can be split during import with a picker for individual slot variants.
- Support-pack retargeting: move voice, effect, or camera packs to other costume slots via right-click.
- Import repair: normalizes `config.txt` to `config.json`, synthesizes missing manifests, prunes stale entries, quarantines incomplete model packs.
- BNTX portrait patching: fixes mismatched internal texture names from reslotting.
- `Wi-Fi Safe` mode: one-click enable of only client-side-safe mods, excluding unsafe music tracklist/database edits.
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
- PRC-backed stage slot discovery using the real SSBU stage playlist structure, with a Wi-Fi-safe Main Menu replacement slot.
- Wi-Fi-safe existing-slot replacement overlays for vanilla/discovered BGM slots.
- Standalone library player with queue, favorites, and preview playback.
- `.nus3audio` Opus stream playback via `ffplay` when available.
- Legacy stage-playlist editing for local or fully matched setups only; additive tracklists are not Wi-Fi-safe.
- Experimental Spotify playlist export (opt-in via Settings).

### Conflicts
- Scan for XMSBT, MSBT, PRC, and stage-data conflicts.
- Filter and group by type or by fighter/form/slot.
- Friendly slot and form names in conflict cards.
- Locale MSBT rename safety tools.

### Online Compatibility
- Check mod setups for online desync risk, including unsafe added-track music edits by default.
- Shareable profile codes for comparing setups.
- Optional strict audio/environment policy modes for tournament parity of replacement audio/BGM.

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

Output: `dist/SSBUModManager-1.0.2-windows.zip`

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
- **Music page shows no safe slots**: Rescan after adding or enabling a mod containing both `ui_stage_db.prc` and `ui_bgm_db.prc`. The app now also checks `disabled_mods`.
- **Legacy playlist edits and online play**: Adding extra songs or extending a stage tracklist is not Wi-Fi-safe. Use the Music page's slot-replacement workflow if you want one-sided custom music online.
- **Audio preview fails**: Ensure `ffmpeg` is installed and in `PATH`.
- **Startup diagnostics**: Set `SSBUMM_HEARTBEAT=1` before launch to enable heartbeat logging in `crash.log`.
