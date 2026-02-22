"""Emulator Migration page — migrate, export, and import SSBU data between emulators.

Switch emulators each run their own multiplayer/LDN networks, so online rooms
are NOT cross-compatible between emulators. This page makes it easy to migrate
all SSBU data (mods, plugins, saves, etc.) to a different emulator with one click.
"""

import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pathlib import Path
from src.ui.base_page import BasePage
from src.paths import auto_detect_all_emulators, EMULATOR_PATHS
from src.core.emulator_migrator import (
    scan_emulator_data, create_migration_plan, execute_migration,
    export_ssbu_data, import_ssbu_data, get_emulator_sdmc_path,
    direct_export_emulator_data, direct_import_emulator_data,
    scan_emulator_extended_data,
)
from src.utils.logger import logger


class MigrationPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._migrating = False
        self._build_ui()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(25, 5))

        ctk.CTkLabel(header, text="Emulator Migration",
                     font=ctk.CTkFont(size=24, weight="bold"), anchor="w"
                     ).pack(side="left")

        desc = ctk.CTkLabel(self,
            text="Migrate your SSBU data between emulators. Different emulators run separate multiplayer "
                 "networks (LDN), so online rooms are NOT cross-compatible — you need the same emulator "
                 "as your friends to play together online.",
            font=ctk.CTkFont(size=12), text_color="#999999", anchor="w", wraplength=800,
            justify="left")
        desc.pack(fill="x", padx=30, pady=(0, 15))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=30)
        self._scroll = scroll

        # === Section 1: Emulator-to-Emulator Migration ===
        migrate_section = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        migrate_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(migrate_section, text="Migrate Between Emulators",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(migrate_section,
                     text="Copy all SSBU data from one emulator to another. The source data is preserved.",
                     font=ctk.CTkFont(size=12), text_color="#999999", anchor="w"
                     ).pack(fill="x", padx=15, pady=(0, 10))

        # Source / Target selection
        sel_frame = ctk.CTkFrame(migrate_section, fg_color="transparent")
        sel_frame.pack(fill="x", padx=15, pady=5)

        emulator_names = list(EMULATOR_PATHS.keys())

        # Source
        src_frame = ctk.CTkFrame(sel_frame, fg_color="transparent")
        src_frame.pack(side="left", padx=(0, 30))
        ctk.CTkLabel(src_frame, text="Source Emulator:",
                     font=ctk.CTkFont(size=13), anchor="w").pack(anchor="w")
        self.source_var = ctk.StringVar(value=emulator_names[0] if emulator_names else "")
        self.source_menu = ctk.CTkOptionMenu(
            src_frame, variable=self.source_var, values=emulator_names,
            width=180, height=34, command=self._on_source_changed)
        self.source_menu.pack(anchor="w", pady=5)
        self.source_status = ctk.CTkLabel(src_frame, text="",
                                          font=ctk.CTkFont(size=11), text_color="#888888", anchor="w")
        self.source_status.pack(anchor="w")

        # Arrow
        ctk.CTkLabel(sel_frame, text="\u27a1", font=ctk.CTkFont(size=24),
                     text_color="#e94560").pack(side="left", padx=10, pady=(15, 0))

        # Target
        tgt_frame = ctk.CTkFrame(sel_frame, fg_color="transparent")
        tgt_frame.pack(side="left", padx=(30, 0))
        ctk.CTkLabel(tgt_frame, text="Target Emulator:",
                     font=ctk.CTkFont(size=13), anchor="w").pack(anchor="w")
        self.target_var = ctk.StringVar(value=emulator_names[1] if len(emulator_names) > 1 else "")
        self.target_menu = ctk.CTkOptionMenu(
            tgt_frame, variable=self.target_var, values=emulator_names,
            width=180, height=34)
        self.target_menu.pack(anchor="w", pady=5)
        self.target_status = ctk.CTkLabel(tgt_frame, text="",
                                          font=ctk.CTkFont(size=11), text_color="#888888", anchor="w")
        self.target_status.pack(anchor="w")

        # Data category checkboxes
        cat_frame = ctk.CTkFrame(migrate_section, fg_color="#1e1e38", corner_radius=8)
        cat_frame.pack(fill="x", padx=15, pady=(10, 5))
        ctk.CTkLabel(cat_frame, text="Data to Migrate:",
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=12, pady=(10, 5))

        self.category_vars = {}
        categories = [
            ("Mods", "All mod folders (characters, skins, stages, UI, audio)", True),
            ("Skyline Plugins", "ARCropolis, HDR, and other Skyline plugins", True),
            ("Skyline Framework", "Skyline runtime hooks (subsdk9, main.npdm)", True),
            ("Save Data", "Game saves (unlocks, replays, spirits, custom stages)", True),
            ("NAND System", "NAND system data (user profiles, emulator settings)", False),
        ]

        for label, desc_text, default in categories:
            var = ctk.BooleanVar(value=default)
            self.category_vars[label] = var
            row = ctk.CTkFrame(cat_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkCheckBox(row, text=label, variable=var,
                            font=ctk.CTkFont(size=12)).pack(side="left")
            ctk.CTkLabel(row, text=f"  — {desc_text}",
                         font=ctk.CTkFont(size=11), text_color="#777777"
                         ).pack(side="left")

        # Overwrite option
        ow_frame = ctk.CTkFrame(migrate_section, fg_color="transparent")
        ow_frame.pack(fill="x", padx=15, pady=5)
        self.overwrite_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(ow_frame, text="Overwrite existing files at target",
                        variable=self.overwrite_var,
                        font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkLabel(ow_frame, text="  (unchecked = skip files that already exist)",
                     font=ctk.CTkFont(size=11), text_color="#777777").pack(side="left")

        # Scan & Migrate buttons
        btn_frame = ctk.CTkFrame(migrate_section, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkButton(btn_frame, text="\u2315  Scan Source", width=140,
                      fg_color="#1f538d", hover_color="#163b6a",
                      command=self._scan_source, height=36, corner_radius=8
                      ).pack(side="left", padx=(0, 10))

        self.migrate_btn = ctk.CTkButton(btn_frame, text="\u27a1  Migrate Now", width=160,
                      fg_color="#2fa572", hover_color="#106a43",
                      command=self._start_migration, height=36, corner_radius=8)
        self.migrate_btn.pack(side="left")

        # Scan results area
        self.scan_result_frame = ctk.CTkFrame(migrate_section, fg_color="transparent")
        self.scan_result_frame.pack(fill="x", padx=15, pady=(5, 15))

        # === Section 2: Export / Import ===
        export_section = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        export_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(export_section, text="Direct Export / Import",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(export_section,
                     text="Export ALL emulator data directly — no need to use the emulator's own export tool. "
                          "This reads data straight from the emulator's AppData directories, including keys, "
                          "firmware, and profiles that aren't in the SDMC root.",
                     font=ctk.CTkFont(size=12), text_color="#999999", anchor="w", wraplength=700
                     ).pack(fill="x", padx=15, pady=(0, 10))

        # Direct export info note
        direct_note = ctk.CTkFrame(export_section, fg_color="#1a1a30", corner_radius=6)
        direct_note.pack(fill="x", padx=15, pady=(0, 8))
        ctk.CTkLabel(direct_note,
            text="\u2139  Direct Export reads from emulator directories automatically — "
                 "you do NOT need to open the emulator first or use its Data Manager page.",
            font=ctk.CTkFont(size=11), text_color="#6688bb", anchor="w",
            wraplength=680, justify="left"
        ).pack(fill="x", padx=12, pady=8)

        # Export emulator selection
        exp_sel_frame = ctk.CTkFrame(export_section, fg_color="transparent")
        exp_sel_frame.pack(fill="x", padx=15, pady=(0, 5))
        ctk.CTkLabel(exp_sel_frame, text="Export from:",
                     font=ctk.CTkFont(size=13), anchor="w").pack(side="left")
        self.export_emu_var = ctk.StringVar(value=emulator_names[0] if emulator_names else "")
        ctk.CTkOptionMenu(exp_sel_frame, variable=self.export_emu_var,
                          values=emulator_names, width=180, height=32,
                          command=self._on_export_emu_changed
                          ).pack(side="left", padx=10)
        self._export_emu_status = ctk.CTkLabel(exp_sel_frame, text="",
                                               font=ctk.CTkFont(size=11),
                                               text_color="#888888", anchor="w")
        self._export_emu_status.pack(side="left", padx=5)

        # Extra data checkboxes
        self._extra_cat_frame = ctk.CTkFrame(export_section, fg_color="#1e1e38", corner_radius=8)
        self._extra_cat_frame.pack(fill="x", padx=15, pady=(0, 8))
        ctk.CTkLabel(self._extra_cat_frame, text="Extended Data (beyond SDMC):",
                     font=ctk.CTkFont(size=13, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=12, pady=(10, 5))

        self.extra_include_sdmc = ctk.BooleanVar(value=True)
        self.extra_include_extra = ctk.BooleanVar(value=True)

        row_sdmc = ctk.CTkFrame(self._extra_cat_frame, fg_color="transparent")
        row_sdmc.pack(fill="x", padx=12, pady=2)
        ctk.CTkCheckBox(row_sdmc, text="SDMC Data (mods, plugins, saves)",
                        variable=self.extra_include_sdmc,
                        font=ctk.CTkFont(size=12)).pack(side="left")

        row_extra = ctk.CTkFrame(self._extra_cat_frame, fg_color="transparent")
        row_extra.pack(fill="x", padx=12, pady=2)
        ctk.CTkCheckBox(row_extra, text="Extended Data (keys, firmware, profiles)",
                        variable=self.extra_include_extra,
                        font=ctk.CTkFont(size=12)).pack(side="left")

        self._extra_details = ctk.CTkLabel(self._extra_cat_frame, text="",
                                           font=ctk.CTkFont(size=11),
                                           text_color="#888888", anchor="w",
                                           wraplength=680, justify="left")
        self._extra_details.pack(fill="x", padx=12, pady=(3, 8))

        exp_btn_frame = ctk.CTkFrame(export_section, fg_color="transparent")
        exp_btn_frame.pack(fill="x", padx=15, pady=(5, 5))

        self._direct_export_btn = ctk.CTkButton(
            exp_btn_frame, text="\u21e9  Direct Export", width=180,
            fg_color="#2fa572", hover_color="#248a5d",
            command=self._direct_export, height=36, corner_radius=8)
        self._direct_export_btn.pack(side="left", padx=(0, 10))

        ctk.CTkButton(exp_btn_frame, text="\u21e7  Import from Folder", width=180,
                      fg_color="#555555", hover_color="#444444",
                      command=self._import_data, height=36, corner_radius=8
                      ).pack(side="left")

        # Export progress
        self._export_progress_frame = ctk.CTkFrame(export_section, fg_color="transparent")
        self._export_progress_frame.pack(fill="x", padx=15, pady=(0, 5))

        self._export_status = ctk.CTkLabel(self._export_progress_frame, text="",
                                           font=ctk.CTkFont(size=11),
                                           text_color="#6688bb", anchor="w")
        self._export_progress_bar = ctk.CTkProgressBar(self._export_progress_frame,
                                                        height=4, fg_color="#2a2a45",
                                                        progress_color="#2fa572")
        # Not shown until export starts

        ctk.CTkFrame(export_section, height=8, fg_color="transparent").pack()

        # === Section 3: Detected Emulators Info ===
        info_section = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        info_section.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(info_section, text="Detected Emulators",
                     font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=15, pady=(15, 5))

        self.detected_info_frame = ctk.CTkFrame(info_section, fg_color="transparent")
        self.detected_info_frame.pack(fill="x", padx=15, pady=(0, 15))

        # Progress bar (hidden by default)
        self.progress_frame = ctk.CTkFrame(scroll, fg_color="#242438", corner_radius=10)
        # Not packed initially

        self.progress_label = ctk.CTkLabel(self.progress_frame, text="",
                                           font=ctk.CTkFont(size=12), anchor="w")
        self.progress_label.pack(fill="x", padx=15, pady=(15, 5))

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, width=600)
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 15))
        self.progress_bar.set(0)

    def on_show(self):
        """Refresh detected emulators when page is shown."""
        self._refresh_detected()
        self._on_source_changed(self.source_var.get())

    def _refresh_detected(self):
        """Show all detected emulators with their paths and data summary."""
        for w in self.detected_info_frame.winfo_children():
            w.destroy()

        detected = auto_detect_all_emulators()
        if not detected:
            ctk.CTkLabel(self.detected_info_frame,
                         text="No emulators detected. Install an emulator and set up SSBU first.",
                         font=ctk.CTkFont(size=12), text_color="#888888"
                         ).pack(anchor="w", pady=5)
            return

        for emu_name, emu_path in detected:
            row = ctk.CTkFrame(self.detected_info_frame, fg_color="#1e1e38", corner_radius=6)
            row.pack(fill="x", pady=3)

            name_label = ctk.CTkLabel(row, text=f"\u2713  {emu_name}",
                                      font=ctk.CTkFont(size=13, weight="bold"),
                                      text_color="#2fa572", anchor="w")
            name_label.pack(side="left", padx=(12, 10), pady=8)

            path_label = ctk.CTkLabel(row, text=str(emu_path),
                                      font=ctk.CTkFont(size=11), text_color="#7a7a9a", anchor="w")
            path_label.pack(side="left", padx=5, pady=8)

            # Quick size indicator
            items = scan_emulator_data(emu_path)
            total_files = sum(i.file_count for i in items if i.exists)
            total_size = sum(i.total_size for i in items if i.exists)
            size_mb = total_size / (1024 * 1024) if total_size > 0 else 0

            if total_files > 0:
                size_label = ctk.CTkLabel(row,
                    text=f"{total_files} files, {size_mb:.1f} MB",
                    font=ctk.CTkFont(size=11), text_color="#6688bb", anchor="e")
                size_label.pack(side="right", padx=12, pady=8)

    def _on_source_changed(self, _value=None):
        """Update source status when selection changes."""
        src_name = self.source_var.get()
        src_path = get_emulator_sdmc_path(src_name)
        if src_path:
            self.source_status.configure(text=f"Found: {src_path}", text_color="#2fa572")
        else:
            self.source_status.configure(text="Not installed or no data found", text_color="#e94560")

    def _scan_source(self):
        """Scan the source emulator and show what data is available."""
        src_name = self.source_var.get()
        src_path = get_emulator_sdmc_path(src_name)

        if not src_path:
            messagebox.showwarning("Not Found",
                f"{src_name} SDMC directory not found.\n\n"
                f"Make sure {src_name} is installed and has SSBU data.")
            return

        # Clear previous results
        for w in self.scan_result_frame.winfo_children():
            w.destroy()

        items = scan_emulator_data(src_path)
        found = [i for i in items if i.exists]

        if not found:
            ctk.CTkLabel(self.scan_result_frame,
                         text="No SSBU data found in source emulator.",
                         font=ctk.CTkFont(size=12), text_color="#e94560"
                         ).pack(anchor="w", pady=5)
            return

        ctk.CTkLabel(self.scan_result_frame,
                     text=f"Found {len(found)} data categories in {src_name}:",
                     font=ctk.CTkFont(size=12, weight="bold"), anchor="w"
                     ).pack(anchor="w", pady=(5, 5))

        for item in found:
            size_mb = item.total_size / (1024 * 1024)
            row = ctk.CTkFrame(self.scan_result_frame, fg_color="#1e1e38", corner_radius=6)
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text=f"  \u2713  {item.label}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#2fa572", anchor="w"
                         ).pack(side="left", padx=10, pady=6)
            ctk.CTkLabel(row,
                         text=f"{item.file_count} files, {size_mb:.1f} MB",
                         font=ctk.CTkFont(size=11), text_color="#6688bb", anchor="e"
                         ).pack(side="right", padx=10, pady=6)

        total_files = sum(i.file_count for i in found)
        total_mb = sum(i.total_size for i in found) / (1024 * 1024)
        ctk.CTkLabel(self.scan_result_frame,
                     text=f"Total: {total_files} files, {total_mb:.1f} MB",
                     font=ctk.CTkFont(size=12), text_color="#999999", anchor="w"
                     ).pack(anchor="w", pady=(5, 0))

    def _get_selected_categories(self) -> list[str]:
        """Get list of selected data categories."""
        return [label for label, var in self.category_vars.items() if var.get()]

    def _start_migration(self):
        """Start the emulator-to-emulator migration."""
        if self._migrating:
            return

        src_name = self.source_var.get()
        tgt_name = self.target_var.get()

        if src_name == tgt_name:
            messagebox.showwarning("Invalid", "Source and target emulators must be different.")
            return

        src_path = get_emulator_sdmc_path(src_name)
        if not src_path:
            messagebox.showwarning("Not Found", f"{src_name} SDMC directory not found.")
            return

        selected = self._get_selected_categories()
        if not selected:
            messagebox.showwarning("Nothing Selected", "Select at least one data category to migrate.")
            return

        # Confirm
        msg = (f"Migrate SSBU data:\n\n"
               f"From: {src_name} ({src_path})\n"
               f"To:   {tgt_name}\n\n"
               f"Categories: {', '.join(selected)}\n"
               f"Overwrite: {'Yes' if self.overwrite_var.get() else 'No'}\n\n"
               f"This will copy files to the target emulator. Source data is preserved.\n\n"
               f"Continue?")

        if not messagebox.askyesno("Confirm Migration", msg):
            return

        self._migrating = True
        self.migrate_btn.configure(state="disabled", text="Migrating...")

        # Show progress
        self.progress_frame.pack(fill="x", pady=(0, 15), before=self.progress_frame.master.winfo_children()[-1]
                                 if self.progress_frame.master.winfo_children() else None)
        self.progress_bar.set(0)
        self.progress_label.configure(text="Starting migration...")

        def run_migration():
            tgt_path = get_emulator_sdmc_path(tgt_name)
            if not tgt_path:
                # Create the directory
                import os
                templates = EMULATOR_PATHS.get(tgt_name, [])
                for template in templates:
                    expanded = template
                    for var in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
                        val = os.environ.get(var, "")
                        expanded = expanded.replace("{" + var + "}", val)
                    candidate = Path(expanded)
                    try:
                        candidate.mkdir(parents=True, exist_ok=True)
                        tgt_path = candidate
                        break
                    except OSError:
                        continue

            if not tgt_path:
                self.after(0, lambda: self._migration_done(None, tgt_name))
                return

            plan = create_migration_plan(
                src_name, src_path, tgt_name, tgt_path,
                selected_categories=selected,
            )

            def progress_cb(msg, frac):
                self.after(0, lambda m=msg, f=frac: self._update_progress(m, f))

            result = execute_migration(
                plan,
                overwrite=self.overwrite_var.get(),
                progress_callback=progress_cb,
            )

            self.after(0, lambda: self._migration_done(result, tgt_name))

        threading.Thread(target=run_migration, daemon=True).start()

    def _update_progress(self, message: str, fraction: float):
        """Update progress bar from main thread."""
        try:
            self.progress_label.configure(text=message)
            self.progress_bar.set(fraction)
        except Exception:
            pass

    def _migration_done(self, result, target_name: str):
        """Called when migration completes."""
        self._migrating = False
        self.migrate_btn.configure(state="normal", text="\u27a1  Migrate Now")

        if result is None:
            messagebox.showerror("Error", f"Could not create SDMC directory for {target_name}.")
            return

        try:
            self.progress_frame.pack_forget()
        except Exception:
            pass

        if result.success:
            size_mb = result.bytes_copied / (1024 * 1024)
            msg = (f"Migration complete!\n\n"
                   f"Files copied: {result.files_copied}\n"
                   f"Data transferred: {size_mb:.1f} MB\n"
                   f"Time: {result.duration_seconds:.1f} seconds")
            if result.errors:
                msg += f"\n\nWarnings ({len(result.errors)}):\n" + "\n".join(result.errors[:5])
            messagebox.showinfo("Success", msg)

            # Ask if user wants to switch to the target emulator
            if messagebox.askyesno("Switch Emulator",
                f"Would you like to switch your active emulator to {target_name}?\n\n"
                f"This will update your SDMC path to the {target_name} directory."):
                self._switch_active_emulator(target_name)
        else:
            msg = f"Migration failed.\n\nErrors:\n" + "\n".join(result.errors[:10])
            messagebox.showerror("Migration Failed", msg)

    def _switch_active_emulator(self, emulator_name: str):
        """Switch the app to use a different emulator."""
        from src.paths import derive_mods_path, derive_plugins_path
        path = get_emulator_sdmc_path(emulator_name)
        if path:
            settings = self.app.config_manager.settings
            settings.eden_sdmc_path = path
            settings.mods_path = derive_mods_path(path)
            settings.plugins_path = derive_plugins_path(path)
            settings.emulator = emulator_name
            self.app.config_manager.save(settings)
            self.app._update_managers()
            logger.info("Migration", f"Switched active emulator to {emulator_name}")
            messagebox.showinfo("Switched",
                f"Active emulator changed to {emulator_name}.\n"
                f"SDMC path: {path}")

    def _on_export_emu_changed(self, _value=None):
        """Update export section when emulator selection changes."""
        emu = self.export_emu_var.get()
        sdmc = get_emulator_sdmc_path(emu)

        if sdmc:
            self._export_emu_status.configure(text=f"Found: {sdmc}", text_color="#2fa572")
            # Show extended data info
            extra_items = scan_emulator_extended_data(emu)
            found_extra = [i for i in extra_items if i.exists]
            if found_extra:
                labels = ", ".join(i.label for i in found_extra)
                self._extra_details.configure(
                    text=f"Available extended data: {labels}")
            else:
                self._extra_details.configure(
                    text="No extended data directories found for this emulator.")
        else:
            self._export_emu_status.configure(
                text="Not installed or no data found", text_color="#e94560")
            self._extra_details.configure(text="")

    def _direct_export(self):
        """Direct export: reads data from emulator directories without emulator UI."""
        if self._migrating:
            return

        emu = self.export_emu_var.get()
        if not get_emulator_sdmc_path(emu):
            messagebox.showwarning("Not Found",
                f"{emu} data not found. Make sure it is installed with SSBU data.")
            return

        if not self.extra_include_sdmc.get() and not self.extra_include_extra.get():
            messagebox.showwarning("Nothing Selected",
                "Select at least 'SDMC Data' or 'Extended Data' to export.")
            return

        folder = filedialog.askdirectory(title="Select Export Destination Folder")
        if not folder:
            return

        import time as _t
        export_path = Path(folder) / f"ssbu-{emu.lower()}-export-{_t.strftime('%Y%m%d')}"

        if not messagebox.askyesno("Confirm Direct Export",
            f"Export {emu} data directly to:\n{export_path}\n\n"
            f"Include SDMC: {'Yes' if self.extra_include_sdmc.get() else 'No'}\n"
            f"Include Extended: {'Yes' if self.extra_include_extra.get() else 'No'}\n\n"
            f"This reads from emulator directories — no emulator UI needed."):
            return

        self._migrating = True
        self._direct_export_btn.configure(state="disabled", text="Exporting...")
        self._export_status.pack(fill="x", pady=(5, 2))
        self._export_progress_bar.pack(fill="x", pady=(0, 5))
        self._export_progress_bar.set(0)
        self._export_status.configure(text="Starting export...", text_color="#6688bb")

        def progress_cb(msg, frac):
            try:
                self.after(0, lambda m=msg, f=frac: self._update_export_progress(m, f))
            except Exception:
                pass

        def run():
            try:
                result = direct_export_emulator_data(
                    emulator_name=emu,
                    export_path=export_path,
                    include_sdmc=self.extra_include_sdmc.get(),
                    include_extra=self.extra_include_extra.get(),
                    progress_callback=progress_cb,
                )
                self.after(0, lambda: self._direct_export_done(result, export_path))
            except Exception as e:
                logger.error("Migration", f"Direct export failed: {e}")
                self.after(0, lambda: self._direct_export_done(None, export_path))

        threading.Thread(target=run, daemon=True).start()

    def _update_export_progress(self, message: str, fraction: float):
        try:
            self._export_status.configure(text=message)
            self._export_progress_bar.set(fraction)
        except Exception:
            pass

    def _direct_export_done(self, result, export_path: Path):
        self._migrating = False
        self._direct_export_btn.configure(state="normal", text="\u21e9  Direct Export")

        if result is None:
            self._export_status.configure(text="Export failed!", text_color="#e94560")
            messagebox.showerror("Export Failed", "An unexpected error occurred during export.")
            return

        if result.success:
            size_mb = result.bytes_copied / (1024 * 1024)
            self._export_status.configure(
                text=f"Exported {result.files_copied} files ({size_mb:.1f} MB)",
                text_color="#2fa572")
            self._export_progress_bar.set(1.0)
            messagebox.showinfo("Export Complete",
                f"Direct export complete!\n\n"
                f"Files exported: {result.files_copied}\n"
                f"Data size: {size_mb:.1f} MB\n"
                f"Time: {result.duration_seconds:.1f} seconds\n"
                f"Saved to: {export_path}\n\n"
                f"You can import this into any emulator using the Import button.")
        else:
            self._export_status.configure(text="Export had errors", text_color="#d4a017")
            messagebox.showwarning("Export Warnings",
                f"Export completed with {len(result.errors)} error(s):\n"
                + "\n".join(result.errors[:10]))

    def _export_data(self):
        """Legacy export: SDMC data only to a user-chosen folder."""
        settings = self.app.config_manager.settings
        if not settings.eden_sdmc_path:
            messagebox.showwarning("Warning", "Set up your emulator SDMC path in Settings first.")
            return

        folder = filedialog.askdirectory(title="Select Export Destination Folder")
        if not folder:
            return

        selected = self._get_selected_categories()
        if not selected:
            messagebox.showwarning("Nothing Selected", "Select at least one data category to export.")
            return

        export_path = Path(folder) / "ssbu-export"
        if not messagebox.askyesno("Confirm Export",
            f"Export SSBU data to:\n{export_path}\n\n"
            f"Categories: {', '.join(selected)}"):
            return

        self._migrating = True

        def run_export():
            def progress_cb(msg, frac):
                pass  # Silent for legacy export

            result = export_ssbu_data(
                settings.eden_sdmc_path, export_path,
                selected_categories=selected,
                progress_callback=progress_cb,
            )
            self.after(0, lambda: self._export_done(result, export_path))

        threading.Thread(target=run_export, daemon=True).start()

    def _export_done(self, result, export_path: Path):
        self._migrating = False
        if result.success:
            size_mb = result.bytes_copied / (1024 * 1024)
            messagebox.showinfo("Export Complete",
                f"Exported {result.files_copied} files ({size_mb:.1f} MB) to:\n{export_path}")
        else:
            messagebox.showerror("Export Failed", "\n".join(result.errors[:10]))

    def _import_data(self):
        """Import SSBU data from an exported folder."""
        settings = self.app.config_manager.settings
        if not settings.eden_sdmc_path:
            messagebox.showwarning("Warning", "Set up your emulator SDMC path in Settings first.")
            return

        folder = filedialog.askdirectory(title="Select Folder to Import From")
        if not folder:
            return

        import_path = Path(folder)

        # Check if this is a direct export (has export_manifest.json or sdmc/ subfolder)
        is_direct = (import_path / "export_manifest.json").exists() or (import_path / "sdmc").exists()

        if is_direct:
            # Use direct import which handles sdmc/ and extra/ subfolders
            emu = settings.emulator or "Current"
            manifest_text = ""
            manifest_file = import_path / "export_manifest.json"
            if manifest_file.exists():
                try:
                    import json
                    with open(manifest_file) as f:
                        manifest = json.load(f)
                    manifest_text = (
                        f"Source emulator: {manifest.get('emulator', 'Unknown')}\n"
                        f"Export date: {manifest.get('timestamp', 'Unknown')}\n"
                        f"Categories: {', '.join(manifest.get('categories', []))}\n"
                    )
                except Exception:
                    pass

            if not messagebox.askyesno("Confirm Import",
                f"Import data from direct export:\n{import_path}\n\n"
                f"{manifest_text}\n"
                f"Import into: {settings.eden_sdmc_path}\n"
                f"Overwrite existing: {'Yes' if self.overwrite_var.get() else 'No'}"):
                return

            self._migrating = True

            def run_import():
                result = direct_import_emulator_data(
                    import_path=import_path,
                    emulator_name=settings.emulator or emu,
                    overwrite=self.overwrite_var.get(),
                )
                self.after(0, lambda: self._import_done(result))

            threading.Thread(target=run_import, daemon=True).start()
        else:
            # Legacy import: same as before
            items = scan_emulator_data(import_path)
            found = [i for i in items if i.exists]
            if not found:
                messagebox.showwarning("No Data Found",
                    f"No SSBU data structure found in:\n{import_path}\n\n"
                    f"Expected directories like 'ultimate/mods/', 'atmosphere/contents/', etc.\n"
                    f"Or a direct export with 'sdmc/' and 'export_manifest.json'.")
                return

            total_files = sum(i.file_count for i in found)
            categories = [i.label for i in found]

            if not messagebox.askyesno("Confirm Import",
                f"Import SSBU data from:\n{import_path}\n\n"
                f"Found: {', '.join(categories)}\n"
                f"Total files: {total_files}\n\n"
                f"Import into: {settings.eden_sdmc_path}"):
                return

            self._migrating = True

            def run_import():
                result = import_ssbu_data(
                    import_path, settings.eden_sdmc_path,
                    overwrite=self.overwrite_var.get(),
                )
                self.after(0, lambda: self._import_done(result))

            threading.Thread(target=run_import, daemon=True).start()

    def _import_done(self, result):
        self._migrating = False
        if result.success:
            size_mb = result.bytes_copied / (1024 * 1024)
            messagebox.showinfo("Import Complete",
                f"Imported {result.files_copied} files ({size_mb:.1f} MB).")
            # Refresh managers
            self.app._update_managers()
        else:
            messagebox.showerror("Import Failed", "\n".join(result.errors[:10]))
