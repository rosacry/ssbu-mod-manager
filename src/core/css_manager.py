"""CSS (Character Select Screen) management - extracted from original css_manager.py."""
import os
import re
import json
import glob
from pathlib import Path
from typing import Optional, Any
from src.core.prc_handler import PRCHandler
from src.core.msbt_handler import MSBTHandler


class CSSManager:
    def __init__(self, prc_handler: PRCHandler, msbt_handler: MSBTHandler):
        self.prc_handler = prc_handler
        self.msbt_handler = msbt_handler
        self.prc_root = None
        self.db_root = None
        self.msbt_file = None
        self.prc_path = ""
        self.msbt_path = ""
        self.characters = []
        self.mod_folder = ""

    def load(self, mod_folder: str) -> list[dict]:
        """Load CSS data from a mod folder. Returns list of character dicts."""
        prc_path = os.path.join(mod_folder, "ui", "param", "database", "ui_chara_db.prc")
        msbt_path = os.path.join(mod_folder, "ui", "message", "msg_name.msbt")

        if not os.path.exists(prc_path):
            raise FileNotFoundError(f"ui_chara_db.prc not found in {mod_folder}/ui/param/database/")
        if not os.path.exists(msbt_path):
            raise FileNotFoundError(f"msg_name.msbt not found in {mod_folder}/ui/message/")

        self.mod_folder = mod_folder
        self.prc_path = prc_path
        self.msbt_path = msbt_path
        self.prc_root = self.prc_handler.load(Path(prc_path))
        self.db_root = self.prc_handler.get_db_root(self.prc_root)
        self.msbt_file = self.msbt_handler.load(Path(msbt_path))

        self._load_characters()
        return self.characters

    def _load_characters(self):
        """Load characters from PRC+MSBT into internal list."""
        self.characters = []
        for i, chara in enumerate(list(self.db_root)):
            ui_chara_id = str(chara['ui_chara_id'].value)
            name_id = str(chara['name_id'].value)
            fighter_kind = str(chara['fighter_kind'].value)
            disp_order = chara['disp_order'].value

            name_normal = self.msbt_handler.get_entry(self.msbt_file, f"nam_chr1_00_{name_id}") or ""
            name_upper = self.msbt_handler.get_entry(self.msbt_file, f"nam_chr2_00_{name_id}") or ""

            self.characters.append({
                "index": i,
                "ui_chara_id": ui_chara_id,
                "name_id": name_id,
                "fighter_kind": fighter_kind,
                "disp_order": disp_order,
                "Name (Normal)": name_normal,
                "Name (Uppercase)": name_upper,
                "color_num": chara['color_num'].value if 'color_num' in chara else 8,
                "c00_index": chara['c00_index'].value if 'c00_index' in chara else 0,
                "c01_index": chara['c01_index'].value if 'c01_index' in chara else 1,
                "c02_index": chara['c02_index'].value if 'c02_index' in chara else 2,
                "c03_index": chara['c03_index'].value if 'c03_index' in chara else 3,
                "c04_index": chara['c04_index'].value if 'c04_index' in chara else 4,
                "c05_index": chara['c05_index'].value if 'c05_index' in chara else 5,
                "c06_index": chara['c06_index'].value if 'c06_index' in chara else 6,
                "c07_index": chara['c07_index'].value if 'c07_index' in chara else 7,
                "chara_ref": chara
            })

    def save(self) -> None:
        """Save PRC and MSBT files."""
        self.prc_handler.save(self.prc_root, Path(self.prc_path))
        self.msbt_handler.save(self.msbt_file, Path(self.msbt_path))
        self._load_characters()

    def update_field(self, chara: dict, field: str, val: str) -> None:
        """Update a character field in both the dict and PRC/MSBT."""
        chara[field] = val

        if field in ["ui_chara_id", "fighter_kind"]:
            try:
                self.prc_handler.set_hash_value(chara['chara_ref'], field, val)
            except Exception:
                pass
        elif field == "name_id":
            chara['chara_ref'][field].value = val
        elif field in ["disp_order", "color_num",
                        "c00_index", "c01_index", "c02_index", "c03_index",
                        "c04_index", "c05_index", "c06_index", "c07_index"]:
            try:
                val_int = int(val)
                self.prc_handler.safe_set_value(chara['chara_ref'], field, val_int)
            except ValueError:
                pass
        elif field == "Name (Normal)":
            name_id = chara['name_id']
            self.msbt_handler.set_entry(self.msbt_file, f"nam_chr1_00_{name_id}", val)
        elif field == "Name (Uppercase)":
            name_id = chara['name_id']
            self.msbt_handler.set_entry(self.msbt_file, f"nam_chr2_00_{name_id}", val)
            self.msbt_handler.set_entry(self.msbt_file, f"nam_chr3_00_{name_id}", val)

    def duplicate_character(self, base_chara: dict) -> dict:
        """Duplicate a character and add to the database."""
        import pyprc

        new_chara_ref = base_chara['chara_ref'].clone()
        new_list = list(self.db_root) + [new_chara_ref]
        self.db_root.set_list(new_list)

        new_index = len(self.characters)
        new_chara = {
            "index": new_index,
            "ui_chara_id": base_chara["ui_chara_id"] + "_copy",
            "name_id": base_chara["name_id"] + "_copy",
            "fighter_kind": base_chara["fighter_kind"],
            "disp_order": -1,
            "Name (Normal)": base_chara["Name (Normal)"] + " Copy",
            "Name (Uppercase)": base_chara["Name (Uppercase)"] + " COPY",
            "color_num": base_chara["color_num"],
            "c00_index": base_chara["c00_index"],
            "c01_index": base_chara["c01_index"],
            "c02_index": base_chara["c02_index"],
            "c03_index": base_chara["c03_index"],
            "c04_index": base_chara["c04_index"],
            "c05_index": base_chara["c05_index"],
            "c06_index": base_chara["c06_index"],
            "c07_index": base_chara["c07_index"],
            "chara_ref": new_chara_ref
        }

        new_chara_ref['ui_chara_id'].value = pyprc.hash(new_chara["ui_chara_id"])
        new_chara_ref['name_id'].value = new_chara["name_id"]
        new_chara_ref['disp_order'].value = new_chara["disp_order"]

        self.msbt_handler.set_entry(self.msbt_file, f"nam_chr1_00_{new_chara['name_id']}", new_chara["Name (Normal)"])
        self.msbt_handler.set_entry(self.msbt_file, f"nam_chr2_00_{new_chara['name_id']}", new_chara["Name (Uppercase)"])
        self.msbt_handler.set_entry(self.msbt_file, f"nam_chr3_00_{new_chara['name_id']}", new_chara["Name (Uppercase)"])

        self.characters.append(new_chara)
        return new_chara

    def hide_character(self, chara: dict) -> None:
        """Hide a character by setting disp_order to -1."""
        chara["disp_order"] = -1
        chara['chara_ref']['disp_order'].value = -1

    def delete_character(self, index: int) -> None:
        """Delete a character from the database."""
        entries = list(self.db_root)
        entries.pop(index)
        self.db_root.set_list(entries)
        self.characters.pop(index)

    def is_custom_character(self, chara: dict) -> bool:
        """Check if a character is custom (not vanilla)."""
        fk = str(chara.get('fighter_kind', ''))
        nid = str(chara.get('name_id', ''))
        fk_name = fk.replace('fighter_kind_', '') if fk.startswith('fighter_kind_') else fk
        return fk_name != nid

    def detect_name_id_from_mod(self, mod_dir: str) -> Optional[str]:
        """Detect name_id from a mod folder by scanning files."""
        detected_name_id = None

        # Method 1: Portrait files
        portrait_dir = os.path.join(mod_dir, "ui", "replace", "chara", "chara_0")
        if os.path.isdir(portrait_dir):
            for fname in os.listdir(portrait_dir):
                m = re.match(r'chara_0_(.+?)_\d+\.bntx', fname)
                if m:
                    detected_name_id = m.group(1)
                    break

        # Method 2: xmsbt name labels
        if not detected_name_id:
            xmsbt_path = os.path.join(mod_dir, "ui", "message", "msg_name.xmsbt")
            if os.path.exists(xmsbt_path):
                try:
                    with open(xmsbt_path, 'r', encoding='utf-16') as xf:
                        xmsbt_content = xf.read()
                    m = re.search(r'nam_chr1_00_(\w+)', xmsbt_content)
                    if m:
                        detected_name_id = m.group(1)
                except Exception:
                    pass

        # Method 3: Narration sound files
        if not detected_name_id:
            narration_dir = os.path.join(mod_dir, "sound", "bank", "narration")
            if os.path.isdir(narration_dir):
                for fname in os.listdir(narration_dir):
                    m = re.match(r'vc_narration_characall_(.+?)\.idsp', fname)
                    if m:
                        detected_name_id = m.group(1)
                        break

        return detected_name_id

    def resort_custom_characters(self) -> None:
        """Re-sort visible custom characters alphabetically."""
        vanilla_max_logical = -1
        custom_visible = []

        for chara in self.characters:
            d = chara['disp_order']
            if d == -1:
                continue
            logical_d = d if d >= 0 else d + 256
            if not self.is_custom_character(chara):
                if logical_d > vanilla_max_logical:
                    vanilla_max_logical = logical_d
            else:
                custom_visible.append(chara)

        if not custom_visible:
            return

        custom_visible.sort(key=lambda c: c['Name (Normal)'].upper())
        start_disp = vanilla_max_logical + 1

        for i, chara in enumerate(custom_visible):
            new_logical = start_disp + i
            new_signed = new_logical if new_logical <= 127 else new_logical - 256
            chara['disp_order'] = new_signed
            self.prc_handler.safe_set_value(chara['chara_ref'], 'disp_order', new_signed)

    def auto_hide_unused(self) -> dict:
        """Scan mods directory, hide characters without matching mods."""
        mods_root = os.path.dirname(self.mod_folder)
        installed_name_ids = set()

        for folder_name in os.listdir(mods_root):
            folder_path = os.path.join(mods_root, folder_name)
            if not os.path.isdir(folder_path):
                continue
            if os.path.normpath(folder_path) == os.path.normpath(self.mod_folder):
                continue

            name_id = self.detect_name_id_from_mod(folder_path)
            if name_id:
                installed_name_ids.add(name_id)

        hidden_count = 0
        shown_count = 0

        for chara in self.characters:
            if not self.is_custom_character(chara):
                continue

            if chara['name_id'] in installed_name_ids:
                if chara['disp_order'] == -1:
                    chara['disp_order'] = 0
                    try:
                        chara['chara_ref']['disp_order'].value = 0
                    except Exception:
                        pass
                    shown_count += 1
            else:
                if chara['disp_order'] != -1:
                    chara['disp_order'] = -1
                    chara['chara_ref']['disp_order'].value = -1
                    hidden_count += 1

        self.resort_custom_characters()

        return {
            "installed_count": len(installed_name_ids),
            "shown_count": shown_count,
            "hidden_count": hidden_count,
            "installed_name_ids": sorted(installed_name_ids)
        }

    def one_click_add(self, mod_dir: str) -> dict:
        """Auto-detect and add a character from a mod directory. Returns info dict or raises."""
        import pyprc

        config_path = os.path.join(mod_dir, "config.json")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"No config.json found in {mod_dir}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        dir_infos = config.get("new-dir-infos", [])
        if not dir_infos:
            raise ValueError("No 'new-dir-infos' found in config.json.")

        fighter_kind_str = None
        costumes = set()

        for dir_path in dir_infos:
            match = re.search(r'fighter/([^/]+)/c(\d{2,3})', dir_path)
            if match:
                if not fighter_kind_str:
                    fighter_kind_str = match.group(1)
                costumes.add(int(match.group(2)))

        if not fighter_kind_str or not costumes:
            raise ValueError("Could not detect base fighter or costume slots from config.json.")

        costumes = sorted(list(costumes))

        # Find base character
        base_chara = None
        for chara in self.characters:
            if chara["fighter_kind"] == f"fighter_kind_{fighter_kind_str}":
                base_chara = chara
                break

        if not base_chara:
            raise ValueError(f"Could not find base fighter 'fighter_kind_{fighter_kind_str}' in CSS database.")

        # Auto-detect name_id
        detected_name_id = self.detect_name_id_from_mod(mod_dir)
        display_name = None

        # Get display name from xmsbt
        xmsbt_path = os.path.join(mod_dir, "ui", "message", "msg_name.xmsbt")
        if os.path.exists(xmsbt_path):
            try:
                with open(xmsbt_path, 'r', encoding='utf-16') as xf:
                    xmsbt_content = xf.read()
                name_match = re.search(r'<entry label="nam_chr1_00_\w+">\s*<text>(.*?)</text>', xmsbt_content, re.DOTALL)
                if name_match:
                    display_name = name_match.group(1).strip()
            except Exception:
                pass

        # Fallback: clean up folder name
        if not display_name:
            folder_name = os.path.basename(mod_dir)
            display_name = re.sub(r'\{.*?\}|\(.*?\)|\[.*?\]|Moveset|V\d+|by .*', '', folder_name, flags=re.IGNORECASE).strip()
            display_name = re.sub(r'[-_~]', ' ', display_name).strip()
            if not display_name:
                display_name = "New Character"

        if not detected_name_id:
            detected_name_id = re.sub(r'[^a-z0-9]', '', display_name.lower())

        # Detect announcer label
        announcer_label = None
        narration_dir = os.path.join(mod_dir, "sound", "bank", "narration")
        if os.path.isdir(narration_dir):
            for fname in os.listdir(narration_dir):
                if fname.startswith("vc_narration_characall_") and fname.endswith(".idsp"):
                    announcer_label = fname.replace(".idsp", "")
                    break

        # Return detection info for the UI to confirm with user
        return {
            "fighter_kind_str": fighter_kind_str,
            "detected_name_id": detected_name_id,
            "display_name": display_name,
            "costumes": costumes,
            "announcer_label": announcer_label,
            "base_chara": base_chara,
        }

    def finalize_add_character(self, detection_info: dict, final_name: str) -> dict:
        """Finalize adding a character after user confirmation."""
        import pyprc

        fighter_kind_str = detection_info["fighter_kind_str"]
        detected_name_id = detection_info["detected_name_id"]
        costumes = detection_info["costumes"]
        announcer_label = detection_info["announcer_label"]
        base_chara = detection_info["base_chara"]

        new_name_id = detected_name_id
        new_ui_chara_id = f"ui_chara_{detected_name_id}"

        new_chara_ref = base_chara['chara_ref'].clone()
        new_list = list(self.db_root) + [new_chara_ref]
        self.db_root.set_list(new_list)

        new_index = len(self.characters)
        new_chara = {
            "index": new_index,
            "ui_chara_id": new_ui_chara_id,
            "name_id": new_name_id,
            "fighter_kind": base_chara["fighter_kind"],
            "disp_order": 0,
            "Name (Normal)": final_name,
            "Name (Uppercase)": final_name.upper(),
            "color_num": len(costumes),
            "c00_index": costumes[0] if len(costumes) > 0 else 0,
            "c01_index": costumes[1] if len(costumes) > 1 else costumes[0],
            "c02_index": costumes[2] if len(costumes) > 2 else costumes[0],
            "c03_index": costumes[3] if len(costumes) > 3 else costumes[0],
            "c04_index": costumes[4] if len(costumes) > 4 else costumes[0],
            "c05_index": costumes[5] if len(costumes) > 5 else costumes[0],
            "c06_index": costumes[6] if len(costumes) > 6 else costumes[0],
            "c07_index": costumes[7] if len(costumes) > 7 else costumes[0],
            "chara_ref": new_chara_ref
        }

        new_chara_ref['ui_chara_id'].value = pyprc.hash(new_chara["ui_chara_id"])
        new_chara_ref['name_id'].value = new_chara["name_id"]

        if announcer_label:
            try:
                new_chara_ref['characall_label_c00'].value = pyprc.hash(announcer_label)
            except Exception:
                pass

        self.prc_handler.safe_set_value(new_chara_ref, 'disp_order', new_chara["disp_order"])
        self.prc_handler.safe_set_value(new_chara_ref, 'color_num', new_chara["color_num"])
        for i in range(8):
            field_name = f"c0{i}_index"
            if field_name in new_chara_ref:
                self.prc_handler.safe_set_value(new_chara_ref, field_name, new_chara[field_name])

        self.msbt_handler.set_entry(self.msbt_file, f"nam_chr1_00_{new_chara['name_id']}", new_chara["Name (Normal)"])
        self.msbt_handler.set_entry(self.msbt_file, f"nam_chr2_00_{new_chara['name_id']}", new_chara["Name (Uppercase)"])
        self.msbt_handler.set_entry(self.msbt_file, f"nam_chr3_00_{new_chara['name_id']}", new_chara["Name (Uppercase)"])

        self.characters.append(new_chara)
        self.resort_custom_characters()

        return new_chara

    def auto_fill_from_config(self, config_path: str) -> dict:
        """Parse config.json and return fighter/costume data."""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        dir_infos = config.get("new-dir-infos", [])
        if not dir_infos:
            raise ValueError("No 'new-dir-infos' found in config.json.")

        fighter_kind = None
        costumes = set()

        for dir_path in dir_infos:
            match = re.search(r'fighter/([^/]+)/c([0-9]{2})', dir_path)
            if match:
                if not fighter_kind:
                    fighter_kind = match.group(1)
                costumes.add(int(match.group(2)))

        if not fighter_kind or not costumes:
            raise ValueError("Could not detect fighter kind or costume slots.")

        return {
            "fighter_kind": f"fighter_kind_{fighter_kind}",
            "costumes": sorted(list(costumes)),
        }
