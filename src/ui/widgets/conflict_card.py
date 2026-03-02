import customtkinter as ctk
from src.models.conflict import FileConflict, ConflictSeverity, ResolutionStrategy
from src.ui import theme


SEVERITY_COLORS = {
    ConflictSeverity.CRITICAL: theme.DANGER_CRITICAL,
    ConflictSeverity.HIGH: theme.ACCENT,
    ConflictSeverity.MEDIUM: theme.WARNING_MEDIUM,
    ConflictSeverity.LOW: theme.TEXT_DIM,
}

SEVERITY_LABELS = {
    ConflictSeverity.CRITICAL: "CRITICAL",
    ConflictSeverity.HIGH: "HIGH",
    ConflictSeverity.MEDIUM: "MEDIUM",
    ConflictSeverity.LOW: "LOW",
}


class ConflictCard(ctk.CTkFrame):
    def __init__(self, parent, conflict: FileConflict,
                 on_merge=None, on_keep=None, on_ignore=None, **kwargs):
        super().__init__(parent, fg_color=theme.BG_CARD, corner_radius=8, **kwargs)
        self.conflict = conflict

        color = SEVERITY_COLORS.get(conflict.severity, theme.TEXT_DIM)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 5))

        severity_badge = ctk.CTkLabel(
            header, text=SEVERITY_LABELS.get(conflict.severity, ""),
            font=ctk.CTkFont(size=theme.FONT_CAPTION, weight="bold"),
            text_color=color,
        )
        severity_badge.pack(side="left", padx=(0, 10))

        path_label = ctk.CTkLabel(
            header, text=conflict.display_path or conflict.relative_path,
            font=ctk.CTkFont(size=theme.FONT_BODY_EMPHASIS, weight="bold"),
            text_color=theme.TEXT_PRIMARY, anchor="w",
        )
        path_label.pack(side="left", fill="x", expand=True)

        if conflict.resolved:
            resolved_badge = ctk.CTkLabel(
                header, text="RESOLVED",
                font=ctk.CTkFont(size=theme.FONT_CAPTION, weight="bold"),
                text_color=theme.SUCCESS,
            )
            resolved_badge.pack(side="right")

        if getattr(conflict, "slot_summary", ""):
            slot_label = ctk.CTkLabel(
                self,
                text=conflict.slot_summary,
                font=ctk.CTkFont(size=theme.FONT_BODY),
                text_color=theme.TEXT_MERGED,
                anchor="w",
                justify="left",
                wraplength=theme.WRAP_MEDIUM,
            )
            slot_label.pack(fill="x", padx=12, pady=(0, 5))

        mods_frame = ctk.CTkFrame(self, fg_color="transparent")
        mods_frame.pack(fill="x", padx=12, pady=(0, 5))

        mods_label = ctk.CTkLabel(
            mods_frame, text="Conflicting mods:",
            font=ctk.CTkFont(size=theme.FONT_BODY),
            text_color=theme.TEXT_HINT, anchor="w",
        )
        mods_label.pack(anchor="w")

        for mod_name in conflict.mods_involved:
            detail = str(getattr(conflict, "mod_display_labels", {}).get(mod_name, "") or "").strip()
            label_text = f"  - {mod_name}"
            if detail:
                label_text += f" [{detail}]"
            mod_item = ctk.CTkLabel(
                mods_frame, text=label_text,
                font=ctk.CTkFont(size=theme.FONT_BODY_MEDIUM),
                text_color=theme.TEXT_SECONDARY, anchor="w",
            )
            mod_item.pack(anchor="w")

        if conflict.is_mergeable:
            if conflict.resolved and conflict.resolution == ResolutionStrategy.MERGE:
                merge_text = "Already merged"
            elif conflict.resolved:
                merge_text = "Already resolved"
            else:
                merge_text = "Can be merged automatically (non-overlapping entries)"
            merge_info = ctk.CTkLabel(
                self, text=merge_text,
                font=ctk.CTkFont(size=theme.FONT_BODY),
                text_color=theme.SUCCESS, anchor="w",
            )
            merge_info.pack(fill="x", padx=12, pady=(0, 5))

        if not conflict.resolved:
            btn_frame = ctk.CTkFrame(self, fg_color="transparent")
            btn_frame.pack(fill="x", padx=12, pady=(0, 10))

            if conflict.is_mergeable and on_merge:
                merge_btn = ctk.CTkButton(
                    btn_frame, text="Merge All", width=100,
                    fg_color=theme.SUCCESS, hover_color=theme.HOVER_SUCCESS,
                    command=lambda: on_merge(conflict),
                )
                merge_btn.pack(side="left", padx=(0, 5))

            if on_keep and len(conflict.mods_involved) > 1:
                for mod_name in conflict.mods_involved:
                    keep_btn = ctk.CTkButton(
                        btn_frame, text=f"Keep {mod_name[:20]}", width=130,
                        command=lambda mn=mod_name: on_keep(conflict, mn),
                    )
                    keep_btn.pack(side="left", padx=(0, 5))

            if on_ignore:
                ignore_btn = ctk.CTkButton(
                    btn_frame, text="Ignore", width=80,
                    fg_color=theme.BTN_NEUTRAL, hover_color=theme.HOVER_NEUTRAL,
                    command=lambda: on_ignore(conflict),
                )
                ignore_btn.pack(side="left", padx=(0, 5))
