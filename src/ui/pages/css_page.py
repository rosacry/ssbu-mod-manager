"""CSS Editor page - refactored from original css_manager.py UI."""
import tkinter as tk
from tkinter import filedialog, messagebox
import tkinter.simpledialog as sd
import customtkinter as ctk
from src.ui.base_page import BasePage
from src.utils.logger import logger


class CSSPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self.selected_index = -1
        self.filtered_indices = []
        self._build_ui()

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 5))

        title = ctk.CTkLabel(header_frame, text="CSS Editor",
                             font=ctk.CTkFont(size=24, weight="bold"), anchor="w")
        title.pack(side="left")

        self.save_btn = ctk.CTkButton(header_frame, text="Save Changes",
                                      command=self.save_changes, state="disabled",
                                      fg_color="#2fa572", hover_color="#106a43",
                                      corner_radius=8, height=34, width=130)
        self.save_btn.pack(side="right", padx=(5, 0))

        self.load_btn = ctk.CTkButton(header_frame, text="Load CSS Mod Folder",
                                      command=self.load_mod_folder,
                                      fg_color="#555555", hover_color="#444444",
                                      corner_radius=8, height=34, width=160)
        self.load_btn.pack(side="right")

        # Summary / status
        summary_frame = ctk.CTkFrame(self, fg_color="transparent")
        summary_frame.pack(fill="x", padx=30, pady=(2, 10))

        self.status_label = ctk.CTkLabel(summary_frame, text="No CSS mod loaded.",
                                         font=ctk.CTkFont(size=12), text_color="#999999", anchor="w")
        self.status_label.pack(side="left")

        # Main content frame
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=30, pady=(0, 5))

        # Left panel - character list
        left_frame = ctk.CTkFrame(main_frame, width=420, fg_color="#242438", corner_radius=10)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        left_frame.pack_propagate(False)

        ctk.CTkLabel(left_frame, text="Characters",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=12, pady=(12, 5))

        # Quick action buttons at top
        action_row = ctk.CTkFrame(left_frame, fg_color="transparent")
        action_row.pack(fill="x", padx=10, pady=(0, 5))

        self.one_click_btn = ctk.CTkButton(
            action_row, text="1-Click Add from Mod",
            command=self.one_click_add_character, state="disabled",
            fg_color="#2fa572", hover_color="#106a43",
            corner_radius=6, height=30, font=ctk.CTkFont(size=11),
        )
        self.one_click_btn.pack(fill="x", pady=2)

        self.auto_hide_btn = ctk.CTkButton(
            action_row, text="Auto-Detect & Hide Unused",
            command=self.auto_hide_unused, state="disabled",
            fg_color="#b08a2a", hover_color="#8a6b1f",
            corner_radius=6, height=30, font=ctk.CTkFont(size=11),
        )
        self.auto_hide_btn.pack(fill="x", pady=2)

        self.search_var = tk.StringVar()
        self.search_var.trace("w", self._update_listbox)
        ctk.CTkEntry(left_frame, placeholder_text="Search characters...",
                     textvariable=self.search_var, height=32
                     ).pack(fill="x", padx=10, pady=5)

        self.listbox = tk.Listbox(left_frame, bg="#1e1e2e", fg="#cccccc",
                                  selectbackground="#1f538d",
                                  selectforeground="white",
                                  font=("Segoe UI", 10),
                                  relief="flat", bd=0, highlightthickness=0)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # Bottom action buttons
        btn_row = ctk.CTkFrame(left_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 10))

        self.add_btn = ctk.CTkButton(btn_row, text="Duplicate Selected",
                                     command=self.add_character, state="disabled",
                                     fg_color="#555555", hover_color="#444444",
                                     corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        self.add_btn.pack(fill="x", pady=2)

        self.hide_btn = ctk.CTkButton(btn_row, text="Hide Selected (disp_order = -1)",
                                      command=self.hide_character, state="disabled",
                                      fg_color="#555555", hover_color="#444444",
                                      corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        self.hide_btn.pack(fill="x", pady=2)

        self.delete_btn = ctk.CTkButton(btn_row, text="Delete Selected",
                                        command=self.delete_character, state="disabled",
                                        fg_color="#b02a2a", hover_color="#8a1f1f",
                                        corner_radius=6, height=30, font=ctk.CTkFont(size=11))
        self.delete_btn.pack(fill="x", pady=2)

        # Right panel - character details
        right_frame = ctk.CTkFrame(main_frame, fg_color="#242438", corner_radius=10)
        right_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))

        ctk.CTkLabel(right_frame, text="Character Details",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=12, pady=(12, 5))

        details_frame = ctk.CTkScrollableFrame(right_frame, fg_color="transparent")
        details_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Form fields
        self.fields = {}
        field_names = [
            "ui_chara_id", "name_id", "fighter_kind", "disp_order",
            "Name (Normal)", "Name (Uppercase)",
            "color_num", "c00_index", "c01_index", "c02_index", "c03_index",
            "c04_index", "c05_index", "c06_index", "c07_index"
        ]
        for row, field in enumerate(field_names):
            lbl = ctk.CTkLabel(details_frame, text=field + ":",
                               font=ctk.CTkFont(size=12), anchor="e")
            lbl.grid(row=row, column=0, sticky="e", padx=(10, 5), pady=3)

            var = tk.StringVar()
            var.trace("w", lambda name, index, mode, f=field: self._on_field_change(f))
            entry = ctk.CTkEntry(details_frame, textvariable=var, width=280, height=30)
            entry.grid(row=row, column=1, sticky="w", padx=(5, 10), pady=3)

            self.fields[field] = var

        self.autofill_btn = ctk.CTkButton(details_frame, text="Auto-Fill from config.json",
                                          command=self.auto_fill_from_config, state="disabled",
                                          fg_color="#555555", hover_color="#444444",
                                          corner_radius=6, height=30)
        self.autofill_btn.grid(row=len(field_names), column=0, columnspan=2, pady=15)

    @property
    def css_manager(self):
        return self.app.css_manager

    def on_show(self):
        # Auto-load if css_mod_folder is set in settings
        settings = self.app.config_manager.settings
        if settings.css_mod_folder and not self.css_manager.mod_folder:
            folder = str(settings.css_mod_folder)
            self._try_load(folder)

    def load_mod_folder(self):
        folder = filedialog.askdirectory(title="Select CSS Mod Folder (e.g., CUSTOM REQUEST CSS)")
        if not folder:
            return
        self._try_load(folder)

    def _try_load(self, folder):
        try:
            self.css_manager.load(folder)
            folder_name = folder.split('/')[-1].split('\\')[-1]
            self.status_label.configure(
                text=f"Loaded: {folder_name} ({len(self.css_manager.characters)} characters)",
                text_color="#2fa572")
            self._update_listbox()
            self._enable_buttons()
            # Save to settings
            from pathlib import Path
            self.app.config_manager.update_setting("css_mod_folder", Path(folder))
            logger.info("CSS", f"Loaded CSS mod folder: {folder}")
            return True
        except FileNotFoundError as e:
            messagebox.showerror("Error", str(e))
            return False
        except Exception as e:
            logger.error("CSS", f"Failed to load CSS mod: {e}")
            messagebox.showerror("Error", f"Failed to load: {e}")
            return False

    def _enable_buttons(self):
        for btn in [self.save_btn, self.add_btn, self.hide_btn,
                    self.one_click_btn, self.delete_btn, self.auto_hide_btn]:
            btn.configure(state="normal")

    def _update_listbox(self, *args):
        search_term = self.search_var.get().lower()
        self.listbox.delete(0, tk.END)
        self.filtered_indices = []

        for i, chara in enumerate(self.css_manager.characters):
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

    def _on_select(self, event):
        selection = self.listbox.curselection()
        if not selection:
            return
        list_index = selection[0]
        self.selected_index = self.filtered_indices[list_index]
        chara = self.css_manager.characters[self.selected_index]

        for field in self.fields:
            self.fields[field].set(str(chara[field]))

        self.autofill_btn.configure(state="normal")

    def _on_field_change(self, field):
        if self.selected_index == -1:
            return
        val = self.fields[field].get()
        chara = self.css_manager.characters[self.selected_index]
        self.css_manager.update_field(chara, field, val)

    def add_character(self):
        if self.selected_index == -1:
            messagebox.showwarning("Warning", "Select a character to duplicate first.")
            return
        base = self.css_manager.characters[self.selected_index]
        self.css_manager.duplicate_character(base)
        self._update_listbox()

        self.search_var.set("")
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(tk.END)
        self.listbox.event_generate("<<ListboxSelect>>")
        self.listbox.see(tk.END)
        logger.info("CSS", "Character duplicated")
        messagebox.showinfo("Success", "Character duplicated! Edit ui_chara_id, name_id, and disp_order.")

    def hide_character(self):
        if self.selected_index == -1:
            messagebox.showwarning("Warning", "Select a character to hide first.")
            return
        chara = self.css_manager.characters[self.selected_index]
        self.css_manager.hide_character(chara)
        self.fields["disp_order"].set("-1")
        self._update_listbox()
        logger.info("CSS", f"Character hidden: {chara['Name (Normal)']}")
        messagebox.showinfo("Success", "Character hidden (disp_order = -1).")

    def delete_character(self):
        if self.selected_index == -1:
            messagebox.showwarning("Warning", "Select a character to delete first.")
            return
        chara = self.css_manager.characters[self.selected_index]
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Delete '{chara['Name (Normal)']}' ({chara['ui_chara_id']})?\n\nCannot be undone after saving.")
        if not confirm:
            return

        self.css_manager.delete_character(self.selected_index)
        self.selected_index = -1
        for field in self.fields:
            self.fields[field].set("")
        self._update_listbox()
        logger.info("CSS", f"Character deleted: {chara['Name (Normal)']}")
        messagebox.showinfo("Success", "Character deleted. Click 'Save Changes' to finalize.")

    def auto_hide_unused(self):
        if not self.css_manager.mod_folder:
            messagebox.showwarning("Warning", "Load a CSS mod folder first.")
            return

        results = self.css_manager.auto_hide_unused()
        self._update_listbox()
        logger.info("CSS", f"Auto-hide: shown={results['shown_count']}, hidden={results['hidden_count']}")

        messagebox.showinfo("Auto-Hide Results",
            f"Scanned mods directory:\n\n"
            f"Installed mods detected: {results['installed_count']}\n"
            f"Characters shown: {results['shown_count']}\n"
            f"Characters hidden: {results['hidden_count']}\n\n"
            f"Detected name_ids:\n{', '.join(results['installed_name_ids'])}\n\n"
            f"Don't forget to click 'Save Changes' when done.")

    def one_click_add_character(self):
        mod_dir = filedialog.askdirectory(title="Select Character Mod Folder")
        if not mod_dir:
            return

        try:
            detection = self.css_manager.one_click_add(mod_dir)

            info_text = f"Detected base fighter: {detection['fighter_kind_str'].title()}\n"
            info_text += f"Detected name_id: {detection['detected_name_id']}\n"
            info_text += f"Detected costumes: {detection['costumes']}\n"
            if detection['announcer_label']:
                info_text += f"Detected announcer: {detection['announcer_label']}\n"
            info_text += f"\nEnter the Character's Display Name:"

            final_name = sd.askstring("Character Name", info_text,
                                      initialvalue=detection['display_name'], parent=self)
            if not final_name:
                return

            new_chara = self.css_manager.finalize_add_character(detection, final_name)
            self._update_listbox()

            self.search_var.set("")
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(tk.END)
            self.listbox.event_generate("<<ListboxSelect>>")
            self.listbox.see(tk.END)

            final_disp = new_chara['disp_order']
            logical = final_disp if final_disp >= 0 else final_disp + 256
            summary = f"Successfully added {final_name}!\n\n"
            summary += f"Base Fighter: {detection['fighter_kind_str']}\n"
            summary += f"name_id: {detection['detected_name_id']}\n"
            summary += f"Costumes: {detection['costumes']}\n"
            summary += f"Display Order: {logical}\n"
            if detection['announcer_label']:
                summary += f"Announcer: {detection['announcer_label']}\n"
            summary += f"\nDon't forget to click 'Save Changes'."

            logger.info("CSS", f"Added character: {final_name}")
            messagebox.showinfo("Success", summary)

        except Exception as e:
            logger.error("CSS", f"Failed to auto-add character: {e}")
            messagebox.showerror("Error", f"Failed to auto-add character: {e}")

    def auto_fill_from_config(self):
        if self.selected_index == -1:
            messagebox.showwarning("Warning", "Select a character first.")
            return

        config_path = filedialog.askopenfilename(title="Select config.json",
                                                  filetypes=[("JSON Files", "*.json")])
        if not config_path:
            return

        try:
            result = self.css_manager.auto_fill_from_config(config_path)
            self.fields["fighter_kind"].set(result["fighter_kind"])
            self.fields["color_num"].set(str(len(result["costumes"])))
            for i in range(8):
                if i < len(result["costumes"]):
                    self.fields[f"c0{i}_index"].set(str(result["costumes"][i]))
                else:
                    self.fields[f"c0{i}_index"].set(str(result["costumes"][0]))
            logger.info("CSS", f"Auto-filled from config: {result['fighter_kind']}")
            messagebox.showinfo("Success",
                f"Auto-filled for {result['fighter_kind']} with "
                f"{len(result['costumes'])} costumes: {result['costumes']}")
        except Exception as e:
            logger.error("CSS", f"Failed to parse config.json: {e}")
            messagebox.showerror("Error", f"Failed to parse config.json: {e}")

    def save_changes(self):
        try:
            self.css_manager.save()
            logger.info("CSS", "Changes saved successfully")
            messagebox.showinfo("Success", "Changes saved successfully!")
            self._update_listbox()
        except Exception as e:
            logger.error("CSS", f"Failed to save: {e}")
            messagebox.showerror("Error", f"Failed to save: {e}")
