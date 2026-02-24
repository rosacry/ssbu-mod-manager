"""Plugins management page - compact rows with accent bars."""
import customtkinter as ctk
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.models.plugin import PluginStatus
from src.utils.logger import logger


class PluginsPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._loaded = False
        self._context_menu = None
        self._build_ui()

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(20, 8))

        title = ctk.CTkLabel(header_frame, text="Skyline Plugin Management",
                             font=ctk.CTkFont(size=24, weight="bold"), anchor="w")
        title.pack(side="left")

        refresh_btn = ctk.CTkButton(header_frame, text="Refresh", width=100,
                                    command=self._force_refresh,
                                    corner_radius=8, height=34)
        refresh_btn.pack(side="right", padx=(5, 0))

        open_btn = ctk.CTkButton(header_frame, text="Open Folder", width=110,
                                 command=self._open_folder,
                                 fg_color="#555555", hover_color="#444444",
                                 corner_radius=8, height=34)
        open_btn.pack(side="right", padx=(5, 0))

        disable_all_btn = ctk.CTkButton(header_frame, text="Disable All", width=100,
                                        command=self._disable_all,
                                        fg_color="#8b2e2e", hover_color="#6e2424",
                                        corner_radius=8, height=34)
        disable_all_btn.pack(side="right", padx=(5, 0))

        enable_all_btn = ctk.CTkButton(header_frame, text="Enable All", width=100,
                                       command=self._enable_all,
                                       fg_color="#2e6b3e", hover_color="#245530",
                                       corner_radius=8, height=34)
        enable_all_btn.pack(side="right", padx=(5, 0))

        # Plugin count
        self.count_label = ctk.CTkLabel(self, text="",
                                        font=ctk.CTkFont(size=12),
                                        text_color="#888888", anchor="w")
        self.count_label.pack(fill="x", padx=32, pady=(0, 6))

        settings = self.app.config_manager.settings
        self._friendly_names_var = ctk.BooleanVar(
            value=getattr(settings, "use_plugin_friendly_names", True)
        )
        self._show_descriptions_var = ctk.BooleanVar(
            value=getattr(settings, "show_plugin_descriptions", True)
        )
        name_controls = ctk.CTkFrame(self, fg_color="transparent")
        name_controls.pack(fill="x", padx=32, pady=(0, 8))

        ctk.CTkCheckBox(
            name_controls,
            text="Use plugin names",
            variable=self._friendly_names_var,
            command=self._toggle_friendly_names,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(0, 14))

        ctk.CTkCheckBox(
            name_controls,
            text="Show descriptions",
            variable=self._show_descriptions_var,
            command=self._toggle_show_descriptions,
            font=ctk.CTkFont(size=12),
        ).pack(side="left")

        self._reset_names_btn = ctk.CTkButton(
            name_controls,
            text="Reset Custom Names",
            width=150,
            height=28,
            corner_radius=6,
            fg_color="#333352",
            hover_color="#444470",
            font=ctk.CTkFont(size=11),
            command=self._reset_custom_names,
        )
        self._reset_names_btn.pack(side="right")

        # Scrollable plugin list
        self.plugin_list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.plugin_list.pack(fill="both", expand=True, padx=25, pady=(0, 10))

        # Warning note
        note_frame = ctk.CTkFrame(self, fg_color="#2e2020", corner_radius=8)
        note_frame.pack(fill="x", padx=30, pady=(5, 15))

        ctk.CTkLabel(
            note_frame,
            text="\u26a0  Disabling required plugins (like ARCropolis) will prevent mods from loading.",
            font=ctk.CTkFont(size=11),
            text_color="#e94560",
        ).pack(fill="x", padx=15, pady=8)

    def on_show(self):
        if not self._loaded:
            self._refresh()

    def on_hide(self):
        self._close_context_menu()

    def _force_refresh(self):
        self.app.plugin_manager.invalidate_cache()
        self._loaded = False
        self._refresh()

    def _refresh(self):
        settings = self.app.config_manager.settings
        self._friendly_names_var.set(getattr(settings, "use_plugin_friendly_names", True))
        self._show_descriptions_var.set(getattr(settings, "show_plugin_descriptions", True))
        overrides = dict(getattr(settings, "plugin_name_overrides", {}) or {})
        has_overrides = any(v.strip() for v in overrides.values())
        self._reset_names_btn.configure(state="normal" if has_overrides else "disabled")
        if not settings.plugins_path or not settings.plugins_path.exists():
            self.count_label.configure(text="No plugins path configured. Go to Settings first.")
            return

        logger.info("Plugins", "Loading plugin list...")
        plugins = self.app.plugin_manager.list_plugins()
        self._loaded = True

        for widget in self.plugin_list.winfo_children():
            widget.destroy()

        active = sum(1 for p in plugins if p.status == PluginStatus.ENABLED)
        self.count_label.configure(
            text=f"{active} active \u00b7 {len(plugins)} total plugins")

        if not plugins:
            ctk.CTkLabel(self.plugin_list,
                         text="No plugins found in the plugins directory.",
                         font=ctk.CTkFont(size=13), text_color="#666666",
                         ).pack(pady=40)
            return

        for plugin in plugins:
            self._render_plugin_row(plugin)

        logger.info("Plugins", f"Rendered {len(plugins)} plugins")

    def _render_plugin_row(self, plugin):
        """Render one plugin row with mods-style compact height."""
        is_enabled = plugin.status == PluginStatus.ENABLED
        is_required = bool(plugin.known_info and plugin.known_info.required)
        use_friendly_names = self._friendly_names_var.get()
        show_descriptions = self._show_descriptions_var.get()

        row_height = 44
        row = ctk.CTkFrame(self.plugin_list, fg_color="#1c1c34", corner_radius=6,
                           height=row_height)
        row.pack(fill="x", pady=1, padx=2)
        row.pack_propagate(False)

        accent_color = "#1f538d" if is_enabled else "#3a3a4a"
        if is_required and is_enabled:
            accent_color = "#e94560"
        accent = ctk.CTkFrame(row, width=4, fg_color=accent_color, corner_radius=2)
        accent.pack(side="left", fill="y", padx=(3, 0), pady=4)

        switch = ctk.CTkSwitch(
            row, text="", width=42, height=20,
            command=lambda p=plugin: self._on_toggle(p),
            onvalue=True, offvalue=False,
            bg_color="#1c1c34",
        )
        switch.pack(side="left", padx=(8, 6))
        if is_enabled:
            switch.select()
        else:
            switch.deselect()

        info_col = ctk.CTkFrame(row, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True, padx=(2, 6), pady=(6, 6))

        name = self._plugin_display_name(plugin) if use_friendly_names else plugin.filename
        display_text = name
        if use_friendly_names:
            base_filename = self._base_plugin_filename(plugin)
            if base_filename and base_filename != name:
                display_text += f"  ({base_filename})"
            if show_descriptions:
                desc = self._plugin_display_description(plugin).strip()
                if desc and desc != name:
                    display_text += f"  \u2014  {desc}"

        name_color = "#d0d0e8" if is_enabled else "#454560"
        ctk.CTkLabel(
            info_col,
            text=display_text,
            font=ctk.CTkFont(size=12),
            text_color=name_color,
            anchor="w",
        ).pack(fill="x")

        if is_required:
            ctk.CTkLabel(
                row,
                text="REQUIRED",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="#e94560",
            ).pack(side="right", padx=(0, 10))

        self._bind_context_menu_recursive(row, plugin)

    def _on_toggle(self, plugin):
        try:
            if plugin.status == PluginStatus.ENABLED:
                if plugin.known_info and plugin.known_info.required:
                    confirm = messagebox.askyesno(
                        "Warning",
                        f"{self._plugin_label(plugin)} is marked as REQUIRED.\n\n"
                        "Disabling it may prevent mods from loading.\n\n"
                        "Are you sure?",
                    )
                    if not confirm:
                        self._loaded = False
                        self._refresh()
                        return
                self.app.plugin_manager.disable_plugin(plugin)
                logger.info("Plugins", f"Disabled: {self._plugin_label(plugin)}")
            else:
                self.app.plugin_manager.enable_plugin(plugin)
                logger.info("Plugins", f"Enabled: {self._plugin_label(plugin)}")
            self._loaded = False
            self._refresh()
        except Exception as e:
            logger.error("Plugins", f"Toggle failed: {e}")
            messagebox.showerror("Error", f"Failed to toggle plugin: {e}")
            self._loaded = False
            self._refresh()

    def _enable_all(self):
        plugins = self.app.plugin_manager.list_plugins()
        disabled = [p for p in plugins if p.status == PluginStatus.DISABLED]
        if not disabled:
            messagebox.showinfo("Info", "All plugins are already enabled.")
            return
        confirm = messagebox.askyesno(
            "Enable All Plugins",
            f"Enable all {len(disabled)} disabled plugin(s)?")
        if not confirm:
            return
        try:
            count = self.app.plugin_manager.enable_all()
            logger.info("Plugins", f"Enabled {count} plugins")
            messagebox.showinfo("Done", f"Enabled {count} plugin(s).")
            self._force_refresh()
        except Exception as e:
            logger.error("Plugins", f"Enable all failed: {e}")
            messagebox.showerror("Error", f"Failed to enable all plugins: {e}")

    def _disable_all(self):
        plugins = self.app.plugin_manager.list_plugins()
        enabled = [p for p in plugins if p.status == PluginStatus.ENABLED]
        if not enabled:
            messagebox.showinfo("Info", "All plugins are already disabled.")
            return
        required = [p for p in enabled if p.known_info and p.known_info.required]
        skip_msg = ""
        if required:
            names = ", ".join(self._plugin_label(p) for p in required)
            skip_msg = f"\n\nRequired plugins will be skipped: {names}"
        confirm = messagebox.askyesno(
            "Disable All Plugins",
            f"Disable all {len(enabled)} enabled plugin(s)?{skip_msg}")
        if not confirm:
            return
        try:
            count = self.app.plugin_manager.disable_all(skip_required=True)
            logger.info("Plugins", f"Disabled {count} plugins")
            messagebox.showinfo("Done", f"Disabled {count} plugin(s).")
            self._force_refresh()
        except Exception as e:
            logger.error("Plugins", f"Disable all failed: {e}")
            messagebox.showerror("Error", f"Failed to disable all plugins: {e}")

    def _open_folder(self):
        from src.utils.file_utils import open_folder
        settings = self.app.config_manager.settings
        if settings.plugins_path and settings.plugins_path.exists():
            open_folder(settings.plugins_path)

    def _toggle_friendly_names(self):
        settings = self.app.config_manager.settings
        settings.use_plugin_friendly_names = self._friendly_names_var.get()
        self.app.config_manager.save(settings)
        self._loaded = False
        self._refresh()

    def _toggle_show_descriptions(self):
        settings = self.app.config_manager.settings
        settings.show_plugin_descriptions = self._show_descriptions_var.get()
        self.app.config_manager.save(settings)
        self._loaded = False
        self._refresh()

    def _plugin_label(self, plugin) -> str:
        if self._friendly_names_var.get():
            return self._plugin_display_name(plugin)
        return plugin.filename

    @staticmethod
    def _base_plugin_filename(plugin) -> str:
        return plugin.filename.replace(".disabled", "")

    def _plugin_display_name(self, plugin) -> str:
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "plugin_name_overrides", {}) or {})
        base = self._base_plugin_filename(plugin)
        custom = overrides.get(base, "").strip()
        if custom:
            return custom
        if plugin.known_info:
            return plugin.display_name
        return base

    def _plugin_display_description(self, plugin) -> str:
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "plugin_description_overrides", {}) or {})
        base = self._base_plugin_filename(plugin)
        custom = overrides.get(base, "").strip()
        if custom:
            return custom
        return plugin.description

    def _has_custom_plugin_name(self, plugin) -> bool:
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "plugin_name_overrides", {}) or {})
        return bool(overrides.get(self._base_plugin_filename(plugin), "").strip())

    def _has_custom_plugin_description(self, plugin) -> bool:
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "plugin_description_overrides", {}) or {})
        return bool(overrides.get(self._base_plugin_filename(plugin), "").strip())

    def _bind_context_menu_recursive(self, widget, plugin):
        """Attach right-click plugin actions to row and all descendants."""
        try:
            widget.bind("<Button-3>",
                        lambda e, p=plugin: self._show_plugin_context_menu(e, p), add="+")
        except Exception:
            pass
        try:
            for child in widget.winfo_children():
                self._bind_context_menu_recursive(child, plugin)
        except Exception:
            pass

    def _show_plugin_context_menu(self, event, plugin):
        if not self._friendly_names_var.get():
            return None
        self._close_context_menu()

        menu = ctk.CTkToplevel(self)
        menu.withdraw()
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.configure(fg_color="#101427")

        frame = ctk.CTkFrame(
            menu,
            fg_color="#171a31",
            border_width=1,
            border_color="#2f3f6a",
            corner_radius=8,
        )
        frame.pack(fill="both", expand=True)

        self._add_context_item(
            frame,
            "Rename Plugin Name...",
            lambda p=plugin: self._rename_plugin_title(p),
        )
        self._add_context_item(
            frame,
            "Rename Plugin Description...",
            lambda p=plugin: self._rename_plugin_description(p),
        )

        if self._has_custom_plugin_name(plugin):
            self._add_context_item(
                frame,
                "Reset Plugin Name",
                lambda p=plugin: self._reset_single_custom_name(p),
            )

        if self._has_custom_plugin_description(plugin):
            self._add_context_item(
                frame,
                "Reset Plugin Description",
                lambda p=plugin: self._reset_single_custom_description(p),
            )

        menu.update_idletasks()
        menu.geometry(f"+{event.x_root + 4}+{event.y_root + 2}")
        menu.deiconify()
        try:
            menu.focus_force()
        except Exception:
            pass
        menu.bind("<FocusOut>", lambda _e: self._close_context_menu(), add="+")
        menu.bind("<Escape>", lambda _e: self._close_context_menu(), add="+")
        self._context_menu = menu
        return "break"

    def _add_context_item(self, parent, text: str, callback):
        btn = ctk.CTkButton(
            parent,
            text=text,
            anchor="w",
            width=220,
            height=30,
            corner_radius=0,
            fg_color="transparent",
            hover_color="#24375f",
            font=ctk.CTkFont(size=12),
            command=lambda cb=callback: self._invoke_context_action(cb),
        )
        btn.pack(fill="x")

    def _invoke_context_action(self, callback):
        self._close_context_menu()
        self.after(0, callback)

    def _close_context_menu(self):
        menu = self._context_menu
        self._context_menu = None
        if menu is None:
            return
        try:
            menu.destroy()
        except Exception:
            pass

    def _rename_plugin_title(self, plugin):
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "plugin_name_overrides", {}) or {})
        base = self._base_plugin_filename(plugin)
        default_name = plugin.display_name if plugin.known_info else base
        initial = overrides.get(base, default_name)

        new_name = self._show_text_entry_dialog(
            title="Rename Plugin Name",
            subtitle=f"Set a custom plugin title for:\n{base}\n\nLeave blank to restore default.",
            initial_value=initial,
        )
        if new_name is None:
            return

        cleaned = new_name.strip()
        if not cleaned or cleaned == default_name:
            overrides.pop(base, None)
        else:
            overrides[base] = cleaned

        settings.plugin_name_overrides = overrides
        self.app.config_manager.save(settings)
        self._loaded = False
        self._refresh()

    def _rename_plugin_description(self, plugin):
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "plugin_description_overrides", {}) or {})
        base = self._base_plugin_filename(plugin)
        default_desc = plugin.description
        initial = overrides.get(base, default_desc)

        new_desc = self._show_text_entry_dialog(
            title="Rename Plugin Description",
            subtitle=f"Set a custom plugin description for:\n{base}\n\nLeave blank to restore default.",
            initial_value=initial,
        )
        if new_desc is None:
            return

        cleaned = new_desc.strip()
        if not cleaned or cleaned == default_desc:
            overrides.pop(base, None)
        else:
            overrides[base] = cleaned

        settings.plugin_description_overrides = overrides
        self.app.config_manager.save(settings)
        self._loaded = False
        self._refresh()

    def _show_text_entry_dialog(self, title: str, subtitle: str, initial_value: str):
        result = {"value": None}
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.configure(fg_color="#0f1327")
        try:
            dialog.transient(self.winfo_toplevel())
        except Exception:
            pass
        try:
            dialog.attributes("-topmost", True)
        except Exception:
            pass

        shell = ctk.CTkFrame(dialog, fg_color="#151b36", corner_radius=10,
                             border_width=1, border_color="#304378")
        shell.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            shell, text=title, anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            shell, text=subtitle, anchor="w", justify="left",
            font=ctk.CTkFont(size=12), text_color="#b9bfd8",
        ).pack(fill="x", padx=14)

        entry = ctk.CTkEntry(shell, height=32)
        entry.pack(fill="x", padx=14, pady=(12, 12))
        entry.insert(0, initial_value or "")
        entry.select_range(0, "end")

        btn_row = ctk.CTkFrame(shell, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 12))

        def close_with(value=None):
            result["value"] = value
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        ctk.CTkButton(
            btn_row, text="Cancel", width=96, height=30,
            fg_color="#2f3557", hover_color="#3f476f",
            command=lambda: close_with(None),
        ).pack(side="right")

        ctk.CTkButton(
            btn_row, text="Save", width=96, height=30,
            fg_color="#1f538d", hover_color="#163b6a",
            command=lambda: close_with(entry.get()),
        ).pack(side="right", padx=(0, 8))

        dialog.bind("<Escape>", lambda _e: close_with(None))
        dialog.bind("<Return>", lambda _e: close_with(entry.get()))
        self._center_dialog(dialog, width=460, height=230)

        dialog.grab_set()
        entry.focus_set()
        self.wait_window(dialog)
        return result["value"]

    def _center_dialog(self, dialog, width: int, height: int):
        try:
            self.update_idletasks()
            x = self.winfo_rootx() + max(20, (self.winfo_width() - width) // 2)
            y = self.winfo_rooty() + max(20, (self.winfo_height() - height) // 2)
        except Exception:
            x, y = 200, 200
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def _reset_single_custom_name(self, plugin):
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "plugin_name_overrides", {}) or {})
        base = self._base_plugin_filename(plugin)
        if base in overrides:
            overrides.pop(base, None)
            settings.plugin_name_overrides = overrides
            self.app.config_manager.save(settings)
            self._loaded = False
            self._refresh()

    def _reset_single_custom_description(self, plugin):
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "plugin_description_overrides", {}) or {})
        base = self._base_plugin_filename(plugin)
        if base in overrides:
            overrides.pop(base, None)
            settings.plugin_description_overrides = overrides
            self.app.config_manager.save(settings)
            self._loaded = False
            self._refresh()

    def _reset_custom_names(self):
        settings = self.app.config_manager.settings
        overrides = dict(getattr(settings, "plugin_name_overrides", {}) or {})
        if not overrides:
            return
        confirm = messagebox.askyesno(
            "Reset Plugin Names",
            "Reset all custom plugin titles back to their defaults?",
        )
        if not confirm:
            return
        settings.plugin_name_overrides = {}
        self.app.config_manager.save(settings)
        self._loaded = False
        self._refresh()
