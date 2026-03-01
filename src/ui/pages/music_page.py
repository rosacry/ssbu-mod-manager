"""Music management page - 3-column layout with audio preview."""
import threading
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from src.core.spotify_manager import (
    SPOTIFY_REDIRECT_URI_DOC,
)
from src.ui.base_page import BasePage
from src.constants import VANILLA_STAGES, COMPETITIVE_STAGES
from src.utils.logger import logger
from src.utils.audio_player import audio_player
from src.utils.action_history import action_history, Action


class MusicPage(BasePage):
    _AUTO_SCAN_DELAY_MS = 260
    _SPINNER_FRAME_INTERVAL_MS = 100
    _FILTER_DEBOUNCE_MS = 120
    _PLAYBACK_STATUS_CLEAR_MS = 3000
    _PLAYBACK_ERROR_CLEAR_MS = 5000
    _PLAYBACK_STOPPED_CLEAR_MS = 2000
    _PLAYBACK_POLL_MS = 500
    _SEEK_UPDATE_MS = 500
    _PLAY_CLICK_DELAY_MS = 50
    _ZERO_DELAY_MS = 0
    _MAX_PERCENT = 100.0
    _MIN_VOLUME = 0.0
    _MAX_VOLUME = 1.0
    _VOLUME_EPSILON = 0.01
    _SECONDS_PER_MINUTE = 60
    _DEFAULT_VOLUME = 0.7
    _MENU_STAGE_ID = "ui_stage_id_menu"
    _MENU_STAGE_PREFIX = "[Menu] "
    _ZERO_TIME_TEXT = "0:00"
    _SPINNER_FRAMES = ["|", "/", "-", "\\"]
    _QUEUE_EMPTY_TEXT = "Library player idle"

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._selected_stage = None
        self._loaded = False
        self._scan_in_progress = False
        self._pending_rescan = False
        self._pending_full_rescan = False
        self._all_tracks = []
        self._track_id_map = {}
        self._stage_ids = []
        self._is_playing = False
        self._spinner_index = 0
        self._spinner_active = False
        self._track_filter_after_id = None
        self._stage_filter_after_id = None
        self._deferred_ui_apply = False
        self._scan_generation = 0
        self._auto_scan_after_id = None
        self._scan_cancel_event = None
        self._auto_scan_delay_ms = self._AUTO_SCAN_DELAY_MS
        self._pending_volume_value = self._DEFAULT_VOLUME
        self._track_data_revision = 0
        self._last_track_render_signature = None
        self._spotify_dialog = None
        self._queue_track_ids = []
        self._queue_index = -1
        self._queue_name = ""
        self._manual_stop_requested = False
        self._suppress_track_selection_autoplay = False
        self._build_ui()

    def _build_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(20, 5))

        title = ctk.CTkLabel(header_frame, text="Music",
                             font=ctk.CTkFont(size=24, weight="bold"), anchor="w")
        title.pack(side="left")

        scan_btn = ctk.CTkButton(header_frame, text="Rescan Tracks", width=130,
                                 command=self._force_scan,
                                 fg_color="#555555", hover_color="#444444",
                                 corner_radius=8, height=34)
        scan_btn.pack(side="right")

        # Summary row
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.pack(fill="x", padx=30, pady=(2, 5))

        self.summary_label = ctk.CTkLabel(
            info_frame, text="Configure which music tracks play on which stages.",
            font=ctk.CTkFont(size=12), text_color="#999999", anchor="w",
        )
        self.summary_label.pack(side="left")

        self.loading_label = ctk.CTkLabel(
            info_frame, text="",
            font=ctk.CTkFont(size=12), text_color="#888888",
        )
        self.loading_label.pack(side="right")

        # Main 3-column layout using PanedWindow for resizable splitters
        content = tk.PanedWindow(
            self, orient=tk.HORIZONTAL, sashwidth=6,
            bg="#12121e", sashpad=0, opaqueresize=True,
            borderwidth=0, relief="flat",
        )
        content.pack(fill="both", expand=True, padx=30, pady=(0, 10))
        self._paned = content  # store for sash positioning

        # === LEFT COLUMN: Stage list ===
        left = ctk.CTkFrame(content, width=420, fg_color="#242438", corner_radius=10)
        content.add(left, minsize=280, stretch="never", width=420)

        ctk.CTkLabel(left, text="Stages",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=10, pady=(10, 5))

        self.stage_search_var = tk.StringVar()
        self.stage_search_var.trace("w", self._on_stage_filter_input)
        ctk.CTkEntry(left, placeholder_text="Search stages...",
                     textvariable=self.stage_search_var, height=30,
                     corner_radius=6).pack(fill="x", padx=10, pady=5)

        # Competitive-only filter
        self.competitive_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            left, text="Competitive only", variable=self.competitive_var,
            command=self._schedule_stage_filter, font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12, pady=(2, 4))

        # Stage list with scrollbar
        stage_list_frame = ctk.CTkFrame(left, fg_color="transparent")
        stage_list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        self.stage_listbox = tk.Listbox(stage_list_frame, bg="#1e1e2e", fg="#cccccc",
                                        selectbackground="#1f538d",
                                        selectforeground="white",
                                        font=("Segoe UI", 10),
                                        relief="flat", bd=0, highlightthickness=0,
                                        activestyle="none", cursor="arrow")
        stage_scroll = ctk.CTkScrollbar(stage_list_frame, command=self.stage_listbox.yview)
        self.stage_listbox.configure(yscrollcommand=stage_scroll.set)
        self.stage_listbox.pack(side="left", fill="both", expand=True)
        stage_scroll.pack(side="right", fill="y")
        self.stage_listbox.bind("<<ListboxSelect>>", self._on_stage_select)

        # Bulk buttons
        bulk_frame = ctk.CTkFrame(left, fg_color="transparent")
        bulk_frame.pack(fill="x", padx=10, pady=(0, 5))

        ctk.CTkButton(bulk_frame, text="All -> All Legacy Stages",
                      command=self._assign_all_to_all,
                      fg_color="#2fa572", hover_color="#106a43",
                      font=ctk.CTkFont(size=11), height=28, corner_radius=6,
                      ).pack(fill="x", pady=1)

        ctk.CTkButton(bulk_frame, text="Clear All Legacy Stages",
                      command=self._clear_all_stages,
                      fg_color="#b02a2a", hover_color="#8a1f1f",
                      font=ctk.CTkFont(size=11), height=28, corner_radius=6,
                      ).pack(fill="x", pady=1)

        # Exclude vanilla option in stage column
        self.exclude_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            left, text="Exclude vanilla tracks", variable=self.exclude_var,
            command=self._on_exclude_change, font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=12, pady=(4, 10))

        # === MIDDLE COLUMN: Stage music workflows ===
        middle = ctk.CTkFrame(content, fg_color="#242438", corner_radius=10)
        content.add(middle, minsize=200, stretch="always", width=300)

        playlist_header = ctk.CTkFrame(middle, fg_color="transparent")
        playlist_header.pack(fill="x", padx=12, pady=(10, 5))

        self.playlist_label = ctk.CTkLabel(playlist_header, text="Select a stage",
                                           font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
        self.playlist_label.pack(side="left")

        self.playlist_count = ctk.CTkLabel(playlist_header, text="",
                                            font=ctk.CTkFont(size=11), text_color="#888888")
        self.playlist_count.pack(side="right")

        self.stage_tabs = ctk.CTkTabview(middle, fg_color="#242438")
        self.stage_tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        safe_tab = self.stage_tabs.add("Safe Slots")
        playlist_tab = self.stage_tabs.add("Legacy Playlist")

        self.safe_slot_note = ctk.CTkLabel(
            safe_tab,
            text=(
                "Replace an existing discovered slot instead of adding a new one. "
                "This is the safer community workflow for online play."
            ),
            font=ctk.CTkFont(size=11),
            text_color="#b9bfd8",
            justify="left",
            wraplength=320,
            anchor="w",
        )
        self.safe_slot_note.pack(fill="x", padx=10, pady=(10, 6))

        self.safe_slot_source = ctk.CTkLabel(
            safe_tab,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="#777799",
            anchor="w",
        )
        self.safe_slot_source.pack(fill="x", padx=10, pady=(0, 6))

        self.safe_slot_frame = ctk.CTkScrollableFrame(safe_tab, fg_color="transparent")
        self.safe_slot_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        safe_btns = ctk.CTkFrame(safe_tab, fg_color="transparent")
        safe_btns.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(
            safe_btns,
            text="Clear Safe Replacements",
            width=150,
            fg_color="#b02a2a",
            hover_color="#8a1f1f",
            command=self._clear_stage_replacements,
            height=28,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
        ).pack(side="right")

        ctk.CTkLabel(
            playlist_tab,
            text=(
                "Legacy playlist editing can append extra stage entries and modify the "
                "stage database. Use this only when you intentionally want that behavior."
            ),
            font=ctk.CTkFont(size=11),
            text_color="#d0b071",
            justify="left",
            wraplength=320,
            anchor="w",
        ).pack(fill="x", padx=10, pady=(10, 6))

        self.playlist_frame = ctk.CTkScrollableFrame(playlist_tab, fg_color="transparent")
        self.playlist_frame.pack(fill="both", expand=True, padx=5, pady=5)

        playlist_btns = ctk.CTkFrame(playlist_tab, fg_color="transparent")
        playlist_btns.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkButton(playlist_btns, text="Clear Stage", width=100,
                      fg_color="#b02a2a", hover_color="#8a1f1f",
                      command=self._clear_stage, height=28, corner_radius=6,
                      font=ctk.CTkFont(size=11),
                      ).pack(side="right")

        ctk.CTkButton(playlist_btns, text="Add All", width=80,
                      fg_color="#2fa572", hover_color="#106a43",
                      command=self._add_all_to_stage, height=28, corner_radius=6,
                      font=ctk.CTkFont(size=11),
                      ).pack(side="right", padx=5)

        # === RIGHT COLUMN: Available tracks ===
        right = ctk.CTkFrame(content, width=550, fg_color="#242438", corner_radius=10)
        content.add(right, minsize=350, stretch="never", width=550)

        avail_header = ctk.CTkFrame(right, fg_color="transparent")
        avail_header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(avail_header, text="Available Tracks",
                     font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(side="left")

        self.track_count_label = ctk.CTkLabel(avail_header, text="",
                                              font=ctk.CTkFont(size=11), text_color="#888888")
        self.track_count_label.pack(side="right")

        self.track_search_var = tk.StringVar()
        self.track_search_var.trace("w", self._on_track_filter_input)
        ctk.CTkEntry(right, placeholder_text="Search tracks...",
                     textvariable=self.track_search_var, height=30,
                     corner_radius=6).pack(fill="x", padx=10, pady=5)

        track_filter_row = ctk.CTkFrame(right, fg_color="transparent")
        track_filter_row.pack(fill="x", padx=10, pady=(0, 4))

        self.favorites_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            track_filter_row,
            text="Favorites only",
            variable=self.favorites_only_var,
            command=self._render_available_tracks,
            font=ctk.CTkFont(size=11),
        ).pack(side="left")

        ctk.CTkLabel(
            track_filter_row,
            text="Ctrl-click to multi-select",
            font=ctk.CTkFont(size=10),
            text_color="#666688",
        ).pack(side="right")

        # Available tracks list
        track_frame = ctk.CTkFrame(right, fg_color="transparent")
        track_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        self.track_listbox = tk.Listbox(track_frame, bg="#1e1e2e", fg="#cccccc",
                                         selectbackground="#1f538d",
                                         selectforeground="white",
                                         font=("Segoe UI", 10),
                                         relief="flat", bd=0, highlightthickness=0,
                                         activestyle="none", cursor="arrow",
                                         selectmode=tk.EXTENDED,
                                         exportselection=False)
        track_scroll = ctk.CTkScrollbar(track_frame, command=self.track_listbox.yview)
        self.track_listbox.configure(yscrollcommand=track_scroll.set)
        self.track_listbox.pack(side="left", fill="both", expand=True)
        track_scroll.pack(side="right", fill="y")

        # Double-click to add
        self.track_listbox.bind("<Double-1>", lambda e: self._add_selected_track())
        # Single-click to auto-play when already playing
        self.track_listbox.bind("<<ListboxSelect>>", self._on_track_selection_changed)

        # Audio player controls: play/stop toggle + volume, right-aligned near track list
        player_frame = ctk.CTkFrame(right, fg_color="#1e1e30", corner_radius=6)
        player_frame.pack(fill="x", padx=10, pady=(2, 4))

        # Keep now-playing status above controls so it remains visible.
        self.player_status = ctk.CTkLabel(
            player_frame, text="",
            font=ctk.CTkFont(size=10), text_color="#2fa572",
            anchor="w",
        )
        self.player_status.pack(fill="x", padx=8, pady=(5, 0))

        self.queue_status = ctk.CTkLabel(
            player_frame,
            text=self._QUEUE_EMPTY_TEXT,
            font=ctk.CTkFont(size=10),
            text_color="#888888",
            anchor="w",
        )
        self.queue_status.pack(fill="x", padx=8, pady=(2, 0))

        player_inner = ctk.CTkFrame(player_frame, fg_color="transparent")
        player_inner.pack(fill="x", padx=8, pady=5)

        # Single play/stop toggle button
        self._is_playing = False
        self.play_toggle_btn = ctk.CTkButton(
            player_inner, text="Play", width=80, height=28,
            fg_color="#2fa572", hover_color="#106a43",
            font=ctk.CTkFont(size=11), corner_radius=6,
            command=self._toggle_playback,
        )
        self.play_toggle_btn.pack(side="left", padx=(0, 6))

        # Volume slider
        vol_label = ctk.CTkLabel(player_inner, text="Vol",
                                 font=ctk.CTkFont(size=10), text_color="#888888")
        vol_label.pack(side="left", padx=(0, 3))
        self.volume_slider = ctk.CTkSlider(
            player_inner, from_=0, to=100, width=90, height=14,
            command=self._on_volume_change,
        )
        self.volume_slider.set(int(self._DEFAULT_VOLUME * self._MAX_PERCENT))
        self.volume_slider.pack(side="left", padx=(0, 6))

        # Seek timeline
        self.seek_label = ctk.CTkLabel(player_inner, text=self._ZERO_TIME_TEXT,
                                       font=ctk.CTkFont(size=10), text_color="#555555")
        self.seek_label.pack(side="left", padx=(4, 2))
        self._seek_dragging = False
        self.seek_slider = ctk.CTkSlider(
            player_inner, from_=0, to=100, width=120, height=14,
            command=self._on_seek_drag,
            fg_color="#2a2a4a", progress_color="#1f538d",
            button_color="#4488cc", button_hover_color="#5599dd",
        )
        self.seek_slider.set(self._ZERO_DELAY_MS)
        self.seek_slider.pack(side="left", padx=(0, 2))
        self.seek_slider.bind("<ButtonPress-1>", lambda e: setattr(self, '_seek_dragging', True))
        self.seek_slider.bind("<ButtonRelease-1>", self._on_seek_release)
        self.seek_duration_label = ctk.CTkLabel(player_inner, text=self._ZERO_TIME_TEXT,
                                                 font=ctk.CTkFont(size=10), text_color="#555555")
        self.seek_duration_label.pack(side="left", padx=(2, 6))

        queue_controls = ctk.CTkFrame(player_frame, fg_color="transparent")
        queue_controls.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkButton(
            queue_controls,
            text="Play Filtered",
            width=110,
            height=26,
            fg_color="#1f538d",
            hover_color="#163b6a",
            font=ctk.CTkFont(size=11),
            command=lambda: self._start_queue_from_source("filtered"),
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            queue_controls,
            text="Play Favorites",
            width=110,
            height=26,
            fg_color="#3f4f76",
            hover_color="#4f6088",
            font=ctk.CTkFont(size=11),
            command=lambda: self._start_queue_from_source("favorites"),
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            queue_controls,
            text="Prev",
            width=60,
            height=26,
            fg_color="#2f3557",
            hover_color="#3f476f",
            font=ctk.CTkFont(size=11),
            command=lambda: self._step_queue(-1),
        ).pack(side="right")
        ctk.CTkButton(
            queue_controls,
            text="Next",
            width=60,
            height=26,
            fg_color="#2f3557",
            hover_color="#3f476f",
            font=ctk.CTkFont(size=11),
            command=lambda: self._step_queue(1),
        ).pack(side="right", padx=(0, 4))

        # Add track button
        add_btn_frame = ctk.CTkFrame(right, fg_color="transparent")
        add_btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(add_btn_frame, text="+ Add Selected Tracks",
                      command=self._add_selected_track,
                      fg_color="#2fa572", hover_color="#106a43",
                      height=30, corner_radius=6, font=ctk.CTkFont(size=12),
                      ).pack(fill="x", pady=(0, 4))

        self.favorite_selected_btn = ctk.CTkButton(
            add_btn_frame,
            text="Favorite Selected",
            command=self._toggle_selected_favorites,
            fg_color="#b08a2a",
            hover_color="#8a6b1f",
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
            state="disabled",
        )
        self.favorite_selected_btn.pack(fill="x", pady=(0, 4))

        self.spotify_export_btn = ctk.CTkButton(
            add_btn_frame,
            text="Spotify Export (Experimental)...",
            command=self._open_spotify_export_dialog,
            fg_color="#1f538d",
            hover_color="#163b6a",
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
        )
        self.spotify_export_btn.pack(fill="x")

    def on_show(self):
        if not self._loaded:
            if not self._scan_in_progress:
                self._schedule_auto_scan()
        else:
            if self._deferred_ui_apply:
                self._apply_loaded_tracks_ui()
            else:
                self._update_summary()
                self._render_available_tracks()
                self._populate_stages()
                # Re-render the playlist if a stage was previously selected
                if self._selected_stage:
                    self._render_playlist()
                    self._render_stage_slots()
        # Sync play button state with actual audio player
        self._refresh_spotify_button_state()
        self._sync_play_state()

    def on_hide(self):
        """Clean up playlist widgets for smoother page transitions."""
        self._cancel_auto_scan()
        if self._scan_in_progress and self._scan_cancel_event is not None:
            try:
                self._scan_cancel_event.set()
                logger.info("Music", "Cancelling background track scan while page is hidden")
            except Exception:
                pass
        for attr in ("_track_filter_after_id", "_stage_filter_after_id"):
            aid = getattr(self, attr, None)
            if aid:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
        for w in self.playlist_frame.winfo_children():
            w.destroy()
        for w in self.safe_slot_frame.winfo_children():
            w.destroy()

    def discard_changes(self):
        self.app.music_manager.reload_saved_assignments()
        if self._loaded:
            self.exclude_var.set(self.app.music_manager.exclude_vanilla)
            self._update_summary()
            self._populate_stages()
            if self._selected_stage:
                self._render_playlist()
                self._render_stage_slots()

    def _schedule_auto_scan(self):
        self._cancel_auto_scan()

        def _run():
            self._auto_scan_after_id = None
            if self._loaded or self._scan_in_progress:
                return
            if not self._is_music_page_active():
                return
            self._scan_tracks(full_scan=False)

        self._auto_scan_after_id = self.after(int(self._auto_scan_delay_ms), _run)

    def _cancel_auto_scan(self):
        if self._auto_scan_after_id:
            try:
                self.after_cancel(self._auto_scan_after_id)
            except Exception:
                pass
            self._auto_scan_after_id = None

    def _sync_play_state(self):
        """Keep play toggle button in sync with actual audio player state."""
        if audio_player.is_playing:
            if not self._is_playing:
                self._is_playing = True
                self.play_toggle_btn.configure(
                    text="Stop", fg_color="#b02a2a", hover_color="#8a1f1f")
        else:
            if self._is_playing:
                self._is_playing = False
                self.play_toggle_btn.configure(
                    text="Play", fg_color="#2fa572", hover_color="#106a43")
                self.player_status.configure(text="")

    def _start_spinner(self, text: str = "Loading"):
        """Start an animated loading spinner in the loading label."""
        self._spinner_active = True
        self._spinner_index = 0
        self._spinner_text = text
        self._animate_spinner()

    def _stop_spinner(self):
        """Stop the loading spinner."""
        self._spinner_active = False
        self.loading_label.configure(text="")

    def _animate_spinner(self):
        """Animate the spinner by cycling through braille frames."""
        if not self._spinner_active:
            return
        frame = self._SPINNER_FRAMES[self._spinner_index % len(self._SPINNER_FRAMES)]
        self.loading_label.configure(text=f"{frame} {self._spinner_text}...")
        self._spinner_index += 1
        self.after(self._SPINNER_FRAME_INTERVAL_MS, self._animate_spinner)

    def _force_scan(self):
        self._cancel_auto_scan()
        if self._scan_in_progress:
            self._pending_rescan = True
            self._pending_full_rescan = True
            self.loading_label.configure(text="Rescan queued...")
            return
        self._loaded = False
        self._scan_tracks(full_scan=True)

    def _scan_tracks(self, full_scan: bool = False):
        self._cancel_auto_scan()
        if self._scan_in_progress:
            return
        settings = self.app.config_manager.settings
        if not settings.mods_path or not settings.mods_path.exists():
            self.track_count_label.configure(text="No mods path configured")
            return

        self._scan_in_progress = True
        self._pending_rescan = False
        self._pending_full_rescan = False
        self._scan_generation += 1
        current_gen = self._scan_generation
        self._scan_cancel_event = threading.Event()
        cancel_event = self._scan_cancel_event
        self._start_spinner("Scanning tracks")
        logger.info("Music", f"Scanning for tracks in: {settings.mods_path}")

        mods_path = settings.mods_path

        def scan():
            try:
                tracks = self.app.music_manager.discover_tracks(
                    mods_path,
                    cancel_event=cancel_event,
                    parse_binary_msbt=full_scan,
                    generate_msbt_overlays=full_scan,
                )
                if cancel_event.is_set():
                    logger.info("Music", "Track scan cancelled")
                    return
                logger.info("Music", f"Found {len(tracks)} tracks")
                if not self.app.shutting_down:
                    try:
                        self.app.after(
                            self._ZERO_DELAY_MS,
                            lambda t=tracks, gen=current_gen: self._on_tracks_loaded(t, gen),
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.error("Music", f"Track scan failed: {e}")
                if not self.app.shutting_down:
                    try:
                        self.app.after(
                            self._ZERO_DELAY_MS,
                            lambda err=str(e), gen=current_gen: self._on_scan_error(err, gen),
                        )
                    except Exception:
                        pass
            finally:
                if not self.app.shutting_down:
                    try:
                        self.app.after(
                            self._ZERO_DELAY_MS,
                            lambda gen=current_gen: self._on_scan_finished(gen),
                        )
                    except Exception:
                        pass

        threading.Thread(target=scan, daemon=True).start()

    def _on_scan_finished(self, scan_gen: int | None = None):
        """Mark scan complete and run queued rescan requests."""
        if scan_gen is not None and scan_gen != self._scan_generation:
            return
        self._scan_in_progress = False
        self._scan_cancel_event = None
        if self._spinner_active and not self._loaded and not self._pending_rescan:
            self._stop_spinner()
            if self._is_music_page_active():
                self.track_count_label.configure(text="Scan cancelled")
        if self._pending_rescan:
            run_full_rescan = bool(self._pending_full_rescan)
            self._pending_rescan = False
            self._pending_full_rescan = False
            self._loaded = False
            self._scan_tracks(full_scan=run_full_rescan)

    def _on_scan_error(self, error_msg: str, scan_gen: int | None = None):
        """Handle track scan failure on the main thread."""
        if scan_gen is not None and scan_gen != self._scan_generation:
            return
        self._stop_spinner()
        self.track_count_label.configure(text="Scan failed")
        if self._is_music_page_active():
            from tkinter import messagebox
            messagebox.showerror("Scan Error", f"Failed to scan tracks: {error_msg}")
        else:
            logger.warn("Music", f"Track scan failed while page hidden: {error_msg}")

    def _on_tracks_loaded(self, tracks, scan_gen: int | None = None):
        if scan_gen is not None and scan_gen != self._scan_generation:
            return
        self._loaded = True
        self._all_tracks = tracks
        self._track_data_revision += 1
        self._last_track_render_signature = None
        try:
            self._stop_spinner()
            self.track_count_label.configure(text=f"{len(tracks)} tracks")
            if self._is_music_page_active():
                self._apply_loaded_tracks_ui()
            else:
                # Avoid heavy listbox repaints on hidden tabs; render when the
                # user navigates back to Music.
                self._deferred_ui_apply = True
                logger.info("Music", "Track scan finished in background; deferred UI render until Music is visible")

            # Invalidate the dashboard conflict cache because
            # generate_msbt_overlays() may have changed _MergedResources
            # (cleaned up stale copies, added/removed files).
            if "dashboard" in self.app.main_window.pages:
                dash = self.app.main_window.pages["dashboard"]
                dash._conflict_cache = None
        except Exception as e:
            logger.warn("Music", f"Track scan finished but UI update was deferred: {e}")

    def _is_music_page_active(self) -> bool:
        try:
            return getattr(self.app.main_window, "current_page", None) == "music"
        except Exception:
            return False

    def _apply_loaded_tracks_ui(self):
        """Apply loaded track data to visible UI widgets."""
        self._deferred_ui_apply = False
        self.track_count_label.configure(text=f"{len(self._all_tracks)} tracks")
        self.exclude_var.set(self.app.music_manager.exclude_vanilla)
        self._update_summary()
        self._render_available_tracks()
        self._populate_stages()
        if self._selected_stage:
            self._render_playlist()
            self._render_stage_slots()
        self._update_track_selection_state()
        self._refresh_spotify_button_state()

    def _update_summary(self):
        summary = self.app.music_manager.get_assignment_summary()
        favorite_count = summary.get("favorite_tracks", 0)
        if summary["stages_configured"] > 0 or summary.get("replacement_stages", 0) > 0:
            parts = [
                f"{summary.get('replacement_stages', 0)} safe stages",
                f"{summary.get('replacement_slots', 0)} safe slots",
                f"{summary['stages_configured']} legacy stages",
                f"{summary['total_assignments']} legacy assignments",
                "Vanilla excluded" if summary["exclude_vanilla"] else "Vanilla included",
            ]
            if summary.get("slot_catalog_stages", 0):
                parts.append(f"{summary['slot_catalog_stages']} stages with slot data")
            if favorite_count:
                parts.append(f"{favorite_count} favorites")
            self.summary_label.configure(
                text=" | ".join(parts),
                text_color="#2fa572")
        else:
            text = "Select a stage to manage safe slots or legacy playlist entries."
            if favorite_count:
                text += f" {favorite_count} favorite track(s) saved."
            self.summary_label.configure(
                text=text,
                text_color="#999999")

    def _stage_list_suffix(self, stage_id: str) -> str:
        legacy_count = len(self.app.music_manager.get_tracks_for_stage(stage_id))
        safe_count = len(self.app.music_manager.replacement_assignments.get(stage_id, {}))
        suffix_parts = []
        if safe_count:
            suffix_parts.append(f"S{safe_count}")
        if legacy_count:
            suffix_parts.append(f"L{legacy_count}")
        if not suffix_parts:
            return ""
        return f" ({' '.join(suffix_parts)})"

    def _update_stage_counts(self) -> None:
        if not self._selected_stage:
            self.playlist_count.configure(text="")
            return
        safe_count = len(self.app.music_manager.replacement_assignments.get(self._selected_stage, {}))
        legacy_count = len(self.app.music_manager.get_tracks_for_stage(self._selected_stage))
        self.playlist_count.configure(text=f"Safe {safe_count} | Legacy {legacy_count}")

    def _populate_stages(self):
        stages = self.app.music_manager.get_stage_list()
        self.stage_listbox.delete(0, tk.END)
        self._stage_ids = []
        comp_only = self.competitive_var.get()

        # Insert "Main Menu" first with a special prefix, then other stages
        menu_stage = None
        other_stages = []
        for stage in stages:
            if stage.stage_id == self._MENU_STAGE_ID:
                menu_stage = stage
            else:
                other_stages.append(stage)

        def _insert_stage(stage):
            if comp_only and stage.stage_id not in COMPETITIVE_STAGES and stage.stage_id != self._MENU_STAGE_ID:
                return
            prefix = self._MENU_STAGE_PREFIX if stage.stage_id == self._MENU_STAGE_ID else ""
            suffix = self._stage_list_suffix(stage.stage_id)
            self.stage_listbox.insert(tk.END, f"{prefix}{stage.stage_name}{suffix}")
            self._stage_ids.append(stage.stage_id)

        # Always show Main Menu first
        if menu_stage:
            _insert_stage(menu_stage)

        for stage in other_stages:
            _insert_stage(stage)

    def _on_stage_filter_input(self, *_args):
        self._schedule_stage_filter()

    def _schedule_stage_filter(self):
        if self._stage_filter_after_id:
            try:
                self.after_cancel(self._stage_filter_after_id)
            except Exception:
                pass
        self._stage_filter_after_id = self.after(self._FILTER_DEBOUNCE_MS, self._apply_stage_filter)

    def _apply_stage_filter(self):
        self._stage_filter_after_id = None
        self._filter_stages()

    def _filter_stages(self):
        search = self.stage_search_var.get().lower()
        stages = self.app.music_manager.get_stage_list()
        self.stage_listbox.delete(0, tk.END)
        self._stage_ids = []
        comp_only = self.competitive_var.get()

        # Sort: Main Menu first, then alphabetical
        menu_stage = None
        other_stages = []
        for stage in stages:
            if stage.stage_id == self._MENU_STAGE_ID:
                menu_stage = stage
            else:
                other_stages.append(stage)

        def _insert_if_match(stage):
            if comp_only and stage.stage_id not in COMPETITIVE_STAGES and stage.stage_id != self._MENU_STAGE_ID:
                return
            if search and search not in stage.stage_name.lower():
                return
            prefix = self._MENU_STAGE_PREFIX if stage.stage_id == self._MENU_STAGE_ID else ""
            suffix = self._stage_list_suffix(stage.stage_id)
            self.stage_listbox.insert(tk.END, f"{prefix}{stage.stage_name}{suffix}")
            self._stage_ids.append(stage.stage_id)

        if menu_stage:
            _insert_if_match(menu_stage)
        for stage in other_stages:
            _insert_if_match(stage)

    def _on_stage_select(self, event):
        sel = self.stage_listbox.curselection()
        if not sel or sel[0] >= len(self._stage_ids):
            return
        self._selected_stage = self._stage_ids[sel[0]]
        stage_name = VANILLA_STAGES.get(self._selected_stage, self._selected_stage)
        self.playlist_label.configure(text=f"Stage: {stage_name}")
        self._render_playlist()
        self._render_stage_slots()

    def _render_playlist(self):
        for w in self.playlist_frame.winfo_children():
            w.destroy()

        if not self._selected_stage:
            self._update_stage_counts()
            return

        tracks = self.app.music_manager.get_tracks_for_stage(self._selected_stage)
        self._update_stage_counts()

        if not tracks:
            ctk.CTkLabel(self.playlist_frame,
                         text="No legacy playlist entries.\n\nSelect tracks from the right panel\nand click '+ Add Selected Tracks'.",
                         text_color="#666666", font=ctk.CTkFont(size=12),
                         justify="center").pack(pady=30)
            return

        for i, track in enumerate(tracks):
            row = ctk.CTkFrame(self.playlist_frame, fg_color="#1e1e38", corner_radius=6,
                               height=36)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=8, pady=2)

            # Track number
            ctk.CTkLabel(inner, text=f"{i+1}.",
                         font=ctk.CTkFont(size=11), text_color="#666666",
                         width=24).pack(side="left")

            # Track info
            display = track.display_name if track.display_name else track.track_id
            ctk.CTkLabel(inner, text=display,
                         font=ctk.CTkFont(size=12), text_color="white",
                         anchor="w").pack(side="left", fill="x", expand=True)

            # Source mod
            if track.source_mod:
                ctk.CTkLabel(inner, text=track.source_mod,
                             font=ctk.CTkFont(size=10), text_color="#555555",
                             ).pack(side="left", padx=(0, 5))

            # Action buttons
            btn_frame = ctk.CTkFrame(inner, fg_color="transparent")
            btn_frame.pack(side="right")

            if i > 0:
                ctk.CTkButton(btn_frame, text="Up", width=24, height=22,
                              fg_color="#3a3a4a", hover_color="#555555",
                              font=ctk.CTkFont(size=10),
                              command=lambda t=track: self._move_up(t)).pack(side="left", padx=1)
            if i < len(tracks) - 1:
                ctk.CTkButton(btn_frame, text="Dn", width=24, height=22,
                              fg_color="#3a3a4a", hover_color="#555555",
                              font=ctk.CTkFont(size=10),
                              command=lambda t=track: self._move_down(t)).pack(side="left", padx=1)

            ctk.CTkButton(btn_frame, text="X", width=24, height=22,
                          fg_color="#b02a2a", hover_color="#8a1f1f",
                          font=ctk.CTkFont(size=10),
                          command=lambda t=track: self._remove_from_stage(t)).pack(side="left", padx=1)

        # Re-patch scroll speeds for the newly created playlist widgets
        self.after(self._PLAY_CLICK_DELAY_MS, self._patch_all_scroll_speeds)

    def _render_stage_slots(self):
        for widget in self.safe_slot_frame.winfo_children():
            widget.destroy()

        source_name = self.app.music_manager.get_stage_slot_source_name()
        if source_name:
            self.safe_slot_source.configure(text=f"Slot source: {source_name}")
        else:
            self.safe_slot_source.configure(text="Slot source: none discovered")

        if not self._selected_stage:
            self._update_stage_counts()
            return

        slots = self.app.music_manager.get_stage_slots(self._selected_stage)
        safe_slots = [slot for slot in slots if slot.is_likely_vanilla]
        self._update_stage_counts()

        if not slots:
            ctk.CTkLabel(
                self.safe_slot_frame,
                text=(
                    "No stage-slot database was discovered.\n\n"
                    "Add or point the app at a mod containing both "
                    "ui_stage_db.prc and ui_bgm_db.prc to enable safe slot replacement."
                ),
                text_color="#666666",
                font=ctk.CTkFont(size=12),
                justify="center",
                wraplength=320,
            ).pack(pady=30)
            return

        if not safe_slots:
            ctk.CTkLabel(
                self.safe_slot_frame,
                text="This stage has no likely-vanilla slots in the discovered database.",
                text_color="#666666",
                font=ctk.CTkFont(size=12),
                justify="center",
                wraplength=320,
            ).pack(pady=30)
            return

        for slot in safe_slots:
            assignment = self.app.music_manager.get_stage_slot_replacement_track(
                self._selected_stage,
                slot.slot_key,
            )
            row = ctk.CTkFrame(self.safe_slot_frame, fg_color="#1e1e38", corner_radius=6)
            row.pack(fill="x", pady=2)

            title = slot.display_name or slot.filename or slot.ui_bgm_id
            meta = slot.filename or slot.ui_bgm_id
            assigned_text = assignment.display_name if assignment else "No replacement assigned"
            assigned_color = "#2fa572" if assignment else "#888888"

            ctk.CTkLabel(
                row,
                text=title,
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
            ).pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(
                row,
                text=f"{meta} | incidence {slot.incidence}",
                font=ctk.CTkFont(size=10),
                text_color="#777799",
                anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 2))
            ctk.CTkLabel(
                row,
                text=f"Replacement: {assigned_text}",
                font=ctk.CTkFont(size=11),
                text_color=assigned_color,
                anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 6))

            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.pack(fill="x", padx=10, pady=(0, 8))
            ctk.CTkButton(
                btns,
                text="Use Selected",
                width=110,
                height=26,
                fg_color="#2fa572",
                hover_color="#106a43",
                font=ctk.CTkFont(size=11),
                command=lambda s=slot: self._assign_selected_track_to_slot(s),
            ).pack(side="left")
            ctk.CTkButton(
                btns,
                text="Clear",
                width=70,
                height=26,
                fg_color="#555570",
                hover_color="#666688",
                font=ctk.CTkFont(size=11),
                command=lambda s=slot: self._clear_slot_replacement(s),
            ).pack(side="left", padx=(6, 0))

        self.after(self._PLAY_CLICK_DELAY_MS, self._patch_all_scroll_speeds)

    def _render_available_tracks(self):
        """Populate the listbox with available tracks."""
        selected_track_ids = {
            track.track_id
            for track in self._get_selected_tracks()
        }
        search = self.track_search_var.get().lower()
        favorites_only = bool(self.favorites_only_var.get())
        render_signature = (self._track_data_revision, search, favorites_only)
        if render_signature == self._last_track_render_signature:
            return
        self._last_track_render_signature = render_signature

        self.track_listbox.delete(0, tk.END)
        self._track_id_map.clear()

        tracks = self._all_tracks or self.app.music_manager.get_all_available_tracks()
        filtered = self._get_filtered_tracks()

        favorites_shown = sum(1 for track in filtered if track.is_favorite)
        total_favorites = len(self.app.music_manager.favorite_track_ids)
        parts = [f"{len(filtered)}/{len(tracks)} tracks"]
        parts.append(f"{favorites_shown} favorites shown")
        if total_favorites != favorites_shown:
            parts.append(f"{total_favorites} total favorites")
        self.track_count_label.configure(text=" | ".join(parts))

        for i, track in enumerate(filtered):
            display = track.display_name if track.display_name else track.track_id
            mod = f" [{track.source_mod}]" if track.source_mod else ""
            prefix = "[Fav] " if track.is_favorite else ""
            self.track_listbox.insert(tk.END, f"{prefix}{display}{mod}")
            self._track_id_map[i] = track
            if track.track_id in selected_track_ids:
                self.track_listbox.selection_set(i)

        logger.debug("Music", f"Populated {len(filtered)} tracks in listbox")
        self._update_track_selection_state()

    def _get_filtered_tracks(self):
        search = self.track_search_var.get().lower()
        favorites_only = bool(self.favorites_only_var.get())
        tracks = self._all_tracks or self.app.music_manager.get_all_available_tracks()
        filtered = []
        for track in tracks:
            display = track.display_name if track.display_name else track.track_id
            if search and search not in display.lower():
                if not track.source_mod or search not in track.source_mod.lower():
                    continue
            if favorites_only and not track.is_favorite:
                continue
            filtered.append(track)
        return filtered

    def _on_track_filter_input(self, *_args):
        self._schedule_track_filter()

    def _schedule_track_filter(self):
        if self._track_filter_after_id:
            try:
                self.after_cancel(self._track_filter_after_id)
            except Exception:
                pass
        self._track_filter_after_id = self.after(self._FILTER_DEBOUNCE_MS, self._apply_track_filter)

    def _apply_track_filter(self):
        self._track_filter_after_id = None
        self._filter_tracks()

    def _filter_tracks(self):
        self._render_available_tracks()

    def _get_selected_tracks(self):
        """Get the currently selected tracks from the listbox."""
        return [
            self._track_id_map[index]
            for index in self.track_listbox.curselection()
            if index in self._track_id_map
        ]

    def _get_selected_track(self):
        """Get the first selected track from the listbox."""
        tracks = self._get_selected_tracks()
        if not tracks:
            return None
        return tracks[0]

    def _update_track_selection_state(self):
        selected_tracks = self._get_selected_tracks()
        if not hasattr(self, "favorite_selected_btn"):
            return

        if not selected_tracks:
            self.favorite_selected_btn.configure(
                text="Favorite Selected",
                state="disabled",
            )
            return

        all_favorites = all(track.is_favorite for track in selected_tracks)
        any_favorites = any(track.is_favorite for track in selected_tracks)
        label = "Favorite Selected"
        if all_favorites:
            label = "Unfavorite Selected"
        elif any_favorites:
            label = "Toggle Favorites"

        self.favorite_selected_btn.configure(text=label, state="normal")

    def _on_track_selection_changed(self, event):
        self._update_track_selection_state()
        self._on_track_click(event)

    def _toggle_selected_favorites(self):
        selected_tracks = self._get_selected_tracks()
        if not selected_tracks:
            messagebox.showwarning("Warning", "Select one or more tracks first.")
            return

        make_favorite = not all(track.is_favorite for track in selected_tracks)
        changed = 0
        for track in selected_tracks:
            before = track.is_favorite
            after = self.app.music_manager.set_track_favorite(track.track_id, make_favorite)
            track.is_favorite = after
            if before != after:
                changed += 1

        if changed:
            self._track_data_revision += 1
            self._last_track_render_signature = None
            self._render_available_tracks()
            self._update_summary()
        else:
            self._update_track_selection_state()

    def _assign_selected_track_to_slot(self, slot):
        if not self._selected_stage:
            messagebox.showwarning("Warning", "Select a stage first.")
            return

        track = self._get_selected_track()
        if track is None:
            messagebox.showwarning("Warning", "Select one track to assign to that slot.")
            return

        stage_id = self._selected_stage
        previous_track = self.app.music_manager.get_stage_slot_replacement_track(stage_id, slot.slot_key)

        def do_assign():
            self.app.music_manager.set_stage_slot_replacement(stage_id, slot.slot_key, track)

        def undo_assign():
            self.app.music_manager.set_stage_slot_replacement(stage_id, slot.slot_key, previous_track)

        action = Action(
            description=f"Replace slot {slot.filename or slot.ui_bgm_id} on {VANILLA_STAGES.get(stage_id, stage_id)}",
            do=do_assign,
            undo=undo_assign,
            page="music",
        )
        action_history.execute(action)

        self._render_stage_slots()
        self._populate_stages()
        self._update_summary()
        self.app.mark_unsaved()

    def _clear_slot_replacement(self, slot):
        if not self._selected_stage:
            return

        stage_id = self._selected_stage
        previous_track = self.app.music_manager.get_stage_slot_replacement_track(stage_id, slot.slot_key)
        if previous_track is None:
            return

        def do_clear():
            self.app.music_manager.set_stage_slot_replacement(stage_id, slot.slot_key, None)

        def undo_clear():
            self.app.music_manager.set_stage_slot_replacement(stage_id, slot.slot_key, previous_track)

        action = Action(
            description=f"Clear replacement for {slot.filename or slot.ui_bgm_id}",
            do=do_clear,
            undo=undo_clear,
            page="music",
        )
        action_history.execute(action)

        self._render_stage_slots()
        self._populate_stages()
        self._update_summary()
        self.app.mark_unsaved()

    def _clear_stage_replacements(self):
        if not self._selected_stage:
            messagebox.showwarning("Warning", "Select a stage first.")
            return

        existing = dict(self.app.music_manager.replacement_assignments.get(self._selected_stage, {}))
        if not existing:
            return

        stage_id = self._selected_stage

        def do_clear():
            self.app.music_manager.clear_stage_replacements(stage_id)

        def undo_clear():
            self.app.music_manager.replacement_assignments[stage_id] = dict(existing)

        action = Action(
            description=f"Clear safe replacements for {VANILLA_STAGES.get(stage_id, stage_id)}",
            do=do_clear,
            undo=undo_clear,
            page="music",
        )
        action_history.execute(action)

        self._render_stage_slots()
        self._populate_stages()
        self._update_summary()
        self.app.mark_unsaved()

    def _add_selected_track(self):
        """Add the selected track to the current stage."""
        if not self._selected_stage:
            messagebox.showwarning("Warning", "Select a stage first.")
            return

        selected_tracks = self._get_selected_tracks()
        if not selected_tracks:
            messagebox.showwarning("Warning", "Select one or more tracks to add.")
            return

        stage_id = self._selected_stage
        track_refs = list(selected_tracks)

        def do_add():
            for track_ref in track_refs:
                self.app.music_manager.assign_track_to_stage(track_ref, stage_id)

        def undo_add():
            for track_ref in track_refs:
                self.app.music_manager.remove_track_from_stage(track_ref.track_id, stage_id)

        action = Action(
            description=(
                f"Add {len(track_refs)} track(s) to "
                f"{VANILLA_STAGES.get(stage_id, stage_id)}"
            ),
            do=do_add, undo=undo_add, page="music",
        )
        action_history.execute(action)

        self._render_playlist()
        self._populate_stages()
        self._update_summary()
        self.app.mark_unsaved()

    def _remove_from_stage(self, track):
        if self._selected_stage:
            stage_id = self._selected_stage
            track_ref = track

            def do_remove():
                self.app.music_manager.remove_track_from_stage(track_ref.track_id, stage_id)

            def undo_remove():
                self.app.music_manager.assign_track_to_stage(track_ref, stage_id)

            action = Action(
                description=f"Remove track from {VANILLA_STAGES.get(stage_id, stage_id)}",
                do=do_remove, undo=undo_remove, page="music",
            )
            action_history.execute(action)

            self._render_playlist()
            self._populate_stages()
            self._update_summary()
            self.app.mark_unsaved()

    def _move_up(self, track):
        if self._selected_stage:
            self.app.music_manager.move_track_up(self._selected_stage, track.track_id)
            self._render_playlist()
            self.app.mark_unsaved()

    def _move_down(self, track):
        if self._selected_stage:
            self.app.music_manager.move_track_down(self._selected_stage, track.track_id)
            self._render_playlist()
            self.app.mark_unsaved()

    def _clear_stage(self):
        if self._selected_stage:
            self.app.music_manager.clear_stage(self._selected_stage)
            self._render_playlist()
            self._populate_stages()
            self._update_summary()
            self.app.mark_unsaved()

    def _add_all_to_stage(self):
        if not self._selected_stage:
            messagebox.showwarning("Warning", "Select a stage first.")
            return
        for track in self.app.music_manager.get_all_available_tracks():
            self.app.music_manager.assign_track_to_stage(track, self._selected_stage)
        self._render_playlist()
        self._populate_stages()
        self._update_summary()
        self.app.mark_unsaved()

    def _clear_all_stages(self):
        if messagebox.askyesno("Clear All", "Remove ALL legacy playlist assignments from ALL stages?"):
            self.app.music_manager.stage_playlists.clear()
            self._render_playlist()
            self._populate_stages()
            self._update_summary()
            self.app.mark_unsaved()

    def _assign_all_to_all(self):
        if messagebox.askyesno("Assign All", "Assign ALL tracks to ALL legacy stage playlists?"):
            self.app.music_manager.assign_all_tracks_to_all_stages()
            self._render_playlist()
            self._populate_stages()
            self._update_summary()
            self.app.mark_unsaved()

    def _on_exclude_change(self):
        self.app.music_manager.set_exclude_vanilla(self.exclude_var.get())
        self._update_summary()
        self.app.mark_unsaved()

    def _tracks_for_spotify_source(self, source: str):
        if source == "Favorite Tracks":
            return self.app.music_manager.get_favorite_tracks()
        return self._get_selected_tracks()

    def _spotify_enabled(self) -> bool:
        return bool(getattr(self.app.config_manager.settings, "experimental_spotify_enabled", False))

    def _refresh_spotify_button_state(self):
        if not hasattr(self, "spotify_export_btn"):
            return
        if self._spotify_enabled():
            self.spotify_export_btn.configure(
                text="Spotify Export (Experimental)...",
                state="normal",
                fg_color="#1f538d",
                hover_color="#163b6a",
            )
        else:
            self.spotify_export_btn.configure(
                text="Spotify Export Disabled in Settings",
                state="disabled",
                fg_color="#2a2a38",
                hover_color="#2a2a38",
            )

    def _resolve_track_by_id(self, track_id: str):
        for track in self.app.music_manager.get_all_available_tracks():
            if track.track_id == track_id:
                return track
        return None

    def _update_queue_status(self):
        if not self._queue_track_ids or self._queue_index < 0:
            self.queue_status.configure(text=self._QUEUE_EMPTY_TEXT, text_color="#888888")
            return
        self.queue_status.configure(
            text=f"Queue: {self._queue_name} {self._queue_index + 1}/{len(self._queue_track_ids)}",
            text_color="#8fb2ff",
        )

    def _prime_queue(self, tracks, queue_name: str, preferred_track_id: str = ""):
        self._queue_track_ids = [track.track_id for track in tracks]
        self._queue_name = queue_name
        self._queue_index = 0
        if preferred_track_id:
            for index, track_id in enumerate(self._queue_track_ids):
                if track_id == preferred_track_id:
                    self._queue_index = index
                    break
        self._update_queue_status()

    def _select_visible_track(self, track_id: str):
        for index, mapped_track in self._track_id_map.items():
            if mapped_track.track_id != track_id:
                continue
            self._suppress_track_selection_autoplay = True
            self.track_listbox.selection_clear(0, tk.END)
            self.track_listbox.selection_set(index)
            self.track_listbox.see(index)
            self.after(self._ZERO_DELAY_MS, lambda: setattr(self, "_suppress_track_selection_autoplay", False))
            self._update_track_selection_state()
            return

    def _start_queue_from_source(self, source: str):
        if source == "favorites":
            tracks = self.app.music_manager.get_favorite_tracks()
            queue_name = "Favorites"
        else:
            tracks = self._get_filtered_tracks()
            queue_name = "Filtered Tracks"

        if not tracks:
            self.player_status.configure(text="No tracks available for that queue.", text_color="#e94560")
            return

        selected = self._get_selected_track()
        preferred_track_id = selected.track_id if selected and any(t.track_id == selected.track_id for t in tracks) else tracks[0].track_id
        self._prime_queue(tracks, queue_name, preferred_track_id=preferred_track_id)
        self._play_queue_index(self._queue_index)

    def _play_queue_index(self, index: int):
        if not self._queue_track_ids:
            self._update_queue_status()
            return
        if index < 0 or index >= len(self._queue_track_ids):
            self.player_status.configure(text="Reached the end of the queue.", text_color="#888888")
            return
        self._queue_index = index
        track = self._resolve_track_by_id(self._queue_track_ids[index])
        if track is None:
            self.player_status.configure(text="Queued track is no longer available.", text_color="#e94560")
            return
        self._select_visible_track(track.track_id)
        self._play_track(track)

    def _step_queue(self, direction: int):
        if not self._queue_track_ids:
            self.player_status.configure(text="Start a queue first.", text_color="#888888")
            return
        self._play_queue_index(self._queue_index + direction)

    def _open_spotify_export_dialog(self):
        if not self._spotify_enabled():
            messagebox.showinfo(
                "Spotify Export Disabled",
                "Enable Spotify playlist export in Settings -> Experimental first.",
            )
            return
        existing = self._spotify_dialog
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass

        dialog = ctk.CTkToplevel(self)
        dialog.withdraw()
        dialog.title("Spotify Export (Experimental)")
        dialog.resizable(False, False)
        dialog.configure(fg_color="#0f1327")
        self._spotify_dialog = dialog

        shell = ctk.CTkFrame(
            dialog,
            fg_color="#151b36",
            corner_radius=10,
            border_width=1,
            border_color="#304378",
        )
        shell.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            shell,
            text="Spotify Export (Experimental)",
            anchor="w",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(
            shell,
            text=(
                "Use a Spotify app client ID with the redirect URI "
                f"{SPOTIFY_REDIRECT_URI_DOC}"
            ),
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color="#b9bfd8",
        ).pack(fill="x", padx=14, pady=(0, 10))

        settings = self.app.config_manager.settings
        state = {
            "busy": False,
            "playlists": [],
            "playlist_map": {},
        }
        client_id_var = tk.StringVar(value=settings.spotify_client_id or "")
        source_var = tk.StringVar(
            value="Selected Tracks" if self._get_selected_tracks() else "Favorite Tracks"
        )
        playlist_var = tk.StringVar(value="")
        new_playlist_var = tk.StringVar(value="")
        public_var = ctk.BooleanVar(value=False)

        auth_frame = ctk.CTkFrame(shell, fg_color="#11182f", corner_radius=8)
        auth_frame.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(
            auth_frame,
            text="Spotify Connection",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(fill="x", padx=10, pady=(10, 6))

        client_row = ctk.CTkFrame(auth_frame, fg_color="transparent")
        client_row.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkEntry(
            client_row,
            textvariable=client_id_var,
            placeholder_text="Spotify client ID",
            height=30,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        connect_btn = ctk.CTkButton(
            client_row,
            text="Connect",
            width=96,
            height=30,
            fg_color="#2fa572",
            hover_color="#106a43",
        )
        connect_btn.pack(side="left", padx=(0, 6))

        disconnect_btn = ctk.CTkButton(
            client_row,
            text="Disconnect",
            width=96,
            height=30,
            fg_color="#555570",
            hover_color="#666688",
        )
        disconnect_btn.pack(side="left")

        auth_status = ctk.CTkLabel(
            auth_frame,
            text="",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
        )
        auth_status.pack(fill="x", padx=10, pady=(0, 10))

        export_frame = ctk.CTkFrame(shell, fg_color="#11182f", corner_radius=8)
        export_frame.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(
            export_frame,
            text="Playlist Export",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(fill="x", padx=10, pady=(10, 6))

        source_counts = ctk.CTkLabel(
            export_frame,
            text=(
                f"Selected tracks: {len(self._get_selected_tracks())} | "
                f"Favorite tracks: {len(self.app.music_manager.get_favorite_tracks())}"
            ),
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color="#b9bfd8",
        )
        source_counts.pack(fill="x", padx=10, pady=(0, 6))

        source_row = ctk.CTkFrame(export_frame, fg_color="transparent")
        source_row.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(source_row, text="Export source",
                     font=ctk.CTkFont(size=11), width=110, anchor="w").pack(side="left")
        source_menu = ctk.CTkOptionMenu(
            source_row,
            values=["Selected Tracks", "Favorite Tracks"],
            variable=source_var,
            width=220,
        )
        source_menu.pack(side="left")

        playlist_row = ctk.CTkFrame(export_frame, fg_color="transparent")
        playlist_row.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(playlist_row, text="Existing playlist",
                     font=ctk.CTkFont(size=11), width=110, anchor="w").pack(side="left")
        playlist_menu = ctk.CTkOptionMenu(
            playlist_row,
            values=["Connect Spotify first"],
            variable=playlist_var,
            width=280,
        )
        playlist_menu.pack(side="left", fill="x", expand=True, padx=(0, 8))

        refresh_btn = ctk.CTkButton(
            playlist_row,
            text="Refresh",
            width=84,
            height=28,
            fg_color="#333352",
            hover_color="#444470",
        )
        refresh_btn.pack(side="left")

        new_playlist_row = ctk.CTkFrame(export_frame, fg_color="transparent")
        new_playlist_row.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(new_playlist_row, text="New playlist",
                     font=ctk.CTkFont(size=11), width=110, anchor="w").pack(side="left")
        ctk.CTkEntry(
            new_playlist_row,
            textvariable=new_playlist_var,
            placeholder_text="Leave blank to use the selected playlist",
            height=30,
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkCheckBox(
            export_frame,
            text="Create new playlist as public",
            variable=public_var,
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=10, pady=(0, 10))

        status_label = ctk.CTkLabel(
            shell,
            text="",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
            wraplength=580,
        )
        status_label.pack(fill="x", padx=14, pady=(0, 8))

        button_row = ctk.CTkFrame(shell, fg_color="transparent")
        button_row.pack(fill="x", padx=14, pady=(0, 12))

        export_btn = ctk.CTkButton(
            button_row,
            text="Export",
            width=96,
            height=30,
            fg_color="#1f538d",
            hover_color="#163b6a",
        )
        export_btn.pack(side="right", padx=(8, 0))

        close_btn = ctk.CTkButton(
            button_row,
            text="Close",
            width=96,
            height=30,
            fg_color="#2f3557",
            hover_color="#3f476f",
        )
        close_btn.pack(side="right")

        def _close_dialog():
            if state["busy"]:
                _set_status("Wait for the current Spotify action to finish.")
                return
            self._spotify_dialog = None
            try:
                dialog.grab_release()
            except Exception:
                pass
            dialog.destroy()

        close_btn.configure(command=_close_dialog)

        def _set_status(text: str, color: str = "#888888") -> None:
            status_label.configure(text=text, text_color=color)

        def _set_busy(busy: bool) -> None:
            state["busy"] = busy
            button_state = "disabled" if busy else "normal"
            connect_btn.configure(state=button_state)
            disconnect_btn.configure(state=button_state)
            refresh_btn.configure(state=button_state)
            export_btn.configure(state=button_state)
            close_btn.configure(state=button_state)

        def _refresh_auth_ui() -> None:
            current = self.app.config_manager.settings
            if self.app.spotify_manager.is_authenticated():
                name = current.spotify_display_name or current.spotify_user_id or "Connected"
                auth_status.configure(
                    text=f"Connected as {name}",
                    text_color="#2fa572",
                )
                connect_btn.configure(text="Reconnect")
                disconnect_btn.configure(state="normal" if not state["busy"] else "disabled")
            else:
                auth_status.configure(
                    text="Not connected",
                    text_color="#888888",
                )
                connect_btn.configure(text="Connect")
                disconnect_btn.configure(state="disabled" if not state["busy"] else "disabled")

        def _apply_playlists(playlists) -> None:
            state["playlists"] = list(playlists)
            playlist_map = {}
            for playlist in playlists:
                label = playlist.label
                if label in playlist_map:
                    label = f"{playlist.name} [{playlist.playlist_id[:8]}]"
                playlist_map[label] = playlist
            state["playlist_map"] = playlist_map

            if playlist_map:
                values = list(playlist_map.keys())
                playlist_menu.configure(values=values)
                last_id = self.app.config_manager.settings.spotify_last_playlist_id
                selected_value = values[0]
                if last_id:
                    for label, playlist in playlist_map.items():
                        if playlist.playlist_id == last_id:
                            selected_value = label
                            break
                playlist_var.set(selected_value)
            else:
                placeholder = "No owned playlists found"
                playlist_menu.configure(values=[placeholder])
                playlist_var.set(placeholder)

        def _load_playlists_async() -> None:
            if not self.app.spotify_manager.is_authenticated():
                _apply_playlists([])
                return

            _set_busy(True)
            _set_status("Loading your Spotify playlists...")

            def _worker():
                try:
                    playlists = self.app.spotify_manager.list_owned_playlists()
                except Exception as exc:
                    self.after(
                        self._ZERO_DELAY_MS,
                        lambda err=str(exc): (
                            _set_busy(False),
                            _set_status(err, "#e94560"),
                            _refresh_auth_ui(),
                        ),
                    )
                    return

                self.after(
                    self._ZERO_DELAY_MS,
                    lambda pls=playlists: (
                        _set_busy(False),
                        _apply_playlists(pls),
                        _refresh_auth_ui(),
                        _set_status(
                            f"Loaded {len(pls)} owned Spotify playlist(s).",
                            "#2fa572",
                        ),
                    ),
                )

            threading.Thread(target=_worker, daemon=True).start()

        def _connect_async() -> None:
            cleaned_client_id = client_id_var.get().strip()
            if not cleaned_client_id:
                _set_status("Enter a Spotify client ID first.", "#e94560")
                return

            _set_busy(True)
            _set_status("Opening Spotify sign-in in your browser...")

            def _worker():
                try:
                    profile = self.app.spotify_manager.connect(cleaned_client_id)
                    playlists = self.app.spotify_manager.list_owned_playlists()
                except Exception as exc:
                    self.after(
                        self._ZERO_DELAY_MS,
                        lambda err=str(exc): (
                            _set_busy(False),
                            _refresh_auth_ui(),
                            _set_status(err, "#e94560"),
                        ),
                    )
                    return

                def _done():
                    _set_busy(False)
                    _refresh_auth_ui()
                    _apply_playlists(playlists)
                    _set_status(
                        f"Connected as {profile.display_name}. Loaded {len(playlists)} playlist(s).",
                        "#2fa572",
                    )

                self.after(self._ZERO_DELAY_MS, _done)

            threading.Thread(target=_worker, daemon=True).start()

        def _disconnect() -> None:
            self.app.spotify_manager.disconnect()
            _apply_playlists([])
            _refresh_auth_ui()
            _set_status("Spotify connection removed.", "#888888")

        def _export_async() -> None:
            source = source_var.get()
            tracks = self._tracks_for_spotify_source(source)
            if not tracks:
                _set_status(f"No tracks available for '{source}'.", "#e94560")
                return
            if not self.app.spotify_manager.is_authenticated():
                _set_status("Connect a Spotify account first.", "#e94560")
                return

            new_playlist_name = new_playlist_var.get().strip()
            selected_label = playlist_var.get().strip()
            selected_playlist = state["playlist_map"].get(selected_label)
            if not new_playlist_name and selected_playlist is None:
                _set_status("Select an existing playlist or enter a new playlist name.", "#e94560")
                return

            _set_busy(True)
            _set_status(f"Exporting {len(tracks)} track(s) to Spotify...")

            def _worker():
                try:
                    playlist = selected_playlist
                    if new_playlist_name:
                        playlist = self.app.spotify_manager.create_playlist(
                            new_playlist_name,
                            public=bool(public_var.get()),
                            description="Created by SSBU Mod Manager",
                        )
                    report = self.app.spotify_manager.export_tracks_to_playlist(playlist, tracks)
                    current = self.app.config_manager.settings
                    current.spotify_last_playlist_id = report.playlist_id
                    self.app.config_manager.save(current)
                except Exception as exc:
                    self.after(
                        self._ZERO_DELAY_MS,
                        lambda err=str(exc): (
                            _set_busy(False),
                            _set_status(err, "#e94560"),
                        ),
                    )
                    return

                def _done():
                    _set_busy(False)
                    _set_status(
                        f"Spotify export finished for '{report.playlist_name}'.",
                        "#2fa572",
                    )
                    messagebox.showinfo(
                        "Spotify Export Complete",
                        self._format_spotify_export_report(report),
                    )
                    _load_playlists_async()

                self.after(self._ZERO_DELAY_MS, _done)

            threading.Thread(target=_worker, daemon=True).start()

        connect_btn.configure(command=_connect_async)
        disconnect_btn.configure(command=_disconnect)
        refresh_btn.configure(command=_load_playlists_async)
        export_btn.configure(command=_export_async)
        dialog.protocol("WM_DELETE_WINDOW", _close_dialog)
        dialog.bind("<Escape>", lambda _e: _close_dialog())

        self._center_dialog(dialog, width=640, height=520)
        self._present_modal_dialog(dialog, focus_widget=None, animate_open=False)
        _refresh_auth_ui()
        if self.app.spotify_manager.is_authenticated():
            _load_playlists_async()
        else:
            _apply_playlists([])
            _set_status("Connect Spotify to load your playlists.")

    @staticmethod
    def _format_spotify_export_report(report) -> str:
        lines = [
            f"Playlist: {report.playlist_name}",
            f"Attempted: {report.attempted}",
            f"Matched on Spotify: {report.matched}",
            f"Added: {report.added}",
            f"Skipped as duplicates/already present: {report.duplicate_skips}",
        ]
        if report.playlist_url:
            lines.append(f"Spotify URL: {report.playlist_url}")
        if report.unresolved:
            lines.append("")
            lines.append("Unresolved tracks:")
            lines.extend(f"- {name}" for name in report.unresolved[:8])
            if len(report.unresolved) > 8:
                lines.append(f"...and {len(report.unresolved) - 8} more")
        if report.low_confidence:
            lines.append("")
            lines.append("Skipped for low-confidence matching:")
            lines.extend(f"- {name}" for name in report.low_confidence[:8])
            if len(report.low_confidence) > 8:
                lines.append(f"...and {len(report.low_confidence) - 8} more")
        return "\n".join(lines)

    def _center_dialog(self, dialog, width: int, height: int):
        try:
            self.update_idletasks()
            x = self.winfo_rootx() + max(20, (self.winfo_width() - width) // 2)
            y = self.winfo_rooty() + max(20, (self.winfo_height() - height) // 2)
        except Exception:
            x, y = 200, 200
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    # Audio playback methods
    def _on_track_click(self, event):
        """When user clicks a track while music is already playing,
        auto-play the newly selected track."""
        if self._suppress_track_selection_autoplay:
            return
        if self._is_playing and len(self._get_selected_tracks()) == 1:
            # Short delay so the listbox selection updates first
            self.after(self._PLAY_CLICK_DELAY_MS, self._play_selected)

    def _toggle_playback(self):
        """Toggle between play and stop."""
        if self._is_playing:
            self._stop_playback()
        else:
            self._play_selected()

    def _play_selected(self):
        track = self._get_selected_track()
        if not track:
            self.player_status.configure(text="Select a track first", text_color="#e94560")
            self.after(
                self._PLAYBACK_STATUS_CLEAR_MS,
                lambda: self.player_status.configure(text=""),
            )
            return
        filtered_tracks = self._get_filtered_tracks()
        if filtered_tracks:
            self._prime_queue(filtered_tracks, "Filtered Tracks", preferred_track_id=track.track_id)
        self._play_track(track)

    def _cancel_playback_timers(self):
        for attr in ("_poll_after_id", "_seek_after_id"):
            aid = getattr(self, attr, None)
            if aid:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)

    def _play_track(self, track):
        """Play a specific track in a background thread."""
        self._manual_stop_requested = False

        # Stop any current playback first to prevent concurrent threads
        if self._is_playing:
            audio_player.stop()
            self._is_playing = False

        self._cancel_playback_timers()

        # Cancel any in-flight play request by bumping the generation counter
        if not hasattr(self, '_play_generation'):
            self._play_generation = 0
        self._play_generation += 1
        current_gen = self._play_generation

        self.player_status.configure(text="Loading...", text_color="#888888")
        self.update_idletasks()

        def _play_bg():
            # If another play request was issued, abandon this one
            if current_gen != self._play_generation:
                return
            result = audio_player.play(track.file_path)
            if current_gen != self._play_generation:
                # A newer request superseded us; stop what we just started
                audio_player.stop()
                return
            if not self.app.shutting_down:
                self.after(self._ZERO_DELAY_MS, lambda: self._on_play_result(result, track))

        threading.Thread(target=_play_bg, daemon=True).start()

    def _on_play_result(self, result, track):
        """Handle play result on the main thread."""
        success, msg = result
        color = "#2fa572" if success else "#e94560"
        self.player_status.configure(text=msg, text_color=color)
        if success:
            self._is_playing = True
            self.play_toggle_btn.configure(
                text="Stop", fg_color="#b02a2a", hover_color="#8a1f1f")
            self._update_queue_status()
            # Start polling for end-of-track to reset button state
            self._poll_playback_end()
            # Start seek bar updates
            dur = audio_player.get_duration()
            self.seek_duration_label.configure(text=self._fmt_time(int(dur)))
            self.seek_slider.set(self._ZERO_DELAY_MS)
            self._update_seek_bar()
        else:
            self.after(
                self._PLAYBACK_ERROR_CLEAR_MS,
                lambda: self.player_status.configure(text=""),
            )

    def _poll_playback_end(self):
        """Periodically check if playback ended so the button resets."""
        self._poll_after_id = None
        if not self._is_playing:
            return
        if not audio_player.is_playing:
            if (
                not self._manual_stop_requested
                and self._queue_track_ids
                and self._queue_index + 1 < len(self._queue_track_ids)
            ):
                self._is_playing = False
                self.play_toggle_btn.configure(
                    text="Play", fg_color="#2fa572", hover_color="#106a43")
                self._play_queue_index(self._queue_index + 1)
                return
            self._is_playing = False
            self.play_toggle_btn.configure(
                text="Play", fg_color="#2fa572", hover_color="#106a43")
            self.player_status.configure(text="")
            return
        self._poll_after_id = self.after(self._PLAYBACK_POLL_MS, self._poll_playback_end)

    def _stop_playback(self):
        self._manual_stop_requested = True
        audio_player.stop()
        self._is_playing = False
        self._cancel_playback_timers()
        self.play_toggle_btn.configure(
            text="Play", fg_color="#2fa572", hover_color="#106a43")
        self.player_status.configure(text="Stopped", text_color="#888888")
        self.seek_slider.set(self._ZERO_DELAY_MS)
        self.seek_label.configure(text=self._ZERO_TIME_TEXT)
        self.seek_duration_label.configure(text=self._ZERO_TIME_TEXT)
        self.after(self._PLAYBACK_STOPPED_CLEAR_MS, lambda: self.player_status.configure(text=""))

    def _on_volume_change(self, value):
        new_volume = max(self._MIN_VOLUME, min(self._MAX_VOLUME, float(value) / self._MAX_PERCENT))
        if abs(new_volume - self._pending_volume_value) < self._VOLUME_EPSILON:
            return
        self._pending_volume_value = new_volume
        audio_player.set_volume(self._pending_volume_value)

    def _on_seek_drag(self, value):
        """Called continuously as the seek slider is dragged."""
        dur = audio_player.get_duration()
        if dur > 0:
            secs = int(value / self._MAX_PERCENT * dur)
            self.seek_label.configure(text=self._fmt_time(secs))

    def _on_seek_release(self, event):
        """Seek to position when slider is released."""
        self._seek_dragging = False
        dur = audio_player.get_duration()
        if dur > 0 and self._is_playing:
            pos = self.seek_slider.get() / self._MAX_PERCENT * dur
            audio_player.seek(pos)

    def _update_seek_bar(self):
        """Periodically update the seek slider to reflect playback position."""
        self._seek_after_id = None
        if not self._is_playing or self._seek_dragging:
            return
        dur = audio_player.get_duration()
        pos = audio_player.get_position()
        if dur > 0:
            pct = min(self._MAX_PERCENT, pos / dur * self._MAX_PERCENT)
            self.seek_slider.set(pct)
            self.seek_label.configure(text=self._fmt_time(int(pos)))
            self.seek_duration_label.configure(text=self._fmt_time(int(dur)))
        self._seek_after_id = self.after(self._SEEK_UPDATE_MS, self._update_seek_bar)

    @staticmethod
    def _fmt_time(seconds: int) -> str:
        m, s = divmod(max(0, seconds), MusicPage._SECONDS_PER_MINUTE)
        return f"{m}:{s:02d}"

    def save_changes(self):
        """Public save method invoked by the global toolbar Save button."""
        self._save_assignments()

    def _save_assignments(self):
        settings = self.app.config_manager.settings
        if not settings.mods_path or not settings.mods_path.exists():
            messagebox.showwarning("Warning", "No mods path configured.")
            return

        summary = self.app.music_manager.get_assignment_summary()
        if summary["stages_configured"] == 0 and summary.get("replacement_slots", 0) == 0:
            messagebox.showwarning("Warning", "No safe replacements or legacy playlist entries configured yet.")
            return

        try:
            result = self.app.music_manager.save_assignments(settings.mods_path)
            msg = f"Music configuration saved!\n\n"
            msg += f"Safe replacement stages: {result.get('replacement_stages', 0)}\n"
            msg += f"Safe replacement files: {result.get('replacement_files', 0)}\n"
            msg += f"Legacy playlist stages: {result['stages_configured']}\n"
            msg += f"Legacy playlist assignments: {result['tracks_assigned']}\n"
            if result.get("menu_music_set"):
                msg += f"\nMain menu music has been set!"
            if result.get("replacement_output_mod"):
                msg += f"\nReplacement overlay: {result['replacement_output_mod']}"
            if result.get("prc_updated"):
                msg += f"\nPRC updated in: {result['output_mod']}"
            logger.info(
                "Music",
                "Saved music config: "
                f"{result.get('replacement_files', 0)} safe replacements, "
                f"{result['stages_configured']} legacy stages, "
                f"{result['tracks_assigned']} legacy tracks",
            )
            self.app.mark_saved()
            messagebox.showinfo("Saved", msg)
        except Exception as e:
            logger.error("Music", f"Save failed: {e}")
            messagebox.showerror("Error", f"Failed to save: {e}")

