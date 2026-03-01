# SSBU Mod Manager

Desktop manager for **Super Smash Bros. Ultimate** mod setups on emulator SDMC paths.
Current release version: **1.4.13**.

It gives you one place to manage mods, Skyline plugins, music assignments, CSS edits, conflict resolution, profiles, and emulator migration.

## Key Features

- Mod management with search, status filter, category grouping, and bulk enable/disable.
- Plugin management with required-plugin safety checks, optional plugin-name display, custom right-click plugin name/description overrides, description visibility toggle, and folder-based disable storage (`disabled_plugins`).
- Right-click mod renaming with app-only alias support or optional on-disk folder rename.
- One-click folder import on Mods/Plugins pages with automatic path mapping:
  - Mods: imports extracted mod folders or folders full of `.zip` / `.7z` / `.rar` downloads, unwraps common extra wrapper folders, auto-selects a single base/default skin from multi-variant packs, and skips/report unsupported complex multi-fighter packs.
  - Mods: detects actual skin-slot overlaps during import, can replace or auto-shift skins into open default slots, and no longer treats voice-only or effect-only slot packs as if they occupied the character's skin slot.
  - Mods: auto-prunes exact slot-scoped support-file conflicts from older support-only packs when a more specific imported skin/voice/effect override should win, and stores removed files under `_import_backups`.
  - Mods: right-click support-pack controls let you retarget slot-scoped voice, effect, or camera packs to another costume slot or duplicate them across the entire fighter without touching the visual skin files.
  - Mods: support-pack retarget dialogs now show friendly form names from pack metadata when available, and target slots also surface detected installed skin occupants or open default slots to make voice/effect/camera reassignment easier.
  - Mods: one-click `Wi-Fi Safe` mode enables only mods classified as safe client-side content and disables the rest.
  - Mods: multi-slot skin packs can now be split during import, with a picker that lets you import the recommended base skin, select individual slot variants, or bring in every form separately, and it shows friendly form names from `msg_name` / `ui_chara_db` metadata when the pack provides them.
  - Mods: skin-slot conflict prompts and overlap warnings now use friendly form names when metadata is available, and they call out which installed skin currently owns the slot plus which default slots remain open.
  - Mods: auto-pruned support-file and disabled-mod reporting now includes friendly form names plus the `_import_backups/...` or `disabled_mods/...` destination, and support-only metadata leftovers no longer keep an otherwise-pruned support pack enabled.
  - Mods: import repair now normalizes legacy `config.txt` manifests to `config.json`, rebuilds reslotted slot-effect configs from the original source pack when available, synthesizes missing generic fighter-effect manifests for Cloud-style skins, and trims stale config entries that point at files not actually present in the installed mod.
  - Mods: import now runs a postflight installed-content repair pass for the imported mods, so broken manifests, safe broad-support overlaps, and byte-identical exact file collisions are corrected immediately instead of being left for Yuzu/ARCropolis to discover.
  - Mods: repair/import postflight fills only the required `ui/replace[_patch]/chara/chara_0..4` portrait assets from the closest available portrait size in the same skin, and no longer fabricates advanced `chara_5..7` portrait files from mismatched BNTX sizes.
  - Mods: imports and installed repairs now invalidate ARCropolis `mod_cache` and stale `conflicts.json` automatically after content changes so new file layouts are not masked by cached loader state.
  - Mods: the new `Repair Installed` action on the Mods page audits enabled and disabled mod folders, fixes safe structural/config problems in place, prunes safe overlap cases with backups, and reports only the exact remaining conflicts that still require manual review.
  - Conflicts: scan results now surface friendly slot/form names inside conflict cards and fallback rows, and conflicting mod lists call out which form/slot each mod is touching instead of only showing raw file paths.
  - Conflicts: the Conflicts page now has a compact filter box plus a `By Type` / `By Fighter/Form/Slot` view switch, so large multi-form character setups can be reviewed by costume slot instead of only by file extension.
  - Plugins: imports `.nro` files and package payloads (`romfs` / `exefs` / `atmosphere/contents`) into the correct SDMC locations.
  - Plugins: one-click `Stable Mode` disables all non-required Skyline plugins so cosmetic-only setups can fall back to a minimal runtime when optional helpers or gameplay frameworks destabilize loading.
- CSS Editor for `ui_chara_db.prc` + `msg_name.msbt` workflows.
- Music page with PRC-backed stage slot discovery, a built-in safe Main Menu replacement slot, Wi-Fi-safer existing-slot replacement overlays, a standalone library player queue, legacy stage-playlist editing, favorites list/filtering, preview playback, and an explicit `.nus3audio`-only track list.
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
- Optional: Spotify account + Spotify app client ID if you want to enable the experimental playlist export from the Music page

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
- `dist/SSBUModManager-1.4.13-windows.zip`

If you explicitly need onefile packaging, build with PyInstaller manually using `--onefile`.

## First-Run Setup

1. Open **Settings**.
2. Set your emulator SDMC path (or use Auto-Detect).
3. Confirm Mods/Plugins paths are populated.
4. Go to **Mods** and **Plugins** to validate discovery.
5. Open **Conflicts** and run an initial scan.
6. Optional: if you want experimental Music -> Spotify export, enable it in **Settings -> Experimental**, then create a Spotify app client ID and register the loopback redirect URI `http://127.0.0.1/callback`.

## UX Notes

