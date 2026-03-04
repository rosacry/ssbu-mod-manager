"""Plugins management page."""
import customtkinter as ctk
import tkinter as tk
import threading
from tkinter import filedialog, messagebox
from pathlib import Path
from src.ui import theme
from src.ui.base_page import BasePage
from src.models.plugin import PluginStatus
from src.core.content_importer import import_plugin_package
from src.core.desync_classifier import classify_plugin_filename
from src.core.runtime_guard import ContentOperationBlockedError
from src.utils.logger import logger

PLUGIN_RISK_BADGES = {
    "desync_vulnerable": ("DESYNC", theme.ACCENT),
    "conditionally_shared": ("CONDITIONAL", theme.WARNING),
    "unknown_needs_review": ("REVIEW", theme.WARNING_ALT),
    "safe_client_only": ("SAFE", theme.SUCCESS),
}


class PluginsPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._loaded = False
        self._context_menu = None
        self.app.bind("<Button-1>", self._close_context_menu_on_global_click, add="+")
        self._build_ui()

    def _build_ui(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(20, 8))

        title = ctk.CTkLabel(header_frame, text="Plugins",
                             font=ctk.CTkFont(size=theme.FONT_PAGE_TITLE, weight="bold"), anchor="w")
        title.pack(side="left")

        refresh_btn = ctk.CTkButton(header_frame, text="Refresh", width=100,
                                    command=self._force_refresh,
                                    corner_radius=8, height=34)
        refresh_btn.pack(side="right", padx=(5, 0))

        open_btn = ctk.CTkButton(header_frame, text="Open Folder", width=110,
                                 command=self._open_folder,
                                 fg_color=theme.BTN_NEUTRAL, hover_color=theme.HOVER_NEUTRAL,
                                 corner_radius=8, height=34)
        open_btn.pack(side="right", padx=(5, 0))

        import_btn = ctk.CTkButton(
            header_frame, text="Import", width=100,
            command=self._import_plugin_folder,
            fg_color=theme.PURPLE, hover_color=theme.HOVER_PURPLE,
            corner_radius=8, height=34,
        )
        import_btn.pack(side="right", padx=(5, 0))

        disable_all_btn = ctk.CTkButton(header_frame, text="Disable All", width=100,
                                        command=self._disable_all,
                                        fg_color=theme.DANGER_BUTTON, hover_color=theme.HOVER_DANGER_ALL,
                                        corner_radius=8, height=34)
        disable_all_btn.pack(side="right", padx=(5, 0))

        enable_all_btn = ctk.CTkButton(header_frame, text="Enable All", width=100,
                                       command=self._enable_all,
                                       fg_color=theme.SUCCESS_BUTTON, hover_color=theme.HOVER_SUCCESS_ALL,
                                       corner_radius=8, height=34)
        enable_all_btn.pack(side="right", padx=(5, 0))

        stable_mode_btn = ctk.CTkButton(
            header_frame,
            text="Stable Mode",
            width=110,
            command=self._apply_stable_mode,
            fg_color=theme.WARNING_BUTTON,
            hover_color=theme.HOVER_REVIEW,
            corner_radius=8,
            height=34,
        )
        stable_mode_btn.pack(side="right", padx=(5, 0))

        self.count_label = ctk.CTkLabel(self, text="",
                                        font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
                                        text_color=theme.TEXT_DIM, anchor="w")
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
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
        ).pack(side="left", padx=(0, 14))

        ctk.CTkCheckBox(
            name_controls,
            text="Show descriptions",
            variable=self._show_descriptions_var,
            command=self._toggle_show_descriptions,
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
        ).pack(side="left")

        self._reset_names_btn = ctk.CTkButton(
            name_controls,
            text="Reset Custom Names",
            width=150,
            height=28,
            corner_radius=6,
            fg_color=theme.BTN_TERTIARY,
            hover_color=theme.HOVER_TERTIARY,
            font=ctk.CTkFont(size=theme.FONT_BODY),
            command=self._reset_custom_names,
        )
        self._reset_names_btn.pack(side="right")

        self.plugin_list = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.plugin_list.pack(fill="both", expand=True, padx=25, pady=(0, 10))

        note_frame = ctk.CTkFrame(self, fg_color=theme.BG_WARNING_NOTE, corner_radius=8)
        note_frame.pack(fill="x", padx=30, pady=(5, 15))

        ctk.CTkLabel(
            note_frame,
            text="\u26a0  Disabling required plugins (like ARCropolis) will prevent mods from loading.",
            font=ctk.CTkFont(size=theme.FONT_BODY),
            text_color=theme.ACCENT,
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
        self.count_label.configure(text="Loading plugins...")

        def _load():
            plugins = self.app.plugin_manager.list_plugins()
            try:
                self.after(0, lambda: self._on_plugins_loaded(plugins))
            except Exception:
                pass

        threading.Thread(target=_load, daemon=True).start()

    def _on_plugins_loaded(self, plugins):
        self._loaded = True

        for widget in self.plugin_list.winfo_children():
            widget.destroy()

        active = sum(1 for p in plugins if p.status == PluginStatus.ENABLED)
        desync_plugins = 0
        for plugin in plugins:
            rep = classify_plugin_filename(self._base_plugin_filename(plugin))
            if rep.level.value == "desync_vulnerable":
                desync_plugins += 1
        summary = f"{active} active \u00b7 {len(plugins)} total plugins"
        if desync_plugins:
            summary += f" \u00b7 {desync_plugins} desync-vulnerable"
        self.count_label.configure(text=summary)

        if not plugins:
            ctk.CTkLabel(self.plugin_list,
                         text="No plugins found in the plugins directory.",
                         font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS), text_color=theme.TEXT_DISABLED,
                         ).pack(pady=40)
            return

        for plugin in plugins:
            self._render_plugin_row(plugin)

        logger.info("Plugins", f"Rendered {len(plugins)} plugins")

    def _render_plugin_row(self, plugin):
        is_enabled = plugin.status == PluginStatus.ENABLED
        is_required = bool(plugin.known_info and plugin.known_info.required)
        use_friendly_names = self._friendly_names_var.get()
        show_descriptions = self._show_descriptions_var.get()
        risk_report = classify_plugin_filename(self._base_plugin_filename(plugin))
        risk_text, risk_color = PLUGIN_RISK_BADGES.get(
            risk_report.level.value,
            ("REVIEW", theme.WARNING_ALT),
        )

        row_height = 44
        row = tk.Frame(self.plugin_list, bg=theme.BG_ROW, height=row_height)
        row.pack(fill="x", pady=1, padx=2)
        row.pack_propagate(False)

        accent_color = theme.PRIMARY if is_enabled else theme.ACCENT_STRIPE_DISABLED
        if is_required and is_enabled:
            accent_color = theme.ACCENT
        accent = tk.Frame(row, width=4, bg=accent_color)
        accent.pack(side="left", fill="y", padx=(3, 0), pady=4)

        switch = ctk.CTkSwitch(
            row, text="", width=42, height=20,
            command=lambda p=plugin: self._on_toggle(p),
            onvalue=True, offvalue=False,
            bg_color=theme.BG_ROW,
        )
        switch.pack(side="left", padx=(8, 6))
        if is_enabled:
            switch.select()
        else:
            switch.deselect()

        base_filename = self._base_plugin_filename(plugin)
        name = self._plugin_display_name(plugin) if use_friendly_names else plugin.filename
        display_text = name
        if use_friendly_names:
            if base_filename and base_filename != name:
                display_text += f"  ({base_filename})"
        if show_descriptions:
            desc = self._plugin_display_description(plugin).strip()
            if desc and desc != name:
                display_text += f"  \u2014  {desc}"

        name_color = theme.TEXT_BODY if is_enabled else theme.TEXT_VERY_DIM
        name_label = tk.Label(
            row,
            text=display_text,
            font=("Segoe UI", theme.FONT_BODY_MEDIUM),
            fg=name_color,
            bg=theme.BG_ROW,
            anchor="w",
        )
        name_label.pack(side="left", fill="x", expand=True, padx=(2, 8))

        tk.Label(
            row,
            text=risk_text,
            font=("Segoe UI", theme.FONT_TINY, "bold"),
            fg=risk_color if is_enabled else theme.TEXT_DISABLED_RISK,
            bg=theme.BG_ROW,
            anchor="e",
        ).pack(side="right", padx=(0, 10))

        if is_required:
            tk.Label(
                row,
                text="REQUIRED",
                font=("Segoe UI", theme.FONT_CAPTION, "bold"),
                fg=theme.ACCENT,
                bg=theme.BG_ROW,
                anchor="e",
            ).pack(side="right", padx=(0, 6))

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
        except ContentOperationBlockedError as e:
            logger.warn("Plugins", f"Toggle blocked: {e}")
            messagebox.showerror(e.info.title, e.info.message)
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
        except ContentOperationBlockedError as e:
            logger.warn("Plugins", f"Enable all blocked: {e}")
            messagebox.showerror(e.info.title, e.info.message)
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
        except ContentOperationBlockedError as e:
            logger.warn("Plugins", f"Disable all blocked: {e}")
            messagebox.showerror(e.info.title, e.info.message)
        except Exception as e:
            logger.error("Plugins", f"Disable all failed: {e}")
            messagebox.showerror("Error", f"Failed to disable all plugins: {e}")

    def _apply_stable_mode(self):
        plugins = self.app.plugin_manager.list_plugins()
        enabled = [p for p in plugins if p.status == PluginStatus.ENABLED]
        optional_enabled = [
            p for p in enabled
            if not (p.known_info and p.known_info.required)
        ]
        if not optional_enabled:
            messagebox.showinfo("Stable Mode", "Only core required plugins are currently enabled.")
            return
        confirm = messagebox.askyesno(
            "Enable Stable Cosmetic Runtime",
            "Disable all non-required Skyline plugins?\n\n"
            "This keeps the core mod loader active and turns off optional plugin features such as "
            "training tools, gameplay frameworks, CSS helpers, results-screen helpers, and other "
            "runtime tweaks that can destabilize cosmetic-heavy setups.\n\n"
            "Stable Mode keeps core required plugins plus safe cosmetic helpers like One Slot Effect active.\n\n"
            "Disabled plugins can be re-enabled later from this page.",
        )
        if not confirm:
            return
        try:
            disabled = self.app.plugin_manager.apply_cosmetic_stable_mode()
            logger.info("Plugins", f"Applied stable mode, disabled {len(disabled)} plugin(s)")
            if disabled:
                preview = ", ".join(disabled[:6])
                if len(disabled) > 6:
                    preview += f", and {len(disabled) - 6} more"
                messagebox.showinfo(
                    "Stable Mode Enabled",
                    f"Disabled {len(disabled)} non-required plugin(s):\n{preview}",
                )
            else:
                messagebox.showinfo("Stable Mode", "Only core required plugins remain enabled.")
            self._force_refresh()
        except ContentOperationBlockedError as e:
            logger.warn("Plugins", f"Stable mode blocked: {e}")
            messagebox.showerror(e.info.title, e.info.message)
        except Exception as e:
            logger.error("Plugins", f"Stable mode failed: {e}")
            messagebox.showerror("Error", f"Failed to apply stable mode: {e}")

    def _open_folder(self):
        from src.utils.file_utils import open_folder
        settings = self.app.config_manager.settings
        if settings.plugins_path and settings.plugins_path.exists():
            open_folder(settings.plugins_path)

    def _import_plugin_folder(self):
        settings = self.app.config_manager.settings
        if not settings.plugins_path:
            messagebox.showerror("Import Failed", "Plugins path is not configured in Settings.")
            return
        if not settings.eden_sdmc_path:
            messagebox.showerror("Import Failed", "SDMC path is not configured in Settings.")
            return

        folder = filedialog.askdirectory(title="Select Plugin Folder to Import")
        if not folder:
            return

        try:
            summary = import_plugin_package(
                Path(folder),
                settings.eden_sdmc_path,
                settings.plugins_path,
            )
            logger.info(
                "Plugins",
                f"Imported plugin package: {summary.files_copied} file(s), "
                f"{summary.plugin_files} plugin binary file(s), {summary.replaced_paths} replaced path(s)",
            )
            lines = [
                f"Copied {summary.files_copied} file(s).",
                f"Imported/updated {summary.plugin_files} plugin binary file(s).",
            ]
            if summary.replaced_paths:
                lines.append(f"Replaced {summary.replaced_paths} existing path(s).")
            if summary.warnings:
                lines.append("")
                lines.extend(summary.warnings[:5])
                if len(summary.warnings) > 5:
                    lines.append(f"...and {len(summary.warnings) - 5} more warning(s).")
            messagebox.showinfo("Import Complete", "\n".join(lines))
            self._force_refresh()
        except Exception as e:
            logger.error("Plugins", f"Import failed: {e}")
            messagebox.showerror("Import Failed", str(e))

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
        filename = plugin.filename
        suffix = ".disabled"
        if filename.lower().endswith(suffix):
            return filename[:-len(suffix)]
        return filename

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
        for seq in ("<ButtonRelease-3>", "<Button-2>", "<Control-Button-1>"):
            try:
                widget.bind(seq,
                            lambda e, p=plugin: self._show_plugin_context_menu(e, p), add="+")
            except Exception:
                pass
        try:
            for child in widget.winfo_children():
                self._bind_context_menu_recursive(child, plugin)
        except Exception:
            pass

    def _show_plugin_context_menu(self, event, plugin):
        self._close_context_menu()
        menu = ctk.CTkToplevel(self)
        menu.withdraw()
        menu.overrideredirect(True)
        menu.attributes("-topmost", True)
        menu.configure(fg_color=theme.BG_CONTEXT_MENU)

        frame = ctk.CTkFrame(
            menu,
            fg_color=theme.BG_CONTEXT_MENU_INNER,
            border_width=1,
            border_color=theme.BORDER_CONTEXT,
            corner_radius=8,
        )
        frame.pack(fill="both", expand=True)

        self._add_context_item(
            frame,
            "Rename Plugin Name",
            lambda p=plugin: self._rename_plugin_title(p),
        )
        self._add_context_item(
            frame,
            "Copy Online Risk Details",
            lambda p=plugin: self._copy_plugin_risk_details(p),
        )
        self._add_context_item(
            frame,
            "Rename Plugin Description",
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
        menu_w = max(frame.winfo_reqwidth(), 220)
        menu_h = max(frame.winfo_reqheight(), 30)
        x, y = self._clamp_popup_to_screen(event.x_root + 4, event.y_root + 2, menu_w, menu_h)
        menu.geometry(f"{menu_w}x{menu_h}+{x}+{y}")
        menu.deiconify()
        menu.lift()
        menu.bind("<Escape>", lambda _e: self._close_context_menu(), add="+")
        self._context_menu = menu
        return "break"

    def _close_context_menu_on_global_click(self, event):
        menu = self._context_menu
        if menu is None:
            return
        try:
            if not menu.winfo_exists():
                self._context_menu = None
                return
        except Exception:
            self._context_menu = None
            return

        w = getattr(event, "widget", None)
        while w is not None:
            if w == menu:
                return
            try:
                w = w.master
            except Exception:
                break
        self._close_context_menu()

    def _add_context_item(self, parent, text: str, callback):
        btn = ctk.CTkButton(
            parent,
            text=text,
            anchor="w",
            width=220,
            height=30,
            corner_radius=0,
            fg_color="transparent",
            hover_color=theme.HOVER_CONTEXT,
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            command=lambda cb=callback: self._invoke_context_action(cb),
        )
        btn.pack(fill="x")

    def _invoke_context_action(self, callback):
        self._close_context_menu()
        try:
            # Give context-menu teardown one frame so rename dialogs
            # never show partially during focus handoff on Windows.
            self.update_idletasks()
            self.after(theme.DELAY_CONTEXT_TEARDOWN, callback)
        except Exception:
            callback()

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
        dialog.withdraw()
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.configure(fg_color=theme.BG_DIALOG)

        shell = ctk.CTkFrame(
            dialog,
            fg_color=theme.BG_DIALOG_SHELL,
            corner_radius=10,
            border_width=1,
            border_color=theme.BORDER_DIALOG,
        )
        shell.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            shell,
            text=title,
            anchor="w",
            font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"),
        ).pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            shell,
            text=subtitle,
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
            text_color=theme.TEXT_SOFT,
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
            btn_row,
            text="Cancel",
            width=96,
            height=30,
            fg_color=theme.BTN_SECONDARY,
            hover_color=theme.HOVER_SECONDARY,
            command=lambda: close_with(None),
        ).pack(side="right")

        ctk.CTkButton(
            btn_row,
            text="Save",
            width=96,
            height=30,
            fg_color=theme.PRIMARY,
            hover_color=theme.HOVER_PRIMARY,
            command=lambda: close_with(entry.get()),
        ).pack(side="right", padx=(0, 8))

        dialog.bind("<Escape>", lambda _e: close_with(None))
        dialog.bind("<Return>", lambda _e: close_with(entry.get()))
        self._center_dialog(dialog, width=theme.WIDTH_DIALOG_TEXT_ENTRY, height=theme.HEIGHT_DIALOG_TEXT_ENTRY)
        self._present_modal_dialog(dialog, focus_widget=entry, animate_open=False)
        self.wait_window(dialog)
        return result["value"]

    def _copy_plugin_risk_details(self, plugin):
        base = self._base_plugin_filename(plugin)
        report = classify_plugin_filename(base)
        badge_text, _color = PLUGIN_RISK_BADGES.get(report.level.value, ("REVIEW", theme.WARNING_ALT))
        lines = [
            f"Plugin: {base}",
            f"Online Risk: {report.level.value} ({badge_text})",
            f"Reason: {report.code}: {report.reason}",
        ]
        if report.evidence_url:
            lines.append(f"Source: {report.evidence_url}")
        text = "\n".join(lines)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Copied", "Online risk details copied to clipboard.")
        except Exception:
            messagebox.showerror("Error", "Failed to copy risk details.")

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
