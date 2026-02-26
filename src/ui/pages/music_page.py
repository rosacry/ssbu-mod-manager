"""Music management page - 3-column layout with audio preview."""
import threading
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from src.ui.base_page import BasePage
from src.constants import VANILLA_STAGES, COMPETITIVE_STAGES
from src.utils.logger import logger
from src.utils.audio_player import audio_player
from src.utils.action_history import action_history, Action


class MusicPage(BasePage):
    _SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._selected_stage = None
        self._loaded = False
        self._scan_in_progress = False
        self._pending_rescan = False
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
        self._auto_scan_delay_ms = 260
        self._pending_volume_value = 0.7
        self._track_data_revision = 0
        self._last_track_render_signature = None
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

        ctk.CTkButton(bulk_frame, text="All → All Stages",
                      command=self._assign_all_to_all,
                      fg_color="#2fa572", hover_color="#106a43",
                      font=ctk.CTkFont(size=11), height=28, corner_radius=6,
                      ).pack(fill="x", pady=1)

        ctk.CTkButton(bulk_frame, text="Clear All Stages",
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

        # === MIDDLE COLUMN: Stage playlist ===
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

        self.playlist_frame = ctk.CTkScrollableFrame(middle, fg_color="transparent")
        self.playlist_frame.pack(fill="both", expand=True, padx=5, pady=5)

        playlist_btns = ctk.CTkFrame(middle, fg_color="transparent")
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

        # Available tracks list
        track_frame = ctk.CTkFrame(right, fg_color="transparent")
        track_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        self.track_listbox = tk.Listbox(track_frame, bg="#1e1e2e", fg="#cccccc",
                                         selectbackground="#1f538d",
                                         selectforeground="white",
                                         font=("Segoe UI", 10),
                                         relief="flat", bd=0, highlightthickness=0,
                                         activestyle="none", cursor="arrow")
        track_scroll = ctk.CTkScrollbar(track_frame, command=self.track_listbox.yview)
        self.track_listbox.configure(yscrollcommand=track_scroll.set)
        self.track_listbox.pack(side="left", fill="both", expand=True)
        track_scroll.pack(side="right", fill="y")

        # Double-click to add
        self.track_listbox.bind("<Double-1>", lambda e: self._add_selected_track())
        # Single-click to auto-play when already playing
        self.track_listbox.bind("<<ListboxSelect>>", self._on_track_click)

        # Audio player controls: play/stop toggle + volume, right-aligned near track list
        player_frame = ctk.CTkFrame(right, fg_color="#1e1e30", corner_radius=6)
        player_frame.pack(fill="x", padx=10, pady=(2, 4))

        # Now playing status — above the controls so it's always visible
        self.player_status = ctk.CTkLabel(
            player_frame, text="",
            font=ctk.CTkFont(size=10), text_color="#2fa572",
            anchor="w",
        )
        self.player_status.pack(fill="x", padx=8, pady=(5, 0))

        player_inner = ctk.CTkFrame(player_frame, fg_color="transparent")
        player_inner.pack(fill="x", padx=8, pady=5)

        # Single play/stop toggle button
        self._is_playing = False
        self.play_toggle_btn = ctk.CTkButton(
            player_inner, text="▶  Play", width=80, height=28,
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
        self.volume_slider.set(70)
        self.volume_slider.pack(side="left", padx=(0, 6))

        # Seek timeline
        self.seek_label = ctk.CTkLabel(player_inner, text="0:00",
                                       font=ctk.CTkFont(size=10), text_color="#555555")
        self.seek_label.pack(side="left", padx=(4, 2))
        self._seek_dragging = False
        self.seek_slider = ctk.CTkSlider(
            player_inner, from_=0, to=100, width=120, height=14,
            command=self._on_seek_drag,
            fg_color="#2a2a4a", progress_color="#1f538d",
            button_color="#4488cc", button_hover_color="#5599dd",
        )
        self.seek_slider.set(0)
        self.seek_slider.pack(side="left", padx=(0, 2))
        self.seek_slider.bind("<ButtonPress-1>", lambda e: setattr(self, '_seek_dragging', True))
        self.seek_slider.bind("<ButtonRelease-1>", self._on_seek_release)
        self.seek_duration_label = ctk.CTkLabel(player_inner, text="0:00",
                                                 font=ctk.CTkFont(size=10), text_color="#555555")
        self.seek_duration_label.pack(side="left", padx=(2, 6))

        # Add track button
        add_btn_frame = ctk.CTkFrame(right, fg_color="transparent")
        add_btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(add_btn_frame, text="+ Add Selected Track",
                      command=self._add_selected_track,
                      fg_color="#2fa572", hover_color="#106a43",
                      height=30, corner_radius=6, font=ctk.CTkFont(size=12),
                      ).pack(fill="x")

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
        # Sync play button state with actual audio player
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

    def _schedule_auto_scan(self):
        self._cancel_auto_scan()

        def _run():
            self._auto_scan_after_id = None
            if self._loaded or self._scan_in_progress:
                return
            if not self._is_music_page_active():
                return
            self._scan_tracks()

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
                    text="■  Stop", fg_color="#b02a2a", hover_color="#8a1f1f")
        else:
            if self._is_playing:
                self._is_playing = False
                self.play_toggle_btn.configure(
                    text="▶  Play", fg_color="#2fa572", hover_color="#106a43")
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
        self.after(100, self._animate_spinner)

    def _force_scan(self):
        self._cancel_auto_scan()
        if self._scan_in_progress:
            self._pending_rescan = True
            self.loading_label.configure(text="Rescan queued...")
            return
        self._loaded = False
        self._scan_tracks()

    def _scan_tracks(self):
        self._cancel_auto_scan()
        if self._scan_in_progress:
            return
        settings = self.app.config_manager.settings
        if not settings.mods_path or not settings.mods_path.exists():
            self.track_count_label.configure(text="No mods path configured")
            return

        self._scan_in_progress = True
        self._pending_rescan = False
        self._scan_generation += 1
        current_gen = self._scan_generation
        self._scan_cancel_event = threading.Event()
        cancel_event = self._scan_cancel_event
        self._start_spinner("Scanning tracks")
        logger.info("Music", f"Scanning for tracks in: {settings.mods_path}")

        mods_path = settings.mods_path

        def scan():
            try:
                tracks = self.app.music_manager.discover_tracks(mods_path, cancel_event=cancel_event)
                if cancel_event.is_set():
                    logger.info("Music", "Track scan cancelled")
                    return
                logger.info("Music", f"Found {len(tracks)} tracks")
                if not self.app.shutting_down:
                    try:
                        self.app.after(0, lambda t=tracks, gen=current_gen: self._on_tracks_loaded(t, gen))
                    except Exception:
                        pass
            except Exception as e:
                logger.error("Music", f"Track scan failed: {e}")
                if not self.app.shutting_down:
                    try:
                        self.app.after(0, lambda err=str(e), gen=current_gen: self._on_scan_error(err, gen))
                    except Exception:
                        pass
            finally:
                if not self.app.shutting_down:
                    try:
                        self.app.after(0, lambda gen=current_gen: self._on_scan_finished(gen))
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
            self._pending_rescan = False
            self._loaded = False
            self._scan_tracks()

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

    def _update_summary(self):
        summary = self.app.music_manager.get_assignment_summary()
        if summary["stages_configured"] > 0:
            self.summary_label.configure(
                text=f"{summary['stages_configured']} stages · "
                     f"{summary['total_assignments']} assignments · "
                     f"{'Vanilla excluded' if summary['exclude_vanilla'] else 'Vanilla included'}",
                text_color="#2fa572")
        else:
            self.summary_label.configure(
                text="Select a stage, then add tracks from the right panel.",
                text_color="#999999")

    def _populate_stages(self):
        stages = self.app.music_manager.get_stage_list()
        self.stage_listbox.delete(0, tk.END)
        self._stage_ids = []
        comp_only = self.competitive_var.get()

        # Insert "Main Menu" first with a special prefix, then other stages
        menu_stage = None
        other_stages = []
        for stage in stages:
            if stage.stage_id == "ui_stage_id_menu":
                menu_stage = stage
            else:
                other_stages.append(stage)

        def _insert_stage(stage):
            if comp_only and stage.stage_id not in COMPETITIVE_STAGES and stage.stage_id != "ui_stage_id_menu":
                return
            count = len(self.app.music_manager.get_tracks_for_stage(stage.stage_id))
            prefix = "🎵 " if stage.stage_id == "ui_stage_id_menu" else ""
            suffix = f" ({count})" if count > 0 else ""
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
        self._stage_filter_after_id = self.after(120, self._apply_stage_filter)

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
            if stage.stage_id == "ui_stage_id_menu":
                menu_stage = stage
            else:
                other_stages.append(stage)

        def _insert_if_match(stage):
            if comp_only and stage.stage_id not in COMPETITIVE_STAGES and stage.stage_id != "ui_stage_id_menu":
                return
            if search and search not in stage.stage_name.lower():
                return
            count = len(self.app.music_manager.get_tracks_for_stage(stage.stage_id))
            prefix = "🎵 " if stage.stage_id == "ui_stage_id_menu" else ""
            suffix = f" ({count})" if count > 0 else ""
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
        self.playlist_label.configure(text=f"Playlist: {stage_name}")
        self._render_playlist()

    def _render_playlist(self):
        for w in self.playlist_frame.winfo_children():
            w.destroy()

        if not self._selected_stage:
            return

        tracks = self.app.music_manager.get_tracks_for_stage(self._selected_stage)
        self.playlist_count.configure(text=f"{len(tracks)} tracks")

        if not tracks:
            ctk.CTkLabel(self.playlist_frame,
                         text="No tracks assigned.\n\nSelect tracks from the right panel\nand click '+ Add Selected Track'.",
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
                ctk.CTkButton(btn_frame, text="▲", width=24, height=22,
                              fg_color="#3a3a4a", hover_color="#555555",
                              font=ctk.CTkFont(size=10),
                              command=lambda t=track: self._move_up(t)).pack(side="left", padx=1)
            if i < len(tracks) - 1:
                ctk.CTkButton(btn_frame, text="▼", width=24, height=22,
                              fg_color="#3a3a4a", hover_color="#555555",
                              font=ctk.CTkFont(size=10),
                              command=lambda t=track: self._move_down(t)).pack(side="left", padx=1)

            ctk.CTkButton(btn_frame, text="✕", width=24, height=22,
                          fg_color="#b02a2a", hover_color="#8a1f1f",
                          font=ctk.CTkFont(size=10),
                          command=lambda t=track: self._remove_from_stage(t)).pack(side="left", padx=1)

        # Re-patch scroll speeds for the newly created playlist widgets
        self.after(50, self._patch_all_scroll_speeds)

    def _render_available_tracks(self):
        """Populate the listbox with available tracks."""
        search = self.track_search_var.get().lower()
        render_signature = (self._track_data_revision, search)
        if render_signature == self._last_track_render_signature:
            return
        self._last_track_render_signature = render_signature

        self.track_listbox.delete(0, tk.END)
        self._track_id_map.clear()

        tracks = self._all_tracks or self.app.music_manager.get_all_available_tracks()

        filtered = []
        for track in tracks:
            display = track.display_name if track.display_name else track.track_id
            if search and search not in display.lower():
                if not track.source_mod or search not in track.source_mod.lower():
                    continue
            filtered.append(track)

        self.track_count_label.configure(text=f"{len(filtered)}/{len(tracks)} tracks")

        for i, track in enumerate(filtered):
            display = track.display_name if track.display_name else track.track_id
            mod = f" [{track.source_mod}]" if track.source_mod else ""
            self.track_listbox.insert(tk.END, f"{display}{mod}")
            self._track_id_map[i] = track

        logger.debug("Music", f"Populated {len(filtered)} tracks in listbox")

    def _on_track_filter_input(self, *_args):
        self._schedule_track_filter()

    def _schedule_track_filter(self):
        if self._track_filter_after_id:
            try:
                self.after_cancel(self._track_filter_after_id)
            except Exception:
                pass
        self._track_filter_after_id = self.after(120, self._apply_track_filter)

    def _apply_track_filter(self):
        self._track_filter_after_id = None
        self._filter_tracks()

    def _filter_tracks(self):
        self._render_available_tracks()

    def _get_selected_track(self):
        """Get the currently selected track from the listbox."""
        sel = self.track_listbox.curselection()
        if not sel:
            return None
        return self._track_id_map.get(sel[0])

    def _add_selected_track(self):
        """Add the selected track to the current stage."""
        if not self._selected_stage:
            messagebox.showwarning("Warning", "Select a stage first.")
            return

        track = self._get_selected_track()
        if not track:
            messagebox.showwarning("Warning", "Select a track to add.")
            return

        stage_id = self._selected_stage
        track_ref = track

        def do_add():
            self.app.music_manager.assign_track_to_stage(track_ref, stage_id)

        def undo_add():
            self.app.music_manager.remove_track_from_stage(track_ref.track_id, stage_id)

        action = Action(
            description=f"Add track to {VANILLA_STAGES.get(stage_id, stage_id)}",
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
        if messagebox.askyesno("Clear All", "Remove ALL assignments from ALL stages?"):
            self.app.music_manager.stage_playlists.clear()
            self._render_playlist()
            self._populate_stages()
            self._update_summary()
            self.app.mark_unsaved()

    def _assign_all_to_all(self):
        if messagebox.askyesno("Assign All", "Assign ALL tracks to ALL stages?"):
            self.app.music_manager.assign_all_tracks_to_all_stages()
            self._render_playlist()
            self._populate_stages()
            self._update_summary()
            self.app.mark_unsaved()

    def _on_exclude_change(self):
        self.app.music_manager.set_exclude_vanilla(self.exclude_var.get())
        self._update_summary()
        self.app.mark_unsaved()

    # Audio playback methods
    def _on_track_click(self, event):
        """When user clicks a track while music is already playing,
        auto-play the newly selected track."""
        if self._is_playing:
            # Short delay so the listbox selection updates first
            self.after(50, self._play_selected)

    def _toggle_playback(self):
        """Toggle between play and stop."""
        if self._is_playing:
            self._stop_playback()
        else:
            self._play_selected()

    def _play_selected(self):
        """Play the selected track (in background thread to avoid UI freeze)."""
        track = self._get_selected_track()
        if not track:
            self.player_status.configure(text="Select a track first", text_color="#e94560")
            self.after(3000, lambda: self.player_status.configure(text=""))
            return

        # Stop any current playback first to prevent concurrent threads
        if self._is_playing:
            audio_player.stop()
            self._is_playing = False

        # Cancel any stale poll / seek-bar loops from previous playback
        if hasattr(self, '_poll_after_id') and self._poll_after_id:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None
        if hasattr(self, '_seek_after_id') and self._seek_after_id:
            try:
                self.after_cancel(self._seek_after_id)
            except Exception:
                pass
            self._seek_after_id = None

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
                self.after(0, lambda: self._on_play_result(result, track))

        threading.Thread(target=_play_bg, daemon=True).start()

    def _on_play_result(self, result, track):
        """Handle play result on the main thread."""
        success, msg = result
        color = "#2fa572" if success else "#e94560"
        self.player_status.configure(text=msg, text_color=color)
        if success:
            self._is_playing = True
            self.play_toggle_btn.configure(
                text="■  Stop", fg_color="#b02a2a", hover_color="#8a1f1f")
            # Start polling for end-of-track to reset button state
            self._poll_playback_end()
            # Start seek bar updates
            dur = audio_player.get_duration()
            self.seek_duration_label.configure(text=self._fmt_time(int(dur)))
            self.seek_slider.set(0)
            self._update_seek_bar()
        else:
            self.after(5000, lambda: self.player_status.configure(text=""))

    def _poll_playback_end(self):
        """Periodically check if playback ended so the button resets."""
        self._poll_after_id = None
        if not self._is_playing:
            return
        if not audio_player.is_playing:
            self._is_playing = False
            self.play_toggle_btn.configure(
                text="\u25b6  Play", fg_color="#2fa572", hover_color="#106a43")
            self.player_status.configure(text="")
            return
        self._poll_after_id = self.after(500, self._poll_playback_end)

    def _stop_playback(self):
        audio_player.stop()
        self._is_playing = False
        # Cancel stale timer loops
        for attr in ('_poll_after_id', '_seek_after_id'):
            aid = getattr(self, attr, None)
            if aid:
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
        self.play_toggle_btn.configure(
            text="▶  Play", fg_color="#2fa572", hover_color="#106a43")
        self.player_status.configure(text="Stopped", text_color="#888888")
        self.seek_slider.set(0)
        self.seek_label.configure(text="0:00")
        self.seek_duration_label.configure(text="0:00")
        self.after(2000, lambda: self.player_status.configure(text=""))

    def _on_volume_change(self, value):
        new_volume = max(0.0, min(1.0, float(value) / 100.0))
        if abs(new_volume - self._pending_volume_value) < 0.01:
            return
        self._pending_volume_value = new_volume
        audio_player.set_volume(self._pending_volume_value)

    def _on_seek_drag(self, value):
        """Called continuously as the seek slider is dragged."""
        dur = audio_player.get_duration()
        if dur > 0:
            secs = int(value / 100.0 * dur)
            self.seek_label.configure(text=self._fmt_time(secs))

    def _on_seek_release(self, event):
        """Seek to position when slider is released."""
        self._seek_dragging = False
        dur = audio_player.get_duration()
        if dur > 0 and self._is_playing:
            pos = self.seek_slider.get() / 100.0 * dur
            audio_player.seek(pos)

    def _update_seek_bar(self):
        """Periodically update the seek slider to reflect playback position."""
        self._seek_after_id = None
        if not self._is_playing or self._seek_dragging:
            return
        dur = audio_player.get_duration()
        pos = audio_player.get_position()
        if dur > 0:
            pct = min(100.0, pos / dur * 100.0)
            self.seek_slider.set(pct)
            self.seek_label.configure(text=self._fmt_time(int(pos)))
            self.seek_duration_label.configure(text=self._fmt_time(int(dur)))
        self._seek_after_id = self.after(500, self._update_seek_bar)

    @staticmethod
    def _fmt_time(seconds: int) -> str:
        m, s = divmod(max(0, seconds), 60)
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
        if summary["stages_configured"] == 0:
            messagebox.showwarning("Warning", "No tracks assigned to any stages yet.")
            return

        try:
            result = self.app.music_manager.save_assignments(settings.mods_path)
            msg = f"Music configuration saved!\n\n"
            msg += f"Stages: {result['stages_configured']}\n"
            msg += f"Assignments: {result['tracks_assigned']}\n"
            if result.get("menu_music_set"):
                msg += f"\nMain menu music has been set!"
            if result.get("prc_updated"):
                msg += f"\nPRC updated in: {result['output_mod']}"
            logger.info("Music", f"Saved: {result['stages_configured']} stages, {result['tracks_assigned']} tracks")
            self.app.mark_saved()
            messagebox.showinfo("Saved", msg)
        except Exception as e:
            logger.error("Music", f"Save failed: {e}")
            messagebox.showerror("Error", f"Failed to save: {e}")