- Default visual density is tuned so current **100% zoom** matches the old 120% look.
- `Ctrl +`, `Ctrl -`, and `Ctrl 0` adjust UI zoom.
- Zoom shortcut repeats now coalesce aggressively, with quick first-tap response and reduced repeated `Ctrl +/-` reflow churn.
- Zoom now updates in-place (no full-page "Applying zoom..." cover), so the active page remains visible while scaling.
- Zoom now coalesces post-apply key-repeat bursts and evicts hidden pages (when there are no unsaved changes) before scaling to keep `Ctrl +/-` responsive in long sessions.
- Online Guide and Migration use higher wheel speed than standard pages.
- Mods and Plugins now share consistent wheel behavior.
- Mod enable/disable toggles now update in-place immediately (including re-enable) without requiring manual Refresh.
- Mod/plugin enable and disable actions now stop early with a clear "close the game or emulator first" error when files are in use by a running emulator.
- Mods import now understands archive download folders, picks one base skin from multi-slot/variant packs, auto-reassigns incoming skins into open default slots when possible, keeps slot-specific voice files aligned when a skin is re-slotted, and reports anything that could not be placed cleanly.
- Multi-slot visual packs now stop for a selection dialog during import, so you can choose specific slot variants instead of being forced into a single auto-picked skin, and metadata-backed form names like `Nazo` or `Hyper Perfect Nazo` are shown when available.
- Mods import now distinguishes skin slots from slot-scoped support packs, so voice/effect-only Sonic-style packs can coexist with a skin on the same costume slot, and re-importing the same mod folder replaces it in place without a false self-conflict.
- Mods import now auto-prunes exact support-file overlaps out of older support-only packs when a more specific imported override needs those paths, and reslotted imports with a slot token in the folder name are renamed to match their final slot.
- Mods import now repairs broken mod manifests during install: legacy `config.txt` files are normalized to `config.json`, generic fighter-effect skins that ship without a manifest get one synthesized automatically, split/reslotted effect configs are rebuilt from the source pack, and stale config references to missing files are dropped before the mod is left active.
- Mods import now runs a postflight repair pass for imported mods, so safe exact overlap cases and malformed installed manifests are corrected immediately instead of being left behind as latent startup/stage-load failures.
- Mods import and installed-mod repair now also fill missing required portrait sizes (`chara_0..4`) from the closest available portrait asset in the same skin, reducing CSS/versus/battle-load failures from incomplete UI skin packs.
- Skin-slot conflict prompts and overlap warnings now show metadata-backed form names where packs provide them, list the installed skin occupying the requested slot, and surface open default slots directly in the replace/move decision flow.
- Auto-pruned support-pack warnings now call out the affected form names and backup folder path, and support-only packs that are reduced to metadata leftovers are moved into `disabled_mods` instead of staying falsely active.
- Conflicts page scan results now show metadata-backed slot/form labels inside the conflict cards, fallback rows, and merge dialogs, and the dashboard's quick text-conflict preview uses the same friendly conflict descriptions.
- Conflicts page now includes a compact text filter plus a `By Fighter/Form/Slot` grouping mode, so costume-heavy setups can be reviewed by slot/form without losing the existing file-type view.
- Plugin disable now moves binaries into a sibling `disabled_plugins` folder, and legacy `.nro.disabled` files are auto-migrated.
- Page navigation now uses a very short settle mask during tab switches to hide first-frame partial rendering on heavier pages.
- Custom plugin names/descriptions can be edited via right-click in Plugins and reset to defaults.
- Mods can be right-click renamed with a choice to keep it app-only or rename the real folder.
- Mods with slot-scoped voice, effect, or camera files can be right-click configured so those support packs stay on one slot, move to another slot, or become fighter-wide.
- Support-pack configuration dialogs now show metadata-backed form names where packs provide them, and target-slot pickers call out detected installed skin names plus `Open default slot` entries for empty costume slots.
- The `Wi-Fi Safe` button on the Mods page enables only mods classified as `SAFE` and disables anything that still requires a shared setup.
- The `Repair Installed` button on the Mods page audits installed mods in-place, auto-fixes safe manifest/overlap issues, stores removed files under `_import_backups`, and reports only the remaining exact overlaps that differ and still need manual review.
- `Repair Installed` also backfills missing required CSS/versus/battle portrait sizes for character skins when the pack shipped only a partial `chara_0..4` set.
- Online-risk classification now recognizes common costume-support assets such as slot-scoped fighter motion/update files and visual-only stage render/motion assets as client-side safe instead of flagging them as desync-prone by default.
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
- Music now separates safer existing-slot replacement overlays from legacy stage-playlist injection, surfaces discovered stage slots from `ui_stage_db.prc`/`ui_bgm_db.prc` when available, always includes a built-in safe Main Menu replacement slot, shows default-to-custom mappings directly in the UI (`x -> y`), and adds a standalone filtered/favorites queue player for in-app listening.
- Spotify playlist export is now explicitly gated behind **Settings -> Experimental** so the Music page can treat it as opt-in functionality.
- `.nus3audio` preview now prefers direct cached Opus stream playback through `ffplay` when available, which reduces unnecessary preview transcoding and preserves higher-fidelity audio in the Music tab.
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
- If the Music page shows no discovered safe slots, install or point the app at a mod containing both `ui_stage_db.prc` and `ui_bgm_db.prc`.
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
