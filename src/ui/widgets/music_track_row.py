import customtkinter as ctk
from src.models.music import MusicTrack
from src.ui import theme
from src.utils.file_utils import format_size


class MusicTrackRow(ctk.CTkFrame):
    def __init__(self, parent, track: MusicTrack, show_actions=True,
                 on_add=None, on_remove=None, on_move_up=None, on_move_down=None,
                 **kwargs):
        super().__init__(parent, fg_color=theme.BG_CARD, corner_radius=6, **kwargs)
        self.track = track

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=6)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)

        display = track.display_name if track.display_name else track.track_id
        name_label = ctk.CTkLabel(
            info, text=display,
            font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS),
            text_color=theme.TEXT_PRIMARY, anchor="w",
        )
        name_label.pack(anchor="w")

        detail_parts = [f"From: {track.source_mod}"] if track.source_mod else []
        detail_parts.append(format_size(track.file_size))
        detail_label = ctk.CTkLabel(
            info, text=" | ".join(detail_parts),
            font=ctk.CTkFont(size=theme.FONT_BODY),
            text_color=theme.TEXT_DIM, anchor="w",
        )
        detail_label.pack(anchor="w")

        if show_actions:
            btn_frame = ctk.CTkFrame(row, fg_color="transparent")
            btn_frame.pack(side="right")

            if on_move_up:
                up_btn = ctk.CTkButton(btn_frame, text="^", width=30, height=28,
                                       command=lambda: on_move_up(track))
                up_btn.pack(side="left", padx=2)

            if on_move_down:
                down_btn = ctk.CTkButton(btn_frame, text="v", width=30, height=28,
                                         command=lambda: on_move_down(track))
                down_btn.pack(side="left", padx=2)

            if on_remove:
                rm_btn = ctk.CTkButton(btn_frame, text="X", width=30, height=28,
                                       fg_color=theme.DANGER, hover_color=theme.HOVER_DANGER,
                                       command=lambda: on_remove(track))
                rm_btn.pack(side="left", padx=2)

            if on_add:
                add_btn = ctk.CTkButton(btn_frame, text="+", width=30, height=28,
                                        fg_color=theme.SUCCESS, hover_color=theme.HOVER_SUCCESS,
                                        command=lambda: on_add(track))
                add_btn.pack(side="left", padx=2)
