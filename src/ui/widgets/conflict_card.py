"""Conflict card widget for the conflicts page."""
import customtkinter as ctk
from src.models.conflict import FileConflict, ConflictSeverity


SEVERITY_COLORS = {
    ConflictSeverity.CRITICAL: "#ff2222",
    ConflictSeverity.HIGH: "#e94560",
    ConflictSeverity.MEDIUM: "#f0a030",
    ConflictSeverity.LOW: "#888888",
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
        super().__init__(parent, fg_color="#242438", corner_radius=8, **kwargs)
        self.conflict = conflict

        color = SEVERITY_COLORS.get(conflict.severity, "#888888")

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 5))

        severity_badge = ctk.CTkLabel(
            header, text=SEVERITY_LABELS.get(conflict.severity, ""),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=color,
        )
        severity_badge.pack(side="left", padx=(0, 10))

        path_label = ctk.CTkLabel(
            header, text=conflict.relative_path,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="white", anchor="w",
        )
        path_label.pack(side="left", fill="x", expand=True)

        if conflict.resolved:
            resolved_badge = ctk.CTkLabel(
                header, text="RESOLVED",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="#2fa572",
            )
            resolved_badge.pack(side="right")

        # Conflicting mods
        mods_frame = ctk.CTkFrame(self, fg_color="transparent")
        mods_frame.pack(fill="x", padx=12, pady=(0, 5))

        mods_label = ctk.CTkLabel(
            mods_frame, text="Conflicting mods:",
            font=ctk.CTkFont(size=11),
            text_color="#aaaaaa", anchor="w",
        )
        mods_label.pack(anchor="w")

        for mod_name in conflict.mods_involved:
            mod_item = ctk.CTkLabel(
                mods_frame, text=f"  - {mod_name}",
                font=ctk.CTkFont(size=12),
                text_color="#cccccc", anchor="w",
            )
            mod_item.pack(anchor="w")

        # Status info
        if conflict.is_mergeable:
            merge_info = ctk.CTkLabel(
                self, text="Auto-mergeable (non-overlapping entries can be combined)",
                font=ctk.CTkFont(size=11),
                text_color="#2fa572", anchor="w",
            )
            merge_info.pack(fill="x", padx=12, pady=(0, 5))

        # Action buttons
        if not conflict.resolved:
            btn_frame = ctk.CTkFrame(self, fg_color="transparent")
            btn_frame.pack(fill="x", padx=12, pady=(0, 10))

            if conflict.is_mergeable and on_merge:
                merge_btn = ctk.CTkButton(
                    btn_frame, text="Merge All", width=100,
                    fg_color="#2fa572", hover_color="#106a43",
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
                    fg_color="#555555", hover_color="#444444",
                    command=lambda: on_ignore(conflict),
                )
                ignore_btn.pack(side="left", padx=(0, 5))
