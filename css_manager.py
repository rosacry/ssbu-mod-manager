import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import pyprc
from LMS.Message.MSBT import MSBT
from LMS.Stream.Reader import Reader
from LMS.Stream.Writer import Writer
import io

# Initialize customtkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class CSSManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SSBU CSS Manager")
        self.geometry("1200x800")

        # Load ParamLabels.csv
        self.labels_path = os.path.join(os.path.dirname(__file__), "ParamLabels.csv")
        if os.path.exists(self.labels_path):
            pyprc.hash.load_labels(self.labels_path)
        else:
            messagebox.showwarning("Warning", "ParamLabels.csv not found. Hashes will not be resolved to strings.")

        self.mod_folder = ""
        self.prc_path = ""
        self.msbt_path = ""
        self.prc_root = None
        self.db_root = None
        self.msbt_file = None
        self.characters = []
        self.selected_index = -1

        self.setup_ui()

    def setup_ui(self):
        # Top frame for loading
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.pack(fill="x", padx=10, pady=10)

        self.load_btn = ctk.CTkButton(self.top_frame, text="Load Mod Folder", command=self.load_mod_folder)
        self.load_btn.pack(side="left", padx=10, pady=10)

        self.save_btn = ctk.CTkButton(self.top_frame, text="Save Changes", command=self.save_changes, state="disabled")
        self.save_btn.pack(side="left", padx=10, pady=10)

        self.status_label = ctk.CTkLabel(self.top_frame, text="No mod loaded.")
        self.status_label.pack(side="left", padx=10, pady=10)

        # Main frame
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Left frame for character list
        self.left_frame = ctk.CTkFrame(self.main_frame, width=450)
        self.left_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        self.one_click_add_btn = ctk.CTkButton(self.left_frame, text="✨ 1-Click Add Character from Mod ✨", command=self.one_click_add_character, state="disabled", fg_color="#2fa572", hover_color="#106a43")
        self.one_click_add_btn.pack(fill="x", padx=10, pady=10)

        self.auto_hide_btn = ctk.CTkButton(self.left_frame, text="🔍 Auto-Detect & Hide Unused", command=self.auto_hide_unused, state="disabled", fg_color="#b08a2a", hover_color="#8a6b1f")
        self.auto_hide_btn.pack(fill="x", padx=10, pady=5)

        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.update_listbox)
        self.search_entry = ctk.CTkEntry(self.left_frame, placeholder_text="Search...", textvariable=self.search_var)
        self.search_entry.pack(fill="x", padx=10, pady=10)

        self.listbox = tk.Listbox(self.left_frame, bg="#2b2b2b", fg="white", selectbackground="#1f538d", font=("Arial", 12))
        self.listbox.pack(fill="both", expand=True, padx=10, pady=10)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        self.add_btn = ctk.CTkButton(self.left_frame, text="Duplicate Selected (Add New)", command=self.add_character, state="disabled")
        self.add_btn.pack(fill="x", padx=10, pady=5)

        self.hide_btn = ctk.CTkButton(self.left_frame, text="Hide Selected (disp_order = -1)", command=self.hide_character, state="disabled")
        self.hide_btn.pack(fill="x", padx=10, pady=5)

        self.delete_btn = ctk.CTkButton(self.left_frame, text="Delete Selected", command=self.delete_character, state="disabled", fg_color="#b02a2a", hover_color="#8a1f1f")
        self.delete_btn.pack(fill="x", padx=10, pady=5)

        # Right frame for character details
        self.right_frame = ctk.CTkFrame(self.main_frame)
        self.right_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        self.details_frame = ctk.CTkScrollableFrame(self.right_frame)
        self.details_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Form fields
        self.fields = {}
        row = 0
        field_names = [
            "ui_chara_id", "name_id", "fighter_kind", "disp_order", 
            "Name (Normal)", "Name (Uppercase)",
            "color_num", "c00_index", "c01_index", "c02_index", "c03_index",
            "c04_index", "c05_index", "c06_index", "c07_index"
        ]
        for field in field_names:
            lbl = ctk.CTkLabel(self.details_frame, text=field + ":")
            lbl.grid(row=row, column=0, sticky="e", padx=10, pady=2)
            
            var = tk.StringVar()
            var.trace("w", lambda name, index, mode, f=field: self.on_field_change(f))
            entry = ctk.CTkEntry(self.details_frame, textvariable=var, width=300)
            entry.grid(row=row, column=1, sticky="w", padx=10, pady=2)
            
            self.fields[field] = var
            row += 1

        self.autofill_btn = ctk.CTkButton(self.details_frame, text="Auto-Fill from Mod config.json", command=self.auto_fill_from_config, state="disabled")
        self.autofill_btn.grid(row=row, column=0, columnspan=2, pady=20)

    def load_mod_folder(self):
        folder = filedialog.askdirectory(title="Select Mod Folder (e.g., CUSTOM REQUEST CSS)")
        if not folder:
            return

        self.prc_path = os.path.join(folder, "ui", "param", "database", "ui_chara_db.prc")
        self.msbt_path = os.path.join(folder, "ui", "message", "msg_name.msbt")

        if not os.path.exists(self.prc_path):
            messagebox.showerror("Error", f"ui_chara_db.prc not found in {folder}/ui/param/database/")
            return
        if not os.path.exists(self.msbt_path):
            messagebox.showerror("Error", f"msg_name.msbt not found in {folder}/ui/message/")
            return

        self.mod_folder = folder
        self.status_label.configure(text=f"Loaded: {os.path.basename(folder)}")
        
        try:
            self.prc_root = pyprc.param(self.prc_path)
            self.db_root = list(self.prc_root)[0][1]
            with open(self.msbt_path, 'rb') as f:
                msbt_data = f.read()
            self.msbt_file = MSBT()
            self.msbt_file.read(Reader(msbt_data))
            
            self.load_characters()
            self.save_btn.configure(state="normal")
            self.add_btn.configure(state="normal")
            self.hide_btn.configure(state="normal")
            self.one_click_add_btn.configure(state="normal")
            self.delete_btn.configure(state="normal")
            self.auto_hide_btn.configure(state="normal")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load files: {e}")

    def load_characters(self):
        self.characters = []
        for i, chara in enumerate(list(self.db_root)):
            ui_chara_id = str(chara['ui_chara_id'].value)
            name_id = str(chara['name_id'].value)
            fighter_kind = str(chara['fighter_kind'].value)
            disp_order = chara['disp_order'].value
            
            # Get names from MSBT
            name_normal = ""
            name_upper = ""
            
            try:
                index1 = self.msbt_file.LBL1.get_index_by_label(f"nam_chr1_00_{name_id}")
                if index1 is not None and index1 < len(self.msbt_file.TXT2.messages):
                    name_normal = self.msbt_file.TXT2.messages[index1]
            except Exception:
                pass

            try:
                index2 = self.msbt_file.LBL1.get_index_by_label(f"nam_chr2_00_{name_id}")
                if index2 is not None and index2 < len(self.msbt_file.TXT2.messages):
                    name_upper = self.msbt_file.TXT2.messages[index2]
            except Exception:
                pass
                
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
            
        self.update_listbox()

    def update_listbox(self, *args):
        search_term = self.search_var.get().lower()
        self.listbox.delete(0, tk.END)
        self.filtered_indices = []
        
        for i, chara in enumerate(self.characters):
            # Show logical display order (0-255) instead of raw signed byte
            raw_disp = chara['disp_order']
            if isinstance(raw_disp, int):
                logical_disp = raw_disp if raw_disp >= 0 else raw_disp + 256
                if raw_disp == -1:
                    logical_disp = "Hidden"
            else:
                logical_disp = raw_disp
            display_text = f"[{logical_disp}] {chara['Name (Normal)']} ({chara['ui_chara_id']})"
            if search_term in display_text.lower():
                self.listbox.insert(tk.END, display_text)
                self.filtered_indices.append(i)

    def on_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return
            
        list_index = selection[0]
        self.selected_index = self.filtered_indices[list_index]
        chara = self.characters[self.selected_index]
        
        for field in self.fields:
            self.fields[field].set(str(chara[field]))
            
        self.autofill_btn.configure(state="normal")

    def on_field_change(self, field):
        if self.selected_index == -1:
            return
            
        val = self.fields[field].get()
        chara = self.characters[self.selected_index]
        chara[field] = val
        
        # Update PRC
        if field in ["ui_chara_id", "fighter_kind"]:
            try:
                if val.startswith("0x"):
                    chara['chara_ref'][field].value = pyprc.hash(int(val, 16))
                else:
                    chara['chara_ref'][field].value = pyprc.hash(val)
            except:
                pass # Invalid hash string
        elif field == "name_id":
            chara['chara_ref'][field].value = val
        elif field in ["disp_order", "color_num", "c00_index", "c01_index", "c02_index", "c03_index", "c04_index", "c05_index", "c06_index", "c07_index"]:
            try:
                val_int = int(val)
                try:
                    chara['chara_ref'][field].value = val_int
                except Exception as e:
                    if "out of range" in str(e).lower():
                        if val_int > 127:
                            chara['chara_ref'][field].value = val_int - 256
                        elif val_int < 0:
                            chara['chara_ref'][field].value = val_int + 256
            except ValueError:
                pass
                
        # Update MSBT
        elif field == "Name (Normal)":
            name_id = chara['name_id']
            self.msbt_set_entry(f"nam_chr1_00_{name_id}", val)
        elif field == "Name (Uppercase)":
            name_id = chara['name_id']
            self.msbt_set_entry(f"nam_chr2_00_{name_id}", val)
            self.msbt_set_entry(f"nam_chr3_00_{name_id}", val)

    def add_character(self):
        if self.selected_index == -1:
            messagebox.showwarning("Warning", "Please select a character to duplicate first.")
            return
            
        base_chara = self.characters[self.selected_index]
        new_chara_ref = base_chara['chara_ref'].clone()
        
        # Add to PRC
        new_list = list(self.db_root) + [new_chara_ref]
        self.db_root.set_list(new_list)
        
        # Create new character dict
        new_index = len(self.characters)
        new_chara = {
            "index": new_index,
            "ui_chara_id": base_chara["ui_chara_id"] + "_copy",
            "name_id": base_chara["name_id"] + "_copy",
            "fighter_kind": base_chara["fighter_kind"],
            "disp_order": -1, # Hidden by default
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
        
        # Update PRC values
        new_chara_ref['ui_chara_id'].value = pyprc.hash(new_chara["ui_chara_id"])
        new_chara_ref['name_id'].value = new_chara["name_id"]
        new_chara_ref['disp_order'].value = new_chara["disp_order"]
        
        # Add to MSBT
        self.msbt_set_entry(f"nam_chr1_00_{new_chara['name_id']}", new_chara["Name (Normal)"])
        self.msbt_set_entry(f"nam_chr2_00_{new_chara['name_id']}", new_chara["Name (Uppercase)"])
        self.msbt_set_entry(f"nam_chr3_00_{new_chara['name_id']}", new_chara["Name (Uppercase)"])
        
        self.characters.append(new_chara)
        self.update_listbox()
        
        # Select the new character
        self.search_var.set("")
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(tk.END)
        self.listbox.event_generate("<<ListboxSelect>>")
        self.listbox.see(tk.END)
        
        messagebox.showinfo("Success", "Character duplicated! Please edit the ui_chara_id, name_id, and disp_order.")

    def hide_character(self):
        if self.selected_index == -1:
            messagebox.showwarning("Warning", "Please select a character to hide first.")
            return
            
        chara = self.characters[self.selected_index]
        chara["disp_order"] = -1
        chara['chara_ref']['disp_order'].value = -1
        self.fields["disp_order"].set("-1")
        self.update_listbox()
        messagebox.showinfo("Success", "Character hidden (disp_order set to -1).")

    def delete_character(self):
        if self.selected_index == -1:
            messagebox.showwarning("Warning", "Please select a character to delete first.")
            return
            
        chara = self.characters[self.selected_index]
        confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to permanently delete '{chara['Name (Normal)']}' ({chara['ui_chara_id']})?\n\nThis cannot be undone after saving.")
        if not confirm:
            return
            
        # Remove from PRC list
        entries = list(self.db_root)
        entries.pop(self.selected_index)
        self.db_root.set_list(entries)
        
        # Remove from character list
        self.characters.pop(self.selected_index)
        self.selected_index = -1
        
        # Clear fields
        for field in self.fields:
            self.fields[field].set("")
        
        self.update_listbox()
        messagebox.showinfo("Success", "Character deleted. Click 'Save Changes' to finalize.")

    def is_custom_character(self, chara):
        """Check if a character entry is custom (not vanilla)."""
        fk = str(chara.get('fighter_kind', ''))
        nid = str(chara.get('name_id', ''))
        fk_name = fk.replace('fighter_kind_', '') if fk.startswith('fighter_kind_') else fk
        return fk_name != nid

    def detect_name_id_from_mod(self, mod_dir):
        """Detect the name_id used by a mod folder by scanning portrait files, xmsbt, and narration sounds."""
        import re
        detected_name_id = None

        # Method 1: Portrait files (chara_0_{name_id}_{num}.bntx)
        portrait_dir = os.path.join(mod_dir, "ui", "replace", "chara", "chara_0")
        if os.path.isdir(portrait_dir):
            for fname in os.listdir(portrait_dir):
                m = re.match(r'chara_0_(.+?)_\d+\.bntx', fname)
                if m:
                    detected_name_id = m.group(1)
                    break

        # Method 2: xmsbt name labels (nam_chr1_00_{name_id})
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

        # Method 3: Narration sound files (vc_narration_characall_{name_id}.idsp)
        if not detected_name_id:
            narration_dir = os.path.join(mod_dir, "sound", "bank", "narration")
            if os.path.isdir(narration_dir):
                for fname in os.listdir(narration_dir):
                    m = re.match(r'vc_narration_characall_(.+?)\.idsp', fname)
                    if m:
                        detected_name_id = m.group(1)
                        break

        return detected_name_id

    def resort_custom_characters(self):
        """Re-sort all visible custom characters alphabetically and reassign disp_orders."""
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

        def safe_set_disp(ref, fld, v):
            try:
                ref[fld].value = v
            except Exception as e:
                if "out of range" in str(e).lower():
                    if v > 127: ref[fld].value = v - 256
                    elif v < 0: ref[fld].value = v + 256

        for i, chara in enumerate(custom_visible):
            new_logical = start_disp + i
            new_signed = new_logical if new_logical <= 127 else new_logical - 256
            chara['disp_order'] = new_signed
            safe_set_disp(chara['chara_ref'], 'disp_order', new_signed)

    def msbt_set_entry(self, label, text):
        """Set an MSBT entry, updating if it exists or creating if it doesn't. No warnings."""
        try:
            index = self.msbt_file.LBL1.get_index_by_label(label)
            if index is not None and index < len(self.msbt_file.TXT2.messages):
                self.msbt_file.TXT2.messages[index] = text
                return
        except (KeyError, Exception):
            pass
        try:
            self.msbt_file.add_data(label)
            self.msbt_file.TXT2.messages[-1] = text
        except Exception:
            pass  # Entry already exists via xmsbt overlay

    def auto_hide_unused(self):
        """Scan mods directory, hide custom characters without matching mods, show those with mods."""
        if not self.mod_folder:
            messagebox.showwarning("Warning", "Please load a CSS mod folder first.")
            return

        mods_root = os.path.dirname(self.mod_folder)

        # Build set of installed name_ids by scanning each mod folder
        installed_name_ids = set()

        for folder_name in os.listdir(mods_root):
            folder_path = os.path.join(mods_root, folder_name)
            if not os.path.isdir(folder_path):
                continue
            if os.path.normpath(folder_path) == os.path.normpath(self.mod_folder):
                continue  # Skip the CSS mod folder itself

            name_id = self.detect_name_id_from_mod(folder_path)
            if name_id:
                installed_name_ids.add(name_id)

        # Process each character
        hidden_count = 0
        shown_count = 0

        for chara in self.characters:
            if not self.is_custom_character(chara):
                continue  # Skip vanilla characters

            if chara['name_id'] in installed_name_ids:
                if chara['disp_order'] == -1:
                    chara['disp_order'] = 0  # Temporary, resort will fix
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

        # Re-sort visible custom characters alphabetically
        self.resort_custom_characters()
        self.update_listbox()

        messagebox.showinfo("Auto-Hide Results",
            f"Scanned mods directory:\n\n"
            f"Installed mods detected: {len(installed_name_ids)}\n"
            f"Characters shown: {shown_count}\n"
            f"Characters hidden: {hidden_count}\n\n"
            f"Detected name_ids:\n{', '.join(sorted(installed_name_ids))}\n\n"
            f"Don't forget to click 'Save Changes' when done.")

    def one_click_add_character(self):
        mod_dir = filedialog.askdirectory(title="Select Character Mod Folder (e.g., Mecha Sonic Moveset V2)")
        if not mod_dir:
            return
            
        config_path = os.path.join(mod_dir, "config.json")
        if not os.path.exists(config_path):
            messagebox.showerror("Error", f"No config.json found in {mod_dir}. Cannot auto-detect fighter data.")
            return
            
        try:
            import json
            import re
            import glob
            import tkinter.simpledialog as sd
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            dir_infos = config.get("new-dir-infos", [])
            if not dir_infos:
                messagebox.showerror("Error", "No 'new-dir-infos' found in config.json.")
                return
                
            fighter_kind_str = None
            costumes = set()
            
            for dir_path in dir_infos:
                match = re.search(r'fighter/([^/]+)/c(\d{2,3})', dir_path)
                if match:
                    if not fighter_kind_str:
                        fighter_kind_str = match.group(1)
                    costumes.add(int(match.group(2)))
                    
            if not fighter_kind_str or not costumes:
                messagebox.showerror("Error", "Could not detect base fighter or costume slots from config.json.")
                return
                
            costumes = sorted(list(costumes))
            
            # Find base character in current DB
            base_chara = None
            for chara in self.characters:
                if chara["fighter_kind"] == f"fighter_kind_{fighter_kind_str}":
                    base_chara = chara
                    break
                    
            if not base_chara:
                messagebox.showerror("Error", f"Could not find base fighter 'fighter_kind_{fighter_kind_str}' in the current CSS database.")
                return
            
            # --- AUTO-DETECT name_id FROM MOD FILES ---
            detected_name_id = self.detect_name_id_from_mod(mod_dir)
            display_name = None
            
            # Get display name from xmsbt if available
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
            
            # Detect announcer label from sound files
            announcer_label = None
            narration_dir = os.path.join(mod_dir, "sound", "bank", "narration")
            if os.path.isdir(narration_dir):
                for fname in os.listdir(narration_dir):
                    if fname.startswith("vc_narration_characall_") and fname.endswith(".idsp"):
                        announcer_label = fname.replace(".idsp", "")
                        break
            
            # Ask user for the final display name
            info_text = f"Detected base fighter: {fighter_kind_str.title()}\n"
            info_text += f"Detected name_id: {detected_name_id}\n"
            info_text += f"Detected costumes: {costumes}\n"
            if announcer_label:
                info_text += f"Detected announcer: {announcer_label}\n"
            info_text += f"\nEnter the Character's Display Name:"
            
            final_name = sd.askstring("Character Name", info_text, initialvalue=display_name, parent=self)
            
            if not final_name:
                return # User cancelled
                
            # Use the detected name_id (from mod files), NOT generated from display name
            new_name_id = detected_name_id
            new_ui_chara_id = f"ui_chara_{detected_name_id}"
            
            # Disp order placeholder - will be set by alphabetical sorting
            new_disp_order = 0
            
            # Duplicate base character
            new_chara_ref = base_chara['chara_ref'].clone()
            new_list = list(self.db_root) + [new_chara_ref]
            self.db_root.set_list(new_list)
            
            new_index = len(self.characters)
            new_chara = {
                "index": new_index,
                "ui_chara_id": new_ui_chara_id,
                "name_id": new_name_id,
                "fighter_kind": base_chara["fighter_kind"],
                "disp_order": new_disp_order,
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
            
            # Update PRC values
            new_chara_ref['ui_chara_id'].value = pyprc.hash(new_chara["ui_chara_id"])
            new_chara_ref['name_id'].value = new_chara["name_id"]
            
            # Set announcer voice label
            if announcer_label:
                try:
                    new_chara_ref['characall_label_c00'].value = pyprc.hash(announcer_label)
                except Exception as e:
                    print(f"Failed to set announcer label: {e}")
            
            def safe_set(ref, fld, v):
                try:
                    ref[fld].value = v
                except Exception as e:
                    if "out of range" in str(e).lower():
                        if v > 127: ref[fld].value = v - 256
                        elif v < 0: ref[fld].value = v + 256
            
            safe_set(new_chara_ref, 'disp_order', new_chara["disp_order"])
            safe_set(new_chara_ref, 'color_num', new_chara["color_num"])
            for i in range(8):
                field_name = f"c0{i}_index"
                if field_name in new_chara_ref:
                    safe_set(new_chara_ref, field_name, new_chara[field_name])
            
            # Add to MSBT (update if exists, create if not — no warnings)
            self.msbt_set_entry(f"nam_chr1_00_{new_chara['name_id']}", new_chara["Name (Normal)"])
            self.msbt_set_entry(f"nam_chr2_00_{new_chara['name_id']}", new_chara["Name (Uppercase)"])
            self.msbt_set_entry(f"nam_chr3_00_{new_chara['name_id']}", new_chara["Name (Uppercase)"])
            
            self.characters.append(new_chara)
            
            # Sort custom characters alphabetically and reassign disp_orders
            self.resort_custom_characters()
            self.update_listbox()
            
            # Select the new character
            self.search_var.set("")
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(tk.END)
            self.listbox.event_generate("<<ListboxSelect>>")
            self.listbox.see(tk.END)
            
            # Get the final disp_order after alphabetical sorting
            final_disp = new_chara['disp_order']
            logical_disp_display = final_disp if final_disp >= 0 else final_disp + 256
            summary = f"Successfully added {final_name}!\n\n"
            summary += f"Base Fighter: {fighter_kind_str}\n"
            summary += f"name_id: {new_name_id}\n"
            summary += f"Costumes: {costumes}\n"
            summary += f"Display Order: {logical_disp_display}\n"
            if announcer_label:
                summary += f"Announcer: {announcer_label}\n"
            summary += f"\nDon't forget to click 'Save Changes' when you're done."
            
            messagebox.showinfo("Success", summary)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to auto-add character: {e}")

    def auto_fill_from_config(self):
        if self.selected_index == -1:
            messagebox.showwarning("Warning", "Please select a character to auto-fill first.")
            return
            
        config_path = filedialog.askopenfilename(title="Select config.json", filetypes=[("JSON Files", "*.json")])
        if not config_path:
            return
            
        try:
            import json
            import re
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # Look for new-dir-infos
            dir_infos = config.get("new-dir-infos", [])
            if not dir_infos:
                messagebox.showerror("Error", "No 'new-dir-infos' found in config.json.")
                return
                
            # Extract fighter kind and costume slots
            # Example: "fighter/samus/c80"
            fighter_kind = None
            costumes = set()
            
            for dir_path in dir_infos:
                match = re.search(r'fighter/([^/]+)/c([0-9]{2})', dir_path)
                if match:
                    if not fighter_kind:
                        fighter_kind = match.group(1)
                    costumes.add(int(match.group(2)))
                    
            if not fighter_kind or not costumes:
                messagebox.showerror("Error", "Could not detect fighter kind or costume slots from config.json.")
                return
                
            costumes = sorted(list(costumes))
            
            # Update fields
            self.fields["fighter_kind"].set(f"fighter_kind_{fighter_kind}")
            self.fields["color_num"].set(str(len(costumes)))
            
            for i in range(8):
                field_name = f"c0{i}_index"
                if i < len(costumes):
                    self.fields[field_name].set(str(costumes[i]))
                else:
                    # If less than 8 costumes, just repeat the first one
                    self.fields[field_name].set(str(costumes[0]))
                    
            messagebox.showinfo("Success", f"Auto-filled for {fighter_kind} with {len(costumes)} costumes: {costumes}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to parse config.json: {e}")

    def save_changes(self):
        try:
            self.prc_root.save(self.prc_path)
            buffer = io.BytesIO()
            self.msbt_file.write(Writer(buffer))
            with open(self.msbt_path, 'wb') as f:
                f.write(buffer.getvalue())
            messagebox.showinfo("Success", "Changes saved successfully!")
            self.load_characters() # Reload to reflect changes
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save files: {e}")

if __name__ == "__main__":
    app = CSSManagerApp()
    app.mainloop()
