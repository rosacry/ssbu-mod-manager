# SSBU Mod Manager

Desktop manager for **Super Smash Bros. Ultimate** mod setups on emulator SDMC paths.
Current release version: **1.0.0**.

It gives you one place to manage mods, Skyline plugins, music assignments, CSS edits, conflict resolution, profiles, and emulator migration.

## Key Features

- Mod management with search, status filter, category grouping, and bulk enable/disable.
- Plugin management with required-plugin safety checks, optional plugin-name display, custom right-click plugin name/description overrides, description visibility toggle, and folder-based disable storage (`disabled_plugins`).
- Right-click mod renaming with app-only alias support or optional on-disk folder rename.
- One-click folder import on Mods/Plugins pages with automatic path mapping:
  - Mods: unwraps common extra wrapper folders before install.
  - Plugins: imports `.nro` files and package payloads (`romfs` / `exefs` / `atmosphere/contents`) into the correct SDMC locations.
- CSS Editor for `ui_chara_db.prc` + `msg_name.msbt` workflows.
- Music page with stage playlists, preview playback, and assignment export.
- Conflict detection and locale MSBT rename safety tools.
- Emulator migration tools (copy, direct export/import, upgrade flow).
- Online Compatibility checker and shareable profile support.
- Online Compatibility checker with optional strict audio/environment policy modes.
- Empirical online validation logging CLI (`scripts/online_validation_tool.py`) for emulator-pair and RTT test records.
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

Release packaging uses a single downloadable artifact: a **zip containing the executable**.

```powershell
python build.py
```

Output:

- `dist/SSBUModManager/SSBUModManager.exe`
- `dist/SSBUModManager-1.0.0-windows.zip`

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
- Zoom shortcut repeats now coalesce aggressively, with quick first-tap response and reduced repeated `Ctrl +/-` reflow churn.
- Zoom now updates in-place (no full-page "Applying zoom..." cover), so the active page remains visible while scaling.
- Zoom now coalesces post-apply key-repeat bursts and evicts hidden pages (when there are no unsaved changes) before scaling to keep `Ctrl +/-` responsive in long sessions.
- Online Guide and Migration use higher wheel speed than standard pages.
- Mods and Plugins now share consistent wheel behavior.
- Mod enable/disable toggles now update in-place immediately (including re-enable) without requiring manual Refresh.
- Plugin disable now moves binaries into a sibling `disabled_plugins` folder, and legacy `.nro.disabled` files are auto-migrated.
- Page navigation now uses a very short settle mask during tab switches to hide first-frame partial rendering on heavier pages.
- Custom plugin names/descriptions can be edited via right-click in Plugins and reset to defaults.
- Mods can be right-click renamed with a choice to keep it app-only or rename the real folder.
- Nested wrapper folders are auto-flattened on import and also surfaced as conflicts during scans.
- Conflicts page initial state and empty states are centered in-view to keep the primary action visible.
- Page switches pre-render target content before reveal to reduce mid-transition pop-in.
- Rename dialogs use a fully prepared modal show path to avoid first-frame flash.
- Windows titlebar/taskbar icon now comes from a shared multi-resolution icon asset.
- Startup now keeps non-active pages lazy (no hidden prewarm pass) to reduce launch and zoom reflow pressure.
- Main window now opens and closes without fade animations.
- Conflicts scan rendering now includes a resilient fallback so results never appear blank after a successful scan.
- Conflicts initial prompt and scan results now use isolated hosts with explicit show/hide transitions to prevent blank-result overlay races.
- Startup geometry is centered before first paint and no delayed post-show recenter is used.
- Startup now pre-renders the initial dashboard while hidden so first visible paint does not show partial widgets.
- Windows startup now disables CustomTkinter header withdraw/deiconify manipulation for the root window to prevent top-left first-frame flash/recenter.
- Conflicts results viewport now runs a short multi-pass settle to prevent intermittent mid-list gaps after scan completion.
- Conflicts scan/render now uses a single deterministic scroll host with stale-host pruning to prevent duplicate scrollbars, blank scan overlays, and intermittent large top gaps.
- Conflicts action buttons row is now only shown when actions exist, preventing the large blank gap before results when all detected conflicts are already resolved/non-mergeable.
- Conflicts post-scan top-anchor guard is now a short fixed stabilization window to block delayed wheel drift without relying on intent heuristics.
- Conflicts post-scan top-anchor guard now holds until first explicit scroll/scrollbar interaction (after a short minimum hold) to prevent delayed drift without trapping intentional scrolling.
- Conflicts rendering now logs compact child-geometry snapshots in developer mode to diagnose rare invisible-gap states.
- Startup uses immediate first-page navigation (without delayed transition overlay) during hidden init to reduce first-frame skeleton/flash states.
- Conflicts scan completion now always schedules a render (independent of current-page transition state) to prevent intermittent "summary updated but rows missing" races.
- Fast scrollbar thumb dragging now uses a paced redraw loop with periodic full repaints to prevent missing/half-rendered text while dragging rapidly.
- Global wheel scrolling now excludes decorative canvases, uses sticky same-page fallback targets, and uses pointer-aware page fallback routing to prevent intermittent "scroll stops until cursor moves" behavior across pages.
- Global wheel scrolling now also keeps a per-page cached target and retries a fresh active-page target if a stale/non-scrollable widget is selected mid-scroll.
- Conflicts page includes a direct header-level `Fix Text Conflicts` action for locale MSBT rename safety checks.
- Conflicts summary now distinguishes pending auto-fix vs already merged counts to reduce ambiguity about what is still actionable.
- Conflicts merge status text now clearly shows `Already merged`/`Already resolved` for fixed items and keeps pending items separate.
- Conflicts stabilization guard now yields immediately to explicit user wheel/scrollbar input to prevent scroll trapping after scans.
- Scrollbar drag handling now accepts raw Tk callback argument variants under heavy drag load, preventing `_clicked_preserve_offset` event errors.
- Full-page view containers now force square corners to prevent rare white corner-dot artifacts on some systems.
- Music auto-scan is now deferred slightly on page show and cooperative-cancelled when leaving the Music tab, preventing heavy background track scans from stalling other pages.
- Dashboard startup conflict scans are deferred/idle-aware to avoid early launch stutter.
- Dashboard quick stats refresh runs off the UI thread to reduce startup and tab-switch hitching.
- App status-bar mod/plugin counts now refresh off the UI thread to reduce startup hitching and early frame drops.
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

## Empirical Validation CLI

Use the built-in logger to record real online test outcomes and regenerate markdown reports:

```powershell
python scripts/online_validation_tool.py seed-defaults
python scripts/online_validation_tool.py next
python scripts/online_validation_tool.py add-matrix --pair-a Eden --pair-b Ryujinx --result FAIL --notes "join failed"
python scripts/online_validation_tool.py add-rtt --mode Public --runs 5 --avg-rtt-ms 42.5 --notes "stable"
python scripts/online_validation_tool.py render
python scripts/online_validation_tool.py status
```

Generated artifacts:
- `docs/online_validation_data.json`
- `docs/emulator_pair_matrix_results.md`
- `docs/public_unlisted_rtt_results.md`
- `docs/online_evidence_lock.md`

The generated matrix/RTT markdown files now include aggregate coverage summaries to show which evidence is still pending.

## License

Private/internal project unless you add a license file.
