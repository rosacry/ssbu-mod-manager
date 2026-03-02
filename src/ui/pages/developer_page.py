"""Developer tools page - log viewer and diagnostics."""
import customtkinter as ctk
import tkinter as tk
from src.ui.base_page import BasePage
from src.ui import theme
from src.utils.logger import logger


class DeveloperPage(BasePage):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._listener_active = False
        self._build_ui()

    def destroy(self):
        """Clean up listener before destruction to avoid TclError."""
        if self._listener_active:
            logger.remove_listener(self._on_log)
            self._listener_active = False
        super().destroy()

    def _build_ui(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(25, 10))

        title = ctk.CTkLabel(header_frame, text="Developer",
                             font=ctk.CTkFont(size=theme.FONT_PAGE_TITLE, weight="bold"), anchor="w")
        title.pack(side="left")

        clear_btn = ctk.CTkButton(header_frame, text="Clear Logs", width=110,
                                  command=self._clear_logs,
                                  fg_color=theme.DANGER, hover_color=theme.HOVER_DANGER,
                                  corner_radius=8, height=34)
        clear_btn.pack(side="right", padx=(5, 0))

        copy_btn = ctk.CTkButton(header_frame, text="Copy All", width=100,
                                 command=self._copy_logs,
                                 fg_color=theme.BTN_NEUTRAL, hover_color=theme.HOVER_NEUTRAL,
                                 corner_radius=8, height=34)
        copy_btn.pack(side="right")

        toggle_frame = ctk.CTkFrame(self, fg_color=theme.BG_CARD_DEEP, corner_radius=12)
        toggle_frame.pack(fill="x", padx=30, pady=(0, 10))

        toggle_inner = ctk.CTkFrame(toggle_frame, fg_color="transparent")
        toggle_inner.pack(fill="x", padx=15, pady=12)

        self.debug_var = ctk.BooleanVar(value=logger.enabled)
        debug_switch = ctk.CTkSwitch(
            toggle_inner, text="Enable Developer Mode (logs all operations)",
            variable=self.debug_var, command=self._toggle_debug,
            font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS),
        )
        debug_switch.pack(side="left")

        self.copy_feedback = ctk.CTkLabel(
            toggle_inner, text="",
            font=ctk.CTkFont(size=theme.FONT_BODY), text_color=theme.SUCCESS,
        )
        self.copy_feedback.pack(side="right", padx=15)

        log_header = ctk.CTkLabel(self, text="Application Logs",
                                  font=ctk.CTkFont(size=theme.FONT_SECTION_HEADING, weight="bold"), anchor="w")
        log_header.pack(fill="x", padx=30, pady=(5, 5))

        log_frame = ctk.CTkFrame(self, fg_color="transparent")
        log_frame.pack(fill="both", expand=True, padx=30, pady=(0, 15))

        self.log_text = tk.Text(
            log_frame, bg=theme.BG_SIDEBAR, fg=theme.TEXT_LOG, font=("Consolas", theme.FONT_CAPTION),
            relief="flat", bd=0, highlightthickness=0,
            wrap="word", insertbackground=theme.TEXT_LOG,
            selectbackground=theme.PRIMARY, selectforeground="white",
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ctk.CTkScrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.tag_config("INFO", foreground=theme.TEXT_HINT)
        self.log_text.tag_config("DEBUG", foreground=theme.INFO)
        self.log_text.tag_config("WARN", foreground=theme.WARNING_MEDIUM)
        self.log_text.tag_config("ERROR", foreground=theme.ACCENT)

        self.log_text.bind("<Key>", self._block_input)
        self.log_text.bind("<Control-a>", self._select_all)
        self.log_text.bind("<Control-A>", self._select_all)

    def _block_input(self, event):
        """Block typing but allow navigation, selection, and copy."""
        allowed_keys = {"Left", "Right", "Up", "Down", "Home", "End",
                        "Prior", "Next", "Shift_L", "Shift_R",
                        "Control_L", "Control_R"}
        if event.keysym in allowed_keys:
            return  # Allow navigation
        if event.state & 0x4 and event.keysym.lower() in ("c", "a"):
            return  # Allow Ctrl+C, Ctrl+A
        return "break"  # Block everything else

    def _select_all(self, event=None):
        self.log_text.tag_add("sel", "1.0", tk.END)
        return "break"

    def on_show(self):
        self.debug_var.set(logger.enabled)
        self._update_toggle_status()
        self._load_existing_logs()
        # Start listening AFTER bulk-loading existing logs to avoid
        # duplicates from after(0) callbacks racing with _load_existing_logs.
        if not self._listener_active:
            logger.add_listener(self._on_log)
            self._listener_active = True

    def on_hide(self):
        """Stop listening when the page is hidden to avoid wasted work."""
        if self._listener_active:
            logger.remove_listener(self._on_log)
            self._listener_active = False

    def _toggle_debug(self):
        enabled = self.debug_var.get()
        logger.enabled = enabled
        settings = self.app.config_manager.settings
        settings.debug_mode = enabled
        self.app.config_manager.save(settings)
        self._update_toggle_status()

    def _update_toggle_status(self):
        return

    def _load_existing_logs(self):
        self.log_text.delete("1.0", tk.END)
        for entry in logger.get_logs():
            self._insert_log_entry(entry)
        self.log_text.see(tk.END)

    def _on_log(self, entry):
        """Called when a new log entry is added (may be from background thread)."""
        try:
            self.after(0, lambda e=entry: self._append_log_entry(e))
        except Exception:
            pass

    def _append_log_entry(self, entry):
        """Insert a log entry on the main thread and scroll to end."""
        try:
            self._insert_log_entry(entry)
            self.log_text.see(tk.END)
        except Exception:
            pass

    def _insert_log_entry(self, entry):
        tag = "INFO"
        if "[ERROR]" in entry:
            tag = "ERROR"
        elif "[WARN]" in entry:
            tag = "WARN"
        elif "[DEBUG]" in entry:
            tag = "DEBUG"
        self.log_text.insert(tk.END, entry + "\n", tag)

    def _clear_logs(self):
        logger.clear()
        self.log_text.delete("1.0", tk.END)

    def _copy_logs(self):
        all_text = self.log_text.get("1.0", tk.END).strip()
        if not all_text:
            self.copy_feedback.configure(text="No logs to copy")
            self.after(theme.DELAY_COPY_TOAST, lambda: self.copy_feedback.configure(text=""))
            return

        try:
            self.clipboard_clear()
            self.clipboard_append(all_text)
            self.update()  # Force clipboard update
            self.copy_feedback.configure(text="Copied!")
            self.after(theme.DELAY_COPY_TOAST, lambda: self.copy_feedback.configure(text=""))
            logger.info("Developer", f"Copied {len(all_text)} chars to clipboard")
        except Exception as e:
            self.copy_feedback.configure(text="Copy failed")
            self.after(theme.DELAY_COPY_TOAST, lambda: self.copy_feedback.configure(text=""))
            logger.error("Developer", f"Clipboard copy failed: {e}")
