# SSBU Mod Manager

A full-featured desktop application for managing Super Smash Bros. Ultimate mods on Nintendo Switch emulators. Built with Python and customtkinter.

![SSBU Mod Manager](assets/logo.png)

## Features

### Mod Management
- **Enable/Disable Mods** — Toggle mods on and off with a single click (rename or move method)
- **Enable/Disable All** — Bulk-toggle all mods with confirmation dialogs
- **Category Detection** — Mods are automatically categorized by content type (Character, Audio, Stage, UI, Effect, etc.)
- **Grouping & Filtering** — Group mods by category, filter by status, and search by name
- **Fix Nested Folders** — Auto-detect and flatten unnecessarily nested mod subfolders
- **Undo/Redo** — All mod actions support undo (Ctrl+Z) and redo (Ctrl+Y)

### CSS Editor
- **1-Click Add Character** — Auto-detects `name_id`, `fighter_kind`, costumes, announcer voice, and display name from mod folders
- **Generate Custom CSS Template** — Automatically build a CSS mod containing only characters with installed mods
- **Alphabetical Ordering** — Custom characters are sorted alphabetically on the CSS grid
- **Auto-Detect & Hide Unused** — Syncs CSS entries with currently installed mods
- **Manual Editing** — Edit any PRC field directly: `ui_chara_id`, `fighter_kind`, `name_id`, `disp_order`, costume indices, announcer labels

### Plugin Management
- **Enable/Disable Plugins** — Manage ARCropolis, HDR, and other Skyline plugins
- **Enable/Disable All** — Bulk-toggle with automatic protection for required plugins (e.g., ARCropolis)
- **Known Plugin Info** — Displays descriptions and links for recognized plugins

