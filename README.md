# SSBU CSS Manager

A Python GUI tool for managing the Character Select Screen (CSS) database in modded Super Smash Bros. Ultimate on Nintendo Switch.

## Features

- **1-Click Add Character** — Select a mod folder and the tool auto-detects `name_id`, `fighter_kind`, costumes, announcer voice, and display name. Adds the character to the CSS database with one click.
- **Alphabetical Ordering** — Custom characters are automatically sorted alphabetically on the CSS grid after each add.
- **Auto-Detect & Hide Unused** — Scans your mods directory and hides CSS entries for mods that aren't installed (and shows entries for mods that are).
- **Manual Editing** — Edit any PRC field directly: `ui_chara_id`, `fighter_kind`, `name_id`, `disp_order`, costume indices, announcer labels, etc.
- **Duplicate / Hide / Delete** — Manage entries with dedicated buttons.
- **Search** — Filter the character list by name.

## Requirements

- Python 3.10+
- [pyprc](https://pypi.org/project/pyprc/) — for reading/writing `.prc` param files
- [pylibms](https://pypi.org/project/pylibms/) (lms) — for reading/writing `.msbt` message files
- [customtkinter](https://pypi.org/project/customtkinter/) — dark-themed GUI framework
- **ParamLabels.csv** — Hash-to-string label mapping (~3 MB, not included in repo). Download from [param-labels](https://github.com/ultimate-research/param-labels) and place in the project root.

## Setup

```bash
# Clone the repo
git clone https://github.com/<your-username>/ssbu-css-manager.git
cd ssbu-css-manager

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Download ParamLabels.csv (place in project root alongside css_manager.py)
# https://github.com/ultimate-research/param-labels

# Run
python css_manager.py
```

## Usage

1. Launch the app: `python css_manager.py`
2. Click **Load Mod Folder** and select your CSS mod folder (e.g., `(CUSTOM REQUEST CSS)` inside your eden mods directory). This folder must contain `ui/param/database/ui_chara_db.prc` and `ui/message/msg_name.msbt`.
3. Use **1-Click Add Character from Mod** to add a new character — select the mod's folder and everything is auto-detected.
4. Use **Auto-Detect & Hide Unused** to sync the CSS with your currently installed mods.
5. Click **Save Changes** when done.

## File Structure

```
ssbu-css-manager/
├── css_manager.py      # Main application
├── ParamLabels.csv     # Hash labels (not in repo — download separately)
├── requirements.txt    # Python dependencies
├── .gitignore
└── README.md
```

## How It Works

- **PRC (`ui_chara_db.prc`)** — The character database. Each entry defines a CSS slot with fields like `ui_chara_id`, `fighter_kind`, `name_id`, `disp_order` (position on the grid), costume indices, and announcer voice labels.
- **MSBT (`msg_name.msbt`)** — The display name text file. Labels like `nam_chr1_00_{name_id}` map to the character name shown on screen.
- **Mod Detection** — The tool reads `config.json`, portrait filenames, `.xmsbt` text files, and narration sound files from each mod folder to auto-detect the correct `name_id` and other properties.

## License

MIT
