# SSBU Mod Manager

Desktop manager for **Super Smash Bros. Ultimate** mod setups on emulator SDMC paths.

It gives you one place to manage mods, Skyline plugins, music assignments, CSS edits, conflict resolution, profiles, and emulator migration.

## Key Features

- Mod management with search, status filter, category grouping, and bulk enable/disable.
- Plugin management with required-plugin safety checks, optional plugin-name display, custom right-click plugin name/description overrides, and description visibility toggle.
- Right-click mod renaming with app-only alias support or optional on-disk folder rename.
- One-click folder import on Mods/Plugins pages with automatic path mapping:
  - Mods: unwraps common extra wrapper folders before install.
  - Plugins: imports `.nro` files and package payloads (`romfs` / `exefs` / `atmosphere/contents`) into the correct SDMC locations.
- CSS Editor for `ui_chara_db.prc` + `msg_name.msbt` workflows.
- Music page with stage playlists, preview playback, and assignment export.
- Conflict detection/resolution (XMSBT merge flow + locale MSBT fixes).
- Emulator migration tools (copy, direct export/import, upgrade flow).
- Online Compatibility checker and shareable profile support.
- Global undo/redo + save/discard toolbar state.

## Requirements

- Windows 10/11
- Python 3.11+
- Dependencies in `requirements.txt`
- Optional: `ffmpeg`/`ffplay` in `PATH` for broader audio fallback support

## Install (Dev)

```powershell
git clone https://github.com/<your-org>/ssbu-mod-manager.git
cd ssbu-mod-manager
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Build

Default build output is **onedir** for much faster app launch than onefile.

```powershell
python build.py
```

Output:

- `dist/SSBUModManager/SSBUModManager.exe`

If you explicitly need onefile packaging, build with PyInstaller manually using `--onefile`.

## First-Run Setup

1. Open **Settings**.
2. Set your emulator SDMC path (or use Auto-Detect).
3. Confirm Mods/Plugins paths are populated.
4. Go to **Mods** and **Plugins** to validate discovery.
5. Open **Conflicts** and run an initial scan.

## UX Notes

- Default visual density is tuned so current **100% zoom** matches the old 120% look.
- `Ctrl +`, `Ctrl -`, and `Ctrl 0` adjust UI zoom.
- Zoom changes are throttled for smoother repeated `Ctrl +/-` use with less jitter.
- Online Guide and Migration use higher wheel speed than standard pages.
- Mods and Plugins now share consistent wheel behavior.
- Page navigation now uses an isolated transition overlay to avoid mixed/partial page paints during fast tab switching.
- Custom plugin names/descriptions can be edited via right-click in Plugins and reset to defaults.
- Mods can be right-click renamed with a choice to keep it app-only or rename the real folder.
- Nested wrapper folders are auto-flattened on import and also surfaced as conflicts during scans.
- Conflicts page initial state and empty states are centered in-view to keep the primary action visible.
- Page switches pre-render target content before reveal to reduce mid-transition pop-in.
- Rename dialogs use a fully prepared modal show path to avoid first-frame flash.
- Windows titlebar/taskbar icon now comes from a shared multi-resolution icon asset.
- Lazy pages are background-warmed after startup to reduce first-open tab hitching.
- Main window now opens and closes without fade animations.
- Conflicts scan rendering now includes a resilient fallback so results never appear blank after a successful scan.
- Conflicts initial prompt and scan results now use isolated hosts with explicit show/hide transitions to prevent blank-result overlay races.
- Startup geometry is centered before first paint and no delayed post-show recenter is used.
- Startup now pre-renders the initial dashboard while hidden so first visible paint does not show partial widgets.
- Conflicts results viewport now runs a short multi-pass settle to prevent intermittent mid-list gaps after scan completion.
- Conflicts scan/render now rebuilds the scroll host each pass to eliminate stale scrollregion state that could cause intermittent large top gaps.
- Startup uses immediate first-page navigation (without delayed transition overlay) during hidden init to reduce first-frame skeleton/flash states.
- Conflicts scan completion now always schedules a render (independent of current-page transition state) to prevent intermittent "summary updated but rows missing" races.
- Fast scrollbar thumb dragging now forces lightweight redraw settles to reduce text smearing/tearing.
- Dashboard startup conflict scans are deferred/idle-aware to avoid early launch stutter.
- Dashboard quick stats refresh runs off the UI thread to reduce startup and tab-switch hitching.
- Primary page headers now match sidebar navigation labels exactly (no redundant "Manager/Management" suffixes).

## Repository Layout

```text
src/
  app.py                 # App bootstrap, navigation, global input/scroll/zoom
  config.py              # Persistent settings
  core/                  # Managers and domain logic
  models/                # Dataclasses and enums
  ui/
    main_window.py       # Shell layout (toolbar/content/status)
    sidebar.py           # Left navigation
    pages/               # Page implementations
    widgets/             # Reusable UI widgets
  utils/                 # Logging, audio, hashing, file helpers, etc.
main.py                  # Entrypoint + crash logging
build.py                 # PyInstaller build script
```

## Troubleshooting

- If no mods/plugins are found, re-check SDMC path in **Settings**.
- If audio preview fails on specific tracks, ensure `ffmpeg` is installed and in `PATH`.
- For startup diagnostics, set `SSBUMM_HEARTBEAT=1` before launch to enable short heartbeat logging in `crash.log`.

## License

Private/internal project unless you add a license file.