### Music Management
- **3-Column Layout** — Stages on the left, playlist in the middle, available tracks on the right
- **Audio Preview** — Play WAV, OGG, MP3, NUS3AUDIO (LOPUS, OPUS, IDSP, BWAV), and FLAC tracks directly in the app
- **Volume Control** — Adjustable volume slider for playback
- **Stage Playlists** — Assign tracks to specific stages with drag-to-reorder
- **Competitive Stages Filter** — Filter stage list to show only tournament-legal stages (Battlefield, Small Battlefield, Final Destination, Smashville, Town and City, Pokemon Stadium 2, Kalos Pokemon League, Hollow Bastion, Northern Cave, Yoshi's Story)
- **Bulk Operations** — Assign all tracks to all stages, clear all assignments
- **Save & Apply** — Generates PRC configuration for in-game music

### Conflict Detection & Resolution
- **Automatic Scanning** — Detects when multiple mods modify the same game file
- **Type-Based Grouping** — Conflicts grouped by file type (XMSBT, MSBT, PRC, STPRM, STDAT) with explanations
- **Auto-Merge** — XMSBT text conflicts are merged using a union strategy (all labels from all mods combined); overlapping labels use last-mod-wins
- **Original File Management** — After merging, original XMSBT files are moved to `_MergedResources/.originals/` to prevent ARCropolis from double-loading both the originals and merged file
- **Restore Originals** — One-click undo of all merges: restores original files to their mod folders and cleans up `_MergedResources`
- **Backup Before Merge** — Configurable automatic backup creation before any merge or resolution operation
- **Manual Resolution** — Choose which mod's version to keep for non-mergeable conflicts

### Profile Sharing
- **Export/Import** — Share your mod setup as a portable profile code
- **Profile Codes** — Compact base64-encoded strings representing your mod configuration

### Additional Features
- **Multi-Emulator Support** — Works with Eden, Ryujinx, Yuzu, Suyu, Sudachi, Citron, and others
- **Auto-Detection** — Automatically finds your emulator's SDMC path on startup
- **Developer Mode** — Built-in debug logging with search, auto-scroll, and clipboard support
- **Zoom / Scaling** — Ctrl+Plus and Ctrl+Minus to zoom the entire UI in/out (60%–200%), Ctrl+0 to reset; persisted across sessions
- **Resizable Panels** — Drag the splitter handles between columns on the Music and CSS Editor pages to resize panes
- **Smooth UI** — Resize debouncing, proper cleanup, and consistent dark theme

## Screenshots

The application features a modern dark theme with sidebar navigation:

- **Dashboard** — Overview stats, quick actions, and conflict status
- **Mods** — Category-grouped mod list with toggle switches
- **Music** — 3-column resizable layout for stage music assignment
- **Conflicts** — Type-grouped conflict display with explanations
- **Settings** — Emulator path configuration and preferences

## Requirements

- Python 3.10+
- Windows (primary platform)

### Python Dependencies

| Package | Purpose |
|---------|---------|
| [customtkinter](https://pypi.org/project/customtkinter/) | Dark-themed GUI framework |
| [pyprc](https://pypi.org/project/pyprc/) | Reading/writing `.prc` param files |
| [pylibms](https://pypi.org/project/pylibms/) | Reading/writing `.msbt` message files |
| [Pillow](https://pypi.org/project/Pillow/) | Image processing for icons |
| [pygame](https://pypi.org/project/pygame/) | Audio playback for music preview |

### Additional Files

- **ParamLabels.csv** — Hash-to-string label mapping (~3 MB, not included in repo). Download from [param-labels](https://github.com/ultimate-research/param-labels) and place in the project root.

## Installation

### From Source

```bash
# Clone the repo
git clone https://github.com/your-username/ssbu-mod-manager.git
cd ssbu-mod-manager

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Download ParamLabels.csv (place in project root)
# https://github.com/ultimate-research/param-labels

# Run
python main.py
```

### Standalone Executable

Download `SSBUModManager.exe` from the [Releases](../../releases) page. No Python installation required.

## Building the Executable

```bash
# Install dependencies (includes PyInstaller)
pip install -r requirements.txt

# Build
python build.py
```

The executable will be in the `dist/` folder.

## Usage

1. **First Launch** — Go to Settings and configure your emulator's SDMC path, or let the app auto-detect it
2. **Manage Mods** — Navigate to the Mods page to enable/disable mods with toggle switches
3. **Edit CSS** — Use the CSS Editor to add custom characters to the character select screen
4. **Manage Music** — Assign custom music tracks to stages in the Music page
5. **Check Conflicts** — Visit the Conflicts page to detect and resolve file conflicts between mods
6. **Share Setup** — Export your mod configuration as a profile code on the Profiles page

## Project Structure

```
ssbu-mod-manager/
├── main.py                         # Entry point
├── build.py                        # PyInstaller build script
├── requirements.txt                # Python dependencies
├── ParamLabels.csv                 # Hash labels (download separately)
├── assets/
│   ├── icon.ico                    # Application icon
│   └── logo.png                    # Logo image
├── src/
│   ├── app.py                      # Main application class
│   ├── config.py                   # Settings persistence
│   ├── constants.py                # Game constants (stages, fighters)
│   ├── paths.py                    # Emulator path detection
│   ├── core/
│   │   ├── conflict_detector.py    # File conflict detection
│   │   ├── conflict_resolver.py    # Conflict resolution & merging
│   │   ├── css_manager.py          # CSS database management
│   │   ├── file_scanner.py         # Mod file scanning
│   │   ├── mod_manager.py          # Mod enable/disable logic
│   │   ├── msbt_handler.py         # MSBT message file handling
│   │   ├── music_manager.py        # Music track & playlist management
│   │   ├── plugin_manager.py       # Plugin management
│   │   ├── prc_handler.py          # PRC param file handling
│   │   └── share_code.py           # Profile export/import
│   ├── models/
│   │   ├── character.py            # Character data model
│   │   ├── conflict.py             # Conflict & resolution models
│   │   ├── mod.py                  # Mod data model
│   │   ├── music.py                # Music track model
│   │   ├── plugin.py               # Plugin data model
│   │   ├── profile.py              # Profile data model
│   │   └── settings.py             # App settings model
│   ├── ui/
│   │   ├── base_page.py            # Base class for all pages
│   │   ├── main_window.py          # Main window with toolbar
│   │   ├── sidebar.py              # Navigation sidebar
│   │   ├── pages/
│   │   │   ├── conflicts_page.py   # Conflict detection & resolution
│   │   │   ├── css_page.py         # CSS editor page
│   │   │   ├── dashboard_page.py   # Dashboard overview
│   │   │   ├── developer_page.py   # Developer debug log
│   │   │   ├── mods_page.py        # Mod management page
│   │   │   ├── music_page.py       # Music management page
│   │   │   ├── plugins_page.py     # Plugin management page
│   │   │   ├── settings_page.py    # Settings configuration
│   │   │   └── share_page.py       # Profile sharing page
│   │   └── widgets/
│   │       ├── conflict_card.py    # Conflict display card
│   │       ├── mod_card.py         # Mod display card
│   │       ├── music_track_row.py  # Music track row widget
│   │       ├── plugin_row.py       # Plugin display row
│   │       ├── search_bar.py       # Search input widget
│   │       ├── status_bar.py       # Bottom status bar
│   │       └── toggle_switch.py    # Toggle switch widget
│   └── utils/
│       ├── action_history.py       # Undo/redo system
│       ├── audio_player.py         # Audio playback (pygame)
│       ├── file_utils.py           # File operation utilities
│       ├── hashing.py              # PRC hash resolution
│       ├── logger.py               # In-memory debug logger
│       ├── nus3audio.py            # NUS3AUDIO container parser (LOPUS/OPUS/IDSP/BWAV)
│       ├── resource_path.py        # PyInstaller resource paths
│       └── xmsbt_parser.py         # XMSBT text file parser
└── tests/                          # Test files
```

## How It Works

- **PRC (`ui_chara_db.prc`)** — The character database. Each entry defines a CSS slot with fields like `ui_chara_id`, `fighter_kind`, `name_id`, `disp_order`, costume indices, and announcer voice labels.
- **MSBT (`msg_name.msbt`)** — The display name text file. Labels like `nam_chr1_00_{name_id}` map to character names shown on screen.
- **XMSBT (`.xmsbt`)** — Text override files used by mods. When multiple mods have XMSBT files for the same path, they can be merged automatically.
- **Mod Detection** — The tool reads `config.json`, portrait filenames, `.xmsbt` text files, and narration sound files from each mod folder to auto-detect properties.
- **Conflict Detection** — Scans all enabled mods for files at the same relative path. Groups conflicts by type and offers resolution strategies.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+Z | Undo last action |
| Ctrl+Y | Redo last undone action |
| Ctrl+Plus | Zoom in (increase UI scale by 10%) |
| Ctrl+Minus | Zoom out (decrease UI scale by 10%) |
| Ctrl+0 | Reset zoom to 100% |

## License

MIT
