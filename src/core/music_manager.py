"""Music track discovery, stage assignment, playlist management, and PRC save."""
import json
import os
import shutil
from pathlib import Path
from typing import Optional
from src.models.music import MusicTrack, StagePlaylist, StageInfo
from src.constants import VANILLA_STAGES
from src.utils.xmsbt_parser import parse_xmsbt
from src.utils.file_utils import backup_file
from src.config import CONFIG_DIR
from src.utils.logger import logger


class MusicManager:
    def __init__(self):
        self.tracks: list[MusicTrack] = []
        self.stage_playlists: dict[str, StagePlaylist] = {}
        self.exclude_vanilla = False

    def discover_tracks(self, mods_root: Path) -> list[MusicTrack]:
        """Discover all custom music tracks across all mod folders."""
        self.tracks = []
        seen_ids = set()

        if not mods_root.exists():
            return self.tracks

        for mod_folder in sorted(mods_root.iterdir()):
            if not mod_folder.is_dir() or mod_folder.name.startswith(".") or mod_folder.name.startswith("_"):
                continue

            # Scan for nus3audio files
            for audio_file in mod_folder.rglob("*.nus3audio"):
                track_id = audio_file.stem  # Filename without extension
                if track_id in seen_ids:
                    continue
                seen_ids.add(track_id)

                try:
                    fsize = audio_file.stat().st_size
                except OSError:
                    fsize = 0

                track = MusicTrack(
                    track_id=track_id,
                    file_path=audio_file,
                    source_mod=mod_folder.name,
                    file_size=fsize,
                    is_custom=True,
                )
                self.tracks.append(track)

            # Try to get track names from XMSBT files
            self._load_track_names_from_mod(mod_folder)

        # Load saved assignments if they exist
        self._load_saved_assignments()

        return self.tracks

    def _load_track_names_from_mod(self, mod_folder: Path) -> None:
        """Load track display names from XMSBT/MSBT files in a mod."""
        for xmsbt_file in mod_folder.rglob("*.xmsbt"):
            if "bgm" in xmsbt_file.name.lower() or "msg_bgm" in xmsbt_file.name.lower():
                entries = parse_xmsbt(xmsbt_file)
                for label, text in entries.items():
                    for track in self.tracks:
                        if track.track_id in label or label.endswith(track.track_id):
                            if not track.display_name:
                                track.display_name = text

    def get_stage_list(self) -> list[StageInfo]:
        """Get list of all vanilla stages."""
        return [
            StageInfo(stage_id=sid, stage_name=sname)
            for sid, sname in sorted(VANILLA_STAGES.items(), key=lambda x: x[1])
        ]

    def get_tracks_for_stage(self, stage_id: str) -> list[MusicTrack]:
        """Get tracks assigned to a specific stage."""
        if stage_id in self.stage_playlists:
            return self.stage_playlists[stage_id].tracks
        return []

    def assign_track_to_stage(self, track: MusicTrack, stage_id: str) -> None:
        """Assign a music track to a stage."""
        if stage_id not in self.stage_playlists:
            stage_name = VANILLA_STAGES.get(stage_id, stage_id)
            self.stage_playlists[stage_id] = StagePlaylist(
                stage_id=stage_id,
                stage_name=stage_name,
            )

        playlist = self.stage_playlists[stage_id]
        if not any(t.track_id == track.track_id for t in playlist.tracks):
            playlist.tracks.append(track)

    def remove_track_from_stage(self, track_id: str, stage_id: str) -> None:
        """Remove a track from a stage's playlist."""
        if stage_id in self.stage_playlists:
            playlist = self.stage_playlists[stage_id]
            playlist.tracks = [t for t in playlist.tracks if t.track_id != track_id]

    def assign_track_to_all_stages(self, track: MusicTrack) -> None:
        """Assign a track to all stages."""
        for stage_id in VANILLA_STAGES:
            self.assign_track_to_stage(track, stage_id)

    def assign_all_tracks_to_all_stages(self) -> None:
        """Assign all discovered tracks to all stages."""
        for track in self.tracks:
            self.assign_track_to_all_stages(track)

    def clear_stage(self, stage_id: str) -> None:
        """Clear all tracks from a stage."""
        if stage_id in self.stage_playlists:
            self.stage_playlists[stage_id].tracks = []

    def set_exclude_vanilla(self, exclude: bool) -> None:
        """Toggle exclusion of vanilla/core music."""
        self.exclude_vanilla = exclude

    def move_track_up(self, stage_id: str, track_id: str) -> None:
        """Move a track up in a stage's playlist."""
        if stage_id not in self.stage_playlists:
            return
        tracks = self.stage_playlists[stage_id].tracks
        for i, t in enumerate(tracks):
            if t.track_id == track_id and i > 0:
                tracks[i], tracks[i-1] = tracks[i-1], tracks[i]
                break

    def move_track_down(self, stage_id: str, track_id: str) -> None:
        """Move a track down in a stage's playlist."""
        if stage_id not in self.stage_playlists:
            return
        tracks = self.stage_playlists[stage_id].tracks
        for i, t in enumerate(tracks):
            if t.track_id == track_id and i < len(tracks) - 1:
                tracks[i], tracks[i+1] = tracks[i+1], tracks[i]
                break

    def get_all_available_tracks(self) -> list[MusicTrack]:
        """Get all discovered tracks."""
        return self.tracks

    # === Save / Apply Methods ===

    def save_assignments(self, mods_root: Path) -> dict:
        """
        Save music assignments by:
        1. Persisting the assignment config to JSON
        2. Generating/modifying the ui_bgm_db.prc and ui_stage_db.prc in a
           _MusicConfig mod folder that ARCropolis will load
        Returns a summary dict.
        """
        result = {
            "stages_configured": 0,
            "tracks_assigned": 0,
            "output_mod": "",
            "prc_updated": False,
            "config_saved": False,
        }

        # Save the JSON config for persistence
        self._save_assignment_config(mods_root)
        result["config_saved"] = True

        # Find the music source mod that has ui_bgm_db.prc and ui_stage_db.prc
        source_mod = self._find_music_source_mod(mods_root)

        if source_mod:
            # Update the PRC files in the source mod
            prc_result = self._apply_prc_assignments(source_mod, mods_root)
            result.update(prc_result)
        else:
            # No source mod with PRC files found - create a standalone config mod
            config_mod = self._create_config_mod(mods_root)
            result["output_mod"] = str(config_mod)

        # Count assignments
        for stage_id, playlist in self.stage_playlists.items():
            if playlist.tracks:
                result["stages_configured"] += 1
                result["tracks_assigned"] += len(playlist.tracks)

        return result

    def _find_music_source_mod(self, mods_root: Path) -> Optional[Path]:
        """Find a mod folder that contains ui_bgm_db.prc (the BGM database)."""
        for mod_folder in sorted(mods_root.iterdir()):
            if not mod_folder.is_dir() or mod_folder.name.startswith("."):
                continue
            bgm_db = mod_folder / "ui" / "param" / "database" / "ui_bgm_db.prc"
            if bgm_db.exists():
                return mod_folder
        return None

    def _apply_prc_assignments(self, source_mod: Path, mods_root: Path) -> dict:
        """Apply stage BGM assignments by modifying the ui_stage_db.prc in the source mod."""
        result = {"prc_updated": False, "output_mod": str(source_mod)}

        stage_db_path = source_mod / "ui" / "param" / "database" / "ui_stage_db.prc"
        bgm_db_path = source_mod / "ui" / "param" / "database" / "ui_bgm_db.prc"

        if not stage_db_path.exists() or not bgm_db_path.exists():
            return result

        try:
            import pyprc

            # Backup originals
            backup_file(stage_db_path)

            # Load the BGM database to get valid BGM IDs
            bgm_prc = pyprc.param(str(bgm_db_path))
            bgm_db = list(bgm_prc)[0][1]

            # Build a set of all custom BGM IDs from the database
            custom_bgm_ids = []
            for entry in bgm_db:
                try:
                    ui_bgm_id = entry['ui_bgm_id'].value
                    custom_bgm_ids.append(ui_bgm_id)
                except (KeyError, AttributeError):
                    continue

            if not custom_bgm_ids:
                return result

            # Load the stage database
            stage_prc = pyprc.param(str(stage_db_path))
            stage_db = list(stage_prc)[0][1]

            # Update each stage's BGM list
            modified = False
            for stage_entry in stage_db:
                try:
                    stage_id_val = str(stage_entry['ui_stage_id'].value)
                except (KeyError, AttributeError):
                    continue

                # Find the matching stage in our playlists
                target_stage = None
                for sid in VANILLA_STAGES:
                    if sid in stage_id_val or stage_id_val in sid:
                        target_stage = sid
                        break

                if not target_stage:
                    continue

                # Get the BGM set list for this stage
                try:
                    bgm_set_list = stage_entry['bgm_set_list']
                except (KeyError, AttributeError):
                    continue

                assigned_tracks = self.get_tracks_for_stage(target_stage)

                if assigned_tracks or self.exclude_vanilla:
                    # Get track IDs that should be assigned
                    assigned_ids = set()
                    for track in assigned_tracks:
                        # Match track_id to a BGM ID in the database
                        for bgm_id in custom_bgm_ids:
                            bgm_str = str(bgm_id)
                            if track.track_id in bgm_str or bgm_str.endswith(track.track_id):
                                assigned_ids.add(bgm_id)
                                break

                    # If we have specific assignments, apply them
                    if assigned_ids:
                        # Update the BGM set list entries
                        current_entries = list(bgm_set_list)
                        new_entries = []

                        if not self.exclude_vanilla:
                            # Keep existing entries
                            new_entries = current_entries[:]

                        # Add new entries by cloning the first entry and modifying
                        if current_entries:
                            for bgm_id in assigned_ids:
                                # Check if already in list
                                already_exists = False
                                for existing in new_entries:
                                    try:
                                        if existing['ui_bgm_id'].value == bgm_id:
                                            already_exists = True
                                            break
                                    except (KeyError, AttributeError):
                                        continue

                                if not already_exists:
                                    new_entry = current_entries[0].clone()
                                    try:
                                        new_entry['ui_bgm_id'].value = bgm_id
                                        new_entry['incidence'].value = 50
                                    except (KeyError, AttributeError):
                                        pass
                                    new_entries.append(new_entry)

                            if len(new_entries) != len(current_entries):
                                bgm_set_list.set_list(new_entries)
                                modified = True

            if modified:
                stage_prc.save(str(stage_db_path))
                result["prc_updated"] = True

        except ImportError:
            logger.warn("MusicManager", "pyprc not installed - PRC stage assignments not applied. Install with: pip install pyprc")
        except Exception as e:
            logger.error("MusicManager", f"Failed to update stage DB: {e}")

        return result

    def _create_config_mod(self, mods_root: Path) -> Path:
        """Create a _MusicConfig mod folder with assignment metadata."""
        config_mod = mods_root / "_MusicConfig"
        config_mod.mkdir(exist_ok=True)

        config = {
            "description": "Auto-generated music configuration by SSBU Mod Manager",
            "exclude_vanilla": self.exclude_vanilla,
            "assignments": {},
        }

        for stage_id, playlist in self.stage_playlists.items():
            if playlist.tracks:
                config["assignments"][stage_id] = [
                    {
                        "track_id": t.track_id,
                        "display_name": t.display_name or t.track_id,
                        "source_mod": t.source_mod,
                    }
                    for t in playlist.tracks
                ]

        config_file = config_mod / "music_config.json"
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

        return config_mod

    def _save_assignment_config(self, mods_root: Path) -> None:
        """Save current assignments to a persistent JSON config."""
        config_dir = CONFIG_DIR
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "music_assignments.json"

        data = {
            "exclude_vanilla": self.exclude_vanilla,
            "assignments": {},
        }

        for stage_id, playlist in self.stage_playlists.items():
            if playlist.tracks:
                data["assignments"][stage_id] = [t.track_id for t in playlist.tracks]

        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.error("Music", f"Failed to save assignment config: {e}")

    def _load_saved_assignments(self) -> None:
        """Load previously saved assignments from persistent config."""
        config_file = CONFIG_DIR / "music_assignments.json"
        if not config_file.exists():
            return

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.exclude_vanilla = data.get("exclude_vanilla", False)

            # Build a track lookup by track_id
            track_lookup = {t.track_id: t for t in self.tracks}

            for stage_id, track_ids in data.get("assignments", {}).items():
                for track_id in track_ids:
                    if track_id in track_lookup:
                        self.assign_track_to_stage(track_lookup[track_id], stage_id)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warn("Music", f"Failed to load saved assignments: {e}")

    def get_assignment_summary(self) -> dict:
        """Get a summary of current assignments."""
        total_stages = 0
        total_tracks = 0
        stages_with_music = []

        for stage_id, playlist in self.stage_playlists.items():
            if playlist.tracks:
                total_stages += 1
                total_tracks += len(playlist.tracks)
                stages_with_music.append(playlist.stage_name)

        return {
            "stages_configured": total_stages,
            "total_assignments": total_tracks,
            "stages_with_music": stages_with_music,
            "exclude_vanilla": self.exclude_vanilla,
        }
