"""Music track discovery, stage assignment, playlist management, and PRC save."""
import json
import re
import shutil
import threading
from pathlib import Path
from typing import Optional
from src.models.music import (
    MusicReplacementAssignment,
    MusicTrack,
    StageInfo,
    StagePlaylist,
    StageTrackSlot,
)
from src.constants import VANILLA_STAGES
from src.utils.xmsbt_parser import parse_xmsbt, extract_entries_from_msbt
from src.utils.file_utils import backup_file
from src.utils.resource_path import resource_path
from src.config import CONFIG_DIR
from src.utils.logger import logger


# Keys are lowercase prefixes found in SSBU internal BGM filenames.
# Values are the pretty-printed franchise / game name.
_SERIES_MAP: dict[str, str] = {
    # Nintendo
    "mario":            "Mario",
    "mario64":          "Mario 64",
    "mariokart":        "Mario Kart",
    "mariopaint":       "Mario Paint",
    "mariotennis":      "Mario Tennis",
    "smb":              "Super Mario Bros.",
    "nsmb":             "New Super Mario Bros.",
    "3dworld":          "Super Mario 3D World",
    "galaxy":           "Super Mario Galaxy",
    "odyssey":          "Super Mario Odyssey",
    "sunshine":         "Super Mario Sunshine",
    "papermario":       "Paper Mario",
    "luigi":            "Luigi's Mansion",
    "dk":               "Donkey Kong",
    "donkey_kong":      "Donkey Kong",
    "zelda":            "Zelda",
    "zelda_ocarina":    "Ocarina of Time",
    "zelda_majora":     "Majora's Mask",
    "zelda_wind":       "Wind Waker",
    "zelda_tp":         "Twilight Princess",
    "zelda_ss":         "Skyward Sword",
    "zelda_botw":       "Breath of the Wild",
    "zelda_totk":       "Tears of the Kingdom",
    "metroid":          "Metroid",
    "kirby":            "Kirby",
    "starfox":          "Star Fox",
    "star_fox":         "Star Fox",
    "fzero":            "F-Zero",
    "f_zero":           "F-Zero",
    "pokemon":          "Pokemon",
    "poke":             "Pokemon",
    "pikmin":           "Pikmin",
    "animal_crossing":  "Animal Crossing",
    "splatoon":         "Splatoon",
    "xenoblade":        "Xenoblade Chronicles",
    "fire_emblem":      "Fire Emblem",
    "fe":               "Fire Emblem",
    "kid_icarus":       "Kid Icarus",
    "palutena":         "Kid Icarus",
    "wii_fit":          "Wii Fit",
    "wii_sports":       "Wii Sports",
    "punch_out":        "Punch-Out!!",
    "arms":             "ARMS",
    "mother":           "Mother / EarthBound",
    "earthbound":       "EarthBound",
    "wario":            "WarioWare",
    "ice_climber":      "Ice Climber",
    "game_watch":       "Game & Watch",
    "balloon_fight":    "Balloon Fight",
    "duck_hunt":        "Duck Hunt",
    "mii":              "Mii",
    "tomodachi":        "Tomodachi Life",
    "ring_fit":         "Ring Fit Adventure",
    "nintendogs":       "Nintendogs",
    "brain_age":        "Brain Age",
    "pilotwings":       "Pilotwings",
    "custom_robo":      "Custom Robo",
    "famicom":          "Famicom",
    "smash":            "Super Smash Bros.",
    "menu":             "Super Smash Bros.",
    # Third-party
    "sonic":            "Sonic",
    "sonic_adventure":  "Sonic Adventure",
    "sonic_heroes":     "Sonic Heroes",
    "sonic_cd":         "Sonic CD",
    "sonic_mania":      "Sonic Mania",
    "pacman":           "Pac-Man",
    "pac_man":          "Pac-Man",
    "megaman":          "Mega Man",
    "mega_man":         "Mega Man",
    "castlevania":      "Castlevania",
    "persona":          "Persona",
    "bayonetta":        "Bayonetta",
    "street_fighter":   "Street Fighter",
    "sf":               "Street Fighter",
    "tekken":           "Tekken",
    "fatal_fury":       "Fatal Fury / KOF",
    "kof":              "King of Fighters",
    "snk":              "SNK",
    "dragon_quest":     "Dragon Quest",
    "dq":               "Dragon Quest",
    "final_fantasy":    "Final Fantasy",
    "ff":               "Final Fantasy",
    "kingdom_hearts":   "Kingdom Hearts",
    "minecraft":        "Minecraft",
    "banjo":            "Banjo-Kazooie",
    "metal_gear":       "Metal Gear",
    "mgs":              "Metal Gear Solid",
    "devil_may_cry":    "Devil May Cry",
    "dmc":              "Devil May Cry",
    "shovel_knight":    "Shovel Knight",
    "shantae":          "Shantae",
    "undertale":        "Undertale",
    "cuphead":          "Cuphead",
    "hollow_knight":    "Hollow Knight",
    "touhou":           "Touhou",
}

# Sort by key length descending so longer prefixes match first
# (e.g. "sonic_adventure" before "sonic")
_SERIES_KEYS_SORTED = sorted(_SERIES_MAP.keys(), key=len, reverse=True)

# Words that should stay lowercase in title-case output
_LOWERCASE_WORDS = {"a", "an", "and", "at", "by", "for", "from", "in",
                    "of", "on", "or", "the", "to", "vs", "with"}

NUS3AUDIO_GLOB = "*.nus3audio"
XMSBT_GLOB = "*.xmsbt"
MSBT_GLOB = "*.msbt"
TRACK_ID_PREFIX = "bgm_"
TRACK_ID_PREFIX_LENGTH = len(TRACK_ID_PREFIX)
TRACK_SERIES_SEPARATOR = "__"
TRACK_STAGE_CODE_PATTERN = r"^([A-Z]\d{2})_(.+)$"
DEFAULT_BGM_INCIDENCE = 50
MENU_STAGE_ID = "ui_stage_id_menu"
MENU_BGM_FILENAME = "bgm_z90_menu.nus3audio"
MUSIC_CONFIG_MOD_DIRNAME = "_MusicConfig"
MUSIC_CONFIG_FILENAME = "music_config.json"
ASSIGNMENTS_FILENAME = "music_assignments.json"
LIBRARY_FILENAME = "music_library.json"
REPLACEMENTS_FILENAME = "music_replacements.json"
REPLACEMENT_MANIFEST_FILENAME = "music_replacement_manifest.json"
REPLACEMENT_METADATA_FILENAME = "wifi_safe_replacements.json"
VANILLA_BGM_REFERENCE_PATH = "assets/vanilla_bgm_ids.txt"
STREAM_PREFIX = "stream;"
SOUND_BGM_PARTS = ("sound", "bgm")
MOD_FOLDER_PREFIXES_TO_SKIP = (".", "_")
TRACK_SCAN_CANCEL_LOG = "Track discovery cancelled"
BGM_MESSAGE_MARKERS = ("bgm", "msg_bgm")
BGM_LABEL_MARKERS = ("bgm_title", "bgm_menu")
BGM_SUFFIX_SEPARATOR = "_"
FINGERPRINT_ATTR_NAME = "_last_msbt_fingerprint"
UI_BGM_PREFIX = "ui_bgm_"
STREAM_SET_PREFIX = "set_"
NUS3AUDIO_SUFFIX = ".nus3audio"
STAGE_ID_TOKEN = "ui_stage_id_"
LEGACY_STAGE_ID_TOKEN = "ui_stage_"


def beautify_track_name(track_id: str) -> str:
    """Convert a raw SSBU BGM filename into a human-friendly display name.

    Example transforms:
      bgm_sonic_adventure__mechanical_resonance -> Mechanical Resonance [Sonic Adventure]
      bgm_zelda_overworld -> Overworld [Zelda]
      bgm_T09_battle_kirby01 -> Battle Kirby 01 [Stage T09]
      bgm_menu_select -> Menu Select
    """
    name = track_id

    if name.lower().startswith(TRACK_ID_PREFIX):
        name = name[TRACK_ID_PREFIX_LENGTH:]

    series_label: str | None = None
    song_part: str = name

    if TRACK_SERIES_SEPARATOR in name:
        parts = name.split(TRACK_SERIES_SEPARATOR, 1)
        raw_series = parts[0]
        song_part = parts[1]
        series_label = _SERIES_MAP.get(raw_series.lower(),
                                       raw_series.replace("_", " ").strip().title())
    else:
        lower = name.lower()
        for key in _SERIES_KEYS_SORTED:
            if lower.startswith(key + "_") and len(name) > len(key) + 1:
                series_label = _SERIES_MAP[key]
                song_part = name[len(key) + 1:]
                break

    stage_match = re.match(TRACK_STAGE_CODE_PATTERN, song_part, re.IGNORECASE)
    if stage_match and not series_label:
        series_label = f"Stage {stage_match.group(1).upper()}"
        song_part = stage_match.group(2)

    song_name = song_part.replace("_", " ").strip()
    song_name = re.sub(r"\s+", " ", song_name)

    words = song_name.split()
    titled: list[str] = []
    for i, w in enumerate(words):
        if i == 0 or i == len(words) - 1 or w.lower() not in _LOWERCASE_WORDS:
            titled.append(w.capitalize())
        else:
            titled.append(w.lower())
    song_name = " ".join(titled) if titled else song_name

    if not song_name:
        song_name = track_id

    if series_label:
        return f"{song_name}  [{series_label}]"
    return song_name


def infer_bgm_filename(ui_bgm_id: str, stream_set_id: str = "") -> str:
    """Infer a concrete `bgm_*.nus3audio` filename for a stage slot."""
    stream_value = (stream_set_id or "").strip()
    if stream_value:
        trimmed = stream_value
        if trimmed.lower().startswith(STREAM_SET_PREFIX):
            trimmed = trimmed[len(STREAM_SET_PREFIX):]
        if trimmed.lower().startswith(TRACK_ID_PREFIX):
            trimmed = trimmed[len(TRACK_ID_PREFIX):]
        if trimmed:
            return f"{TRACK_ID_PREFIX}{trimmed}{NUS3AUDIO_SUFFIX}"

    bgm_value = (ui_bgm_id or "").strip()
    if bgm_value.lower().startswith(UI_BGM_PREFIX):
        bgm_value = bgm_value[len(UI_BGM_PREFIX):]
    elif bgm_value.lower().startswith(TRACK_ID_PREFIX):
        bgm_value = bgm_value[len(TRACK_ID_PREFIX):]

    if not bgm_value:
        return ""
    return f"{TRACK_ID_PREFIX}{bgm_value}{NUS3AUDIO_SUFFIX}"


def normalize_stage_id(stage_id: str) -> str:
    cleaned = (stage_id or "").strip()
    if cleaned.startswith(LEGACY_STAGE_ID_TOKEN):
        cleaned = cleaned.replace(LEGACY_STAGE_ID_TOKEN, STAGE_ID_TOKEN, 1)
    return cleaned


class MusicManager:
    def __init__(self):
        self.tracks: list[MusicTrack] = []
        self.stage_playlists: dict[str, StagePlaylist] = {}
        self.stage_slots: dict[str, list[StageTrackSlot]] = {}
        self.replacement_assignments: dict[str, dict[str, MusicReplacementAssignment]] = {}
        self.exclude_vanilla = False
        self.favorite_track_ids: set[str] = set()
        self._library_loaded = False
        self._vanilla_bgm_ids: set[str] | None = None
        self._slot_source_mod: Path | None = None

    @staticmethod
    def _is_supported_track_file(file_path: Path) -> bool:
        return file_path.suffix.lower() == ".nus3audio"

    @staticmethod
    def _scan_cancelled(cancel_event: Optional[threading.Event]) -> bool:
        try:
            return cancel_event is not None and bool(cancel_event.is_set())
        except Exception:
            return False

    @staticmethod
    def _is_skipped_mod_folder(mod_folder: Path) -> bool:
        return mod_folder.name.startswith(MOD_FOLDER_PREFIXES_TO_SKIP)

    def _scan_should_abort(self, cancel_event: Optional[threading.Event]) -> bool:
        if not self._scan_cancelled(cancel_event):
            return False
        logger.info("MusicManager", TRACK_SCAN_CANCEL_LOG)
        return True

    def _load_vanilla_bgm_ids(self) -> set[str]:
        if self._vanilla_bgm_ids is not None:
            return self._vanilla_bgm_ids

        ids: set[str] = set()
        try:
            ref_path = Path(resource_path(VANILLA_BGM_REFERENCE_PATH))
            if ref_path.exists():
                with open(ref_path, "r", encoding="utf-8") as handle:
                    ids = {
                        str(line).strip().lower()
                        for line in handle
                        if str(line).strip()
                    }
        except OSError as exc:
            logger.warn("MusicManager", f"Failed to load vanilla BGM reference: {exc}")

        self._vanilla_bgm_ids = ids
        return ids

    @staticmethod
    def _safe_field_str(entry, field: str) -> str:
        try:
            return str(entry[field].value)
        except Exception:
            return ""

    @staticmethod
    def _safe_field_int(entry, field: str, default: int = 0) -> int:
        try:
            return int(entry[field].value)
        except Exception:
            return default

    def _resolve_stage_id(self, raw_stage_id: str) -> str:
        normalized = normalize_stage_id(raw_stage_id)
        if normalized in VANILLA_STAGES:
            return normalized

        normalized_suffix = normalized.replace(STAGE_ID_TOKEN, "", 1)
        for stage_id in VANILLA_STAGES:
            if stage_id == normalized:
                return stage_id
            if normalized and (normalized in stage_id or stage_id in normalized):
                return stage_id
            if stage_id.replace(STAGE_ID_TOKEN, "", 1) == normalized_suffix:
                return stage_id
        return normalized

    def discover_tracks(
        self,
        mods_root: Path,
        cancel_event: Optional[threading.Event] = None,
        parse_binary_msbt: bool = True,
        generate_msbt_overlays: bool = True,
    ) -> list[MusicTrack]:
        """Discover all custom music tracks across all mod folders.

        ``parse_binary_msbt`` and ``generate_msbt_overlays`` are expensive and
        should only be enabled for explicit full rescans.
        """
        self._load_library_preferences()
        self.tracks = []
        seen_ids = set()

        if not mods_root.exists():
            return self.tracks

        for mod_folder in sorted(mods_root.iterdir()):
            if self._scan_should_abort(cancel_event):
                return self.tracks
            if not mod_folder.is_dir() or self._is_skipped_mod_folder(mod_folder):
                continue

            for audio_file in mod_folder.rglob(NUS3AUDIO_GLOB):
                if self._scan_should_abort(cancel_event):
                    return self.tracks
                if not self._is_supported_track_file(audio_file):
                    continue
                track_id = audio_file.stem
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
                    is_favorite=track_id in self.favorite_track_ids,
                )
                self.tracks.append(track)

            if self._scan_should_abort(cancel_event):
                return self.tracks
            self._load_track_names_from_mod(
                mod_folder,
                cancel_event=cancel_event,
                parse_binary_msbt=parse_binary_msbt,
            )

        if self._scan_should_abort(cancel_event):
            return self.tracks

        if generate_msbt_overlays:
            if self._scan_should_abort(cancel_event):
                return self.tracks
            self._auto_generate_msbt_overlays(mods_root, cancel_event=cancel_event)

            if self._scan_should_abort(cancel_event):
                return self.tracks

        for track in self.tracks:
            if self._scan_should_abort(cancel_event):
                return self.tracks
            if not track.display_name:
                track.display_name = beautify_track_name(track.track_id)
            track.is_favorite = track.track_id in self.favorite_track_ids

        self.tracks = [
            track
            for track in self.tracks
            if self._is_supported_track_file(track.file_path)
        ]

        if self._scan_should_abort(cancel_event):
            return self.tracks
        self._discover_stage_slots(mods_root)
        if self._scan_should_abort(cancel_event):
            return self.tracks
        if self.stage_playlists:
            self._rebind_stage_playlists_to_current_tracks()
        else:
            self._load_saved_assignments()
        self._load_saved_replacements()

        return self.tracks

    def _auto_generate_msbt_overlays(
        self, mods_root: Path, cancel_event: Optional[threading.Event] = None
    ) -> None:
        """Run legacy MSBT overlay maintenance hook.

        Overlay generation is currently disabled in ``ConflictResolver``.
        This hook now acts as a lightweight compatibility path that can
        still clean old generated artifacts when scans occur.
        """
        try:
            from src.core.conflict_resolver import ConflictResolver

            # Quick fingerprint of all binary MSBT files in mods to see
            # whether we actually need to regenerate overlays.
            msbt_fingerprint = set()
            for mod_folder in sorted(mods_root.iterdir()):
                if self._scan_should_abort(cancel_event):
                    return
                if not mod_folder.is_dir():
                    continue
                if self._is_skipped_mod_folder(mod_folder):
                    continue
                for fpath in mod_folder.rglob(MSBT_GLOB):
                    if self._scan_should_abort(cancel_event):
                        return
                    try:
                        stat = fpath.stat()
                        msbt_fingerprint.add((str(fpath), stat.st_size, stat.st_mtime_ns))
                    except OSError:
                        pass
                for fpath in mod_folder.rglob(XMSBT_GLOB):
                    if self._scan_should_abort(cancel_event):
                        return
                    try:
                        stat = fpath.stat()
                        msbt_fingerprint.add((str(fpath), stat.st_size, stat.st_mtime_ns))
                    except OSError:
                        pass

            fp = frozenset(msbt_fingerprint)
            if hasattr(self, FINGERPRINT_ATTR_NAME) and getattr(self, FINGERPRINT_ATTR_NAME) == fp:
                return
            setattr(self, FINGERPRINT_ATTR_NAME, fp)

            if self._scan_should_abort(cancel_event):
                return

            resolver = ConflictResolver(mods_root)
            count = resolver.generate_msbt_overlays(cancel_event=cancel_event)
            if count > 0:
                logger.info("MusicManager",
                            f"Auto-generated {count} MSBT overlay(s) for track names")
        except Exception as e:
            logger.warn("MusicManager", f"Failed to auto-generate MSBT overlays: {e}")

    def _load_track_names_from_mod(
        self,
        mod_folder: Path,
        cancel_event: Optional[threading.Event] = None,
        parse_binary_msbt: bool = True,
    ) -> None:
        """Load track display names from XMSBT/MSBT files in a mod."""
        for xmsbt_file in mod_folder.rglob(XMSBT_GLOB):
            if self._scan_should_abort(cancel_event):
                return
            if any(marker in xmsbt_file.name.lower() for marker in BGM_MESSAGE_MARKERS):
                entries = parse_xmsbt(xmsbt_file)
                self._apply_track_names(entries)

        if parse_binary_msbt:
            for msbt_file in mod_folder.rglob(MSBT_GLOB):
                if self._scan_should_abort(cancel_event):
                    return
                if any(marker in msbt_file.name.lower() for marker in BGM_MESSAGE_MARKERS):
                    entries = extract_entries_from_msbt(msbt_file)
                    self._apply_track_names(entries)

    def _apply_track_names(self, entries: dict[str, str]) -> None:
        """Apply track names from parsed XMSBT/MSBT entries to discovered tracks.

        Matches MSBT labels (e.g. bgm_title_25AR) to discovered tracks
        (e.g. bgm_25AR.nus3audio) using multiple heuristics.
        """
        title_lookup: dict[str, str] = {}
        for label, text in entries.items():
            if not text or not text.strip():
                continue
            lower_label = label.lower()
            if any(marker in lower_label for marker in BGM_LABEL_MARKERS):
                title_lookup[label] = text.strip()

        if not title_lookup:
            title_lookup = {k: v.strip() for k, v in entries.items() if v and v.strip()}

        for track in self.tracks:
            if track.display_name:
                continue

            track_id_lower = track.track_id.lower()
            track_id_bare = track_id_lower
            if track_id_bare.startswith(TRACK_ID_PREFIX):
                track_id_bare = track_id_bare[TRACK_ID_PREFIX_LENGTH:]

            best_match = None

            for label, text in title_lookup.items():
                if track.track_id in label or label.endswith(track.track_id):
                    best_match = text
                    break

                label_parts = label.rsplit(BGM_SUFFIX_SEPARATOR, 1)
                label_suffix = label_parts[-1].lower() if len(label_parts) >= 2 else None

                if label_suffix:
                    if (track_id_lower.endswith(BGM_SUFFIX_SEPARATOR + label_suffix)
                            or track_id_bare == label_suffix):
                        best_match = text
                        break

                    track_suffix = (
                        track.track_id.rsplit(BGM_SUFFIX_SEPARATOR, 1)[-1].lower()
                        if BGM_SUFFIX_SEPARATOR in track.track_id
                        else ""
                    )
                    if label_suffix and track_suffix and label_suffix == track_suffix:
                        best_match = text
                        break

            if best_match:
                track.display_name = best_match

    def _discover_stage_slots(self, mods_root: Path) -> None:
        """Build per-stage slot metadata from discovered PRC databases."""
        self.stage_slots = {}
        self._slot_source_mod = None

        source_mod = self._find_music_source_mod(mods_root)
        if source_mod is None:
            return

        stage_db_path = source_mod / "ui" / "param" / "database" / "ui_stage_db.prc"
        bgm_db_path = source_mod / "ui" / "param" / "database" / "ui_bgm_db.prc"
        if not stage_db_path.exists() or not bgm_db_path.exists():
            return

        try:
            import pyprc
        except ImportError:
            logger.warn("MusicManager", "pyprc not installed - stage slot discovery skipped")
            return

        try:
            vanilla_ids = self._load_vanilla_bgm_ids()
            bgm_prc = pyprc.param(str(bgm_db_path))
            bgm_db = list(bgm_prc)[0][1]
            bgm_lookup: dict[str, dict[str, str | int | bool]] = {}
            for entry in bgm_db:
                ui_bgm_id = self._safe_field_str(entry, "ui_bgm_id")
                if not ui_bgm_id:
                    continue
                stream_set_id = self._safe_field_str(entry, "stream_set_id")
                filename = infer_bgm_filename(ui_bgm_id, stream_set_id)
                display_name = beautify_track_name(Path(filename).stem) if filename else beautify_track_name(ui_bgm_id)
                bgm_lookup[ui_bgm_id] = {
                    "stream_set_id": stream_set_id,
                    "filename": filename,
                    "display_name": display_name,
                    "save_no": self._safe_field_int(entry, "save_no", -1),
                    "menu_value": self._safe_field_int(entry, "menu_value", 0),
                    "is_likely_vanilla": filename.lower() in vanilla_ids if filename else False,
                }

            stage_prc = pyprc.param(str(stage_db_path))
            stage_db = list(stage_prc)[0][1]
            discovered: dict[str, list[StageTrackSlot]] = {}
            for stage_entry in stage_db:
                raw_stage_id = self._safe_field_str(stage_entry, "ui_stage_id")
                if not raw_stage_id:
                    continue
                stage_id = self._resolve_stage_id(raw_stage_id)
                if stage_id not in VANILLA_STAGES:
                    continue
                try:
                    bgm_set_list = stage_entry["bgm_set_list"]
                except Exception:
                    continue

                slots: list[StageTrackSlot] = []
                for order_number, bgm_ref in enumerate(list(bgm_set_list)):
                    ui_bgm_id = self._safe_field_str(bgm_ref, "ui_bgm_id")
                    if not ui_bgm_id:
                        continue
                    meta = bgm_lookup.get(ui_bgm_id, {})
                    filename = str(meta.get("filename", "") or infer_bgm_filename(ui_bgm_id))
                    slot_key = filename or ui_bgm_id
                    slots.append(
                        StageTrackSlot(
                            stage_id=stage_id,
                            stage_name=VANILLA_STAGES.get(stage_id, stage_id),
                            slot_key=slot_key,
                            ui_bgm_id=ui_bgm_id,
                            filename=filename,
                            display_name=str(meta.get("display_name", "") or beautify_track_name(Path(filename or ui_bgm_id).stem)),
                            incidence=self._safe_field_int(bgm_ref, "incidence", DEFAULT_BGM_INCIDENCE),
                            order_number=order_number,
                            is_likely_vanilla=bool(meta.get("is_likely_vanilla", False)),
                        )
                    )

                if slots:
                    discovered[stage_id] = slots

            self.stage_slots = discovered
            self._slot_source_mod = source_mod
        except Exception as exc:
            logger.warn("MusicManager", f"Failed to discover stage slots: {exc}")

    def get_stage_list(self) -> list[StageInfo]:
        """Get list of all vanilla stages."""
        return [
            StageInfo(stage_id=sid, stage_name=sname)
            for sid, sname in sorted(VANILLA_STAGES.items(), key=lambda x: x[1])
        ]

    def _library_config_path(self) -> Path:
        return CONFIG_DIR / LIBRARY_FILENAME

    def _load_library_preferences(self) -> None:
        if self._library_loaded:
            return

        config_file = self._library_config_path()
        self.favorite_track_ids = set()
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                favorites = data.get("favorite_track_ids", [])
                if isinstance(favorites, list):
                    self.favorite_track_ids = {
                        str(track_id).strip()
                        for track_id in favorites
                        if str(track_id).strip()
                    }
            except (json.JSONDecodeError, OSError, TypeError, ValueError) as e:
                logger.warn("Music", f"Failed to load music library preferences: {e}")
        self._library_loaded = True

    def _save_library_preferences(self) -> None:
        config_dir = CONFIG_DIR
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = self._library_config_path()
        data = {
            "favorite_track_ids": sorted(self.favorite_track_ids),
        }
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            logger.error("Music", f"Failed to save music library preferences: {e}")

    def _rebind_stage_playlists_to_current_tracks(self) -> None:
        track_lookup = {track.track_id: track for track in self.tracks}
        rebound: dict[str, StagePlaylist] = {}
        for stage_id, playlist in self.stage_playlists.items():
            rebound_tracks = [
                track_lookup[track.track_id]
                for track in playlist.tracks
                if track.track_id in track_lookup
            ]
            rebound[stage_id] = StagePlaylist(
                stage_id=playlist.stage_id,
                stage_name=playlist.stage_name,
                tracks=rebound_tracks,
            )
        self.stage_playlists = rebound

    def is_track_favorite(self, track_id: str) -> bool:
        self._load_library_preferences()
        return track_id in self.favorite_track_ids

    def set_track_favorite(self, track_id: str, is_favorite: bool) -> bool:
        self._load_library_preferences()
        changed = False
        if is_favorite:
            if track_id not in self.favorite_track_ids:
                self.favorite_track_ids.add(track_id)
                changed = True
        else:
            if track_id in self.favorite_track_ids:
                self.favorite_track_ids.remove(track_id)
                changed = True

        if changed:
            for track in self.tracks:
                if track.track_id == track_id:
                    track.is_favorite = is_favorite
            self._save_library_preferences()
        return is_favorite

    def toggle_track_favorite(self, track_id: str) -> bool:
        return self.set_track_favorite(track_id, not self.is_track_favorite(track_id))

    def get_favorite_tracks(self) -> list[MusicTrack]:
        self._load_library_preferences()
        return [
            track
            for track in self.tracks
            if track.track_id in self.favorite_track_ids
            and self._is_supported_track_file(track.file_path)
        ]

    def _replacement_config_path(self) -> Path:
        return CONFIG_DIR / REPLACEMENTS_FILENAME

    def get_stage_slots(self, stage_id: str) -> list[StageTrackSlot]:
        return list(self.stage_slots.get(stage_id, []))

    def get_stage_slot_source_name(self) -> str:
        if self._slot_source_mod is None:
            return ""
        return self._slot_source_mod.name

    def get_stage_slot_replacement(self, stage_id: str, slot_key: str) -> Optional[MusicReplacementAssignment]:
        return self.replacement_assignments.get(stage_id, {}).get(slot_key)

    def get_stage_slot_replacement_track(self, stage_id: str, slot_key: str) -> Optional[MusicTrack]:
        assignment = self.get_stage_slot_replacement(stage_id, slot_key)
        if assignment is None:
            return None
        for track in self.tracks:
            if track.track_id == assignment.replacement_track_id:
                return track
        return None

    def set_stage_slot_replacement(
        self,
        stage_id: str,
        slot_key: str,
        track: Optional[MusicTrack],
    ) -> None:
        if not stage_id or not slot_key:
            return
        if track is None:
            stage_assignments = self.replacement_assignments.get(stage_id)
            if stage_assignments is None:
                return
            stage_assignments.pop(slot_key, None)
            if not stage_assignments:
                self.replacement_assignments.pop(stage_id, None)
            return

        stage_assignments = self.replacement_assignments.setdefault(stage_id, {})
        stage_assignments[slot_key] = MusicReplacementAssignment(
            stage_id=stage_id,
            slot_key=slot_key,
            replacement_track_id=track.track_id,
        )

    def clear_stage_replacements(self, stage_id: str) -> None:
        self.replacement_assignments.pop(stage_id, None)

    def clear_all_replacements(self) -> None:
        self.replacement_assignments.clear()

    def _save_replacement_config(self) -> None:
        config_dir = CONFIG_DIR
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = self._replacement_config_path()
        data = {"assignments": {}}
        for stage_id, stage_assignments in self.replacement_assignments.items():
            if not stage_assignments:
                continue
            data["assignments"][stage_id] = {
                slot_key: assignment.replacement_track_id
                for slot_key, assignment in stage_assignments.items()
                if assignment.replacement_track_id
            }
        try:
            with open(config_file, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError as exc:
            logger.error("Music", f"Failed to save replacement config: {exc}")

    def _load_saved_replacements(self) -> None:
        config_file = self._replacement_config_path()
        self.replacement_assignments = {}
        if not config_file.exists():
            return

        try:
            with open(config_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            track_lookup = {track.track_id: track for track in self.tracks}
            for stage_id, slot_map in (data.get("assignments", {}) or {}).items():
                if not isinstance(slot_map, dict):
                    continue
                normalized_stage_id = self._resolve_stage_id(str(stage_id))
                for slot_key, track_id in slot_map.items():
                    track_id_str = str(track_id).strip()
                    track = track_lookup.get(track_id_str)
                    if not track_id_str or track is None:
                        continue
                    self.set_stage_slot_replacement(normalized_stage_id, str(slot_key), track)
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            logger.warn("Music", f"Failed to load music replacements: {exc}")

    def reload_saved_assignments(self) -> None:
        self.stage_playlists = {}
        self.exclude_vanilla = False
        self.replacement_assignments = {}
        self._load_saved_assignments()
        self._load_saved_replacements()

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
        return [
            track
            for track in self.tracks
            if self._is_supported_track_file(track.file_path)
        ]

    # === Save / Apply Methods ===

    def save_assignments(self, mods_root: Path) -> dict:
        """
        Save music assignments by:
        1. Persisting the assignment config to JSON
        2. Generating/modifying the ui_bgm_db.prc and ui_stage_db.prc in a
           _MusicConfig mod folder that ARCropolis will load
        3. Handling main menu music replacement separately
        Returns a summary dict.
        """
        result = {
            "stages_configured": 0,
            "tracks_assigned": 0,
            "output_mod": "",
            "prc_updated": False,
            "config_saved": False,
            "menu_music_set": False,
            "replacement_stages": 0,
            "replacement_files": 0,
            "replacement_output_mod": "",
        }

        # Save the JSON config for persistence
        self._save_assignment_config(mods_root)
        self._save_replacement_config()
        result["config_saved"] = True

        # Handle main menu music separately
        menu_tracks = self.get_tracks_for_stage(MENU_STAGE_ID)
        if menu_tracks:
            try:
                self._apply_menu_music(menu_tracks[0], mods_root)
                result["menu_music_set"] = True
            except Exception as e:
                logger.error("MusicManager", f"Failed to apply menu music: {e}")
                result["menu_music_set"] = False
        else:
            self._remove_managed_menu_music(mods_root)

        replacement_result = self._apply_replacement_overlays(mods_root)
        result.update(replacement_result)

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
        for stage_id, slot_map in self.replacement_assignments.items():
            if slot_map:
                result["replacement_stages"] += 1

        return result

    @staticmethod
    def _music_config_dir(mods_root: Path) -> Path:
        return mods_root / MUSIC_CONFIG_MOD_DIRNAME

    @classmethod
    def _music_config_stream_dir(cls, mods_root: Path) -> Path:
        return cls._music_config_dir(mods_root) / STREAM_PREFIX / SOUND_BGM_PARTS[0] / SOUND_BGM_PARTS[1]

    @classmethod
    def _replacement_manifest_path(cls, mods_root: Path) -> Path:
        return cls._music_config_dir(mods_root) / REPLACEMENT_MANIFEST_FILENAME

    @classmethod
    def _replacement_metadata_path(cls, mods_root: Path) -> Path:
        return cls._music_config_dir(mods_root) / REPLACEMENT_METADATA_FILENAME

    def _load_previous_replacement_manifest(self, mods_root: Path) -> set[str]:
        manifest_path = self._replacement_manifest_path(mods_root)
        if not manifest_path.exists():
            return set()
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            files = data.get("managed_filenames", [])
            if not isinstance(files, list):
                return set()
            return {str(name).strip() for name in files if str(name).strip()}
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return set()

    def _write_replacement_manifest(self, mods_root: Path, filenames: set[str]) -> None:
        manifest_path = self._replacement_manifest_path(mods_root)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"managed_filenames": sorted(filenames)}
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _remove_managed_menu_music(self, mods_root: Path) -> None:
        dest = self._music_config_stream_dir(mods_root) / MENU_BGM_FILENAME
        if dest.exists():
            try:
                dest.unlink()
            except OSError as exc:
                logger.warn("MusicManager", f"Failed to clear managed menu music: {exc}")

    def _apply_replacement_overlays(self, mods_root: Path) -> dict:
        result = {
            "replacement_files": 0,
            "replacement_output_mod": "",
        }
        config_mod = self._music_config_dir(mods_root)
        stream_dir = self._music_config_stream_dir(mods_root)
        stream_dir.mkdir(parents=True, exist_ok=True)

        previous_files = self._load_previous_replacement_manifest(mods_root)
        current_files: set[str] = set()
        metadata_rows: list[dict[str, str | int | bool]] = []

        track_lookup = {track.track_id: track for track in self.tracks}
        for stage_id, slot_map in self.replacement_assignments.items():
            for slot_key, assignment in slot_map.items():
                track = track_lookup.get(assignment.replacement_track_id)
                if track is None:
                    continue
                filename = Path(slot_key).name if Path(slot_key).suffix else f"{slot_key}{NUS3AUDIO_SUFFIX}"
                if not filename.lower().endswith(NUS3AUDIO_SUFFIX):
                    filename = f"{Path(filename).stem}{NUS3AUDIO_SUFFIX}"
                dest = stream_dir / filename
                shutil.copy2(str(track.file_path), str(dest))
                current_files.add(filename)
                result["replacement_files"] += 1
                metadata_rows.append(
                    {
                        "stage_id": stage_id,
                        "stage_name": VANILLA_STAGES.get(stage_id, stage_id),
                        "slot_key": slot_key,
                        "filename": filename,
                        "replacement_track_id": track.track_id,
                        "replacement_display_name": track.display_name or track.track_id,
                        "source_mod": track.source_mod,
                    }
                )

        for stale_name in previous_files - current_files:
            stale_path = stream_dir / stale_name
            if stale_path.exists():
                try:
                    stale_path.unlink()
                except OSError as exc:
                    logger.warn("MusicManager", f"Failed to remove stale replacement '{stale_name}': {exc}")

        self._write_replacement_manifest(mods_root, current_files)
        metadata_path = self._replacement_metadata_path(mods_root)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_path, "w", encoding="utf-8") as handle:
            json.dump({"replacements": metadata_rows}, handle, indent=2)

        if current_files:
            result["replacement_output_mod"] = str(config_mod)
        return result

    def _apply_menu_music(self, track: MusicTrack, mods_root: Path) -> None:
        """Apply a track as the main menu music.

        Copies the selected track's .nus3audio file into the _MusicConfig mod
        at the path ARCropolis expects for main menu BGM replacement:
            stream;/sound/bgm/bgm_z90_menu.nus3audio

        The semicolon in the path is ARCropolis's stream-load syntax.
        """
        config_mod = self._music_config_dir(mods_root)
        menu_bgm_dir = self._music_config_stream_dir(mods_root)
        menu_bgm_dir.mkdir(parents=True, exist_ok=True)
        dest = menu_bgm_dir / MENU_BGM_FILENAME

        shutil.copy2(str(track.file_path), str(dest))
        logger.info("MusicManager",
                    f"Menu music set to: {track.display_name or track.track_id} "
                    f"(from {track.source_mod})")

    def _find_music_source_mod(self, mods_root: Path) -> Optional[Path]:
        """Find a mod folder that contains ui_bgm_db.prc (the BGM database)."""
        for mod_folder in sorted(mods_root.iterdir()):
            if not mod_folder.is_dir():
                continue
            if self._is_skipped_mod_folder(mod_folder):
                continue
            bgm_db = mod_folder / "ui" / "param" / "database" / "ui_bgm_db.prc"
            stage_db = mod_folder / "ui" / "param" / "database" / "ui_stage_db.prc"
            if bgm_db.exists() and stage_db.exists():
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
                                        new_entry['incidence'].value = DEFAULT_BGM_INCIDENCE
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
        config_mod = self._music_config_dir(mods_root)
        config_mod.mkdir(exist_ok=True)

        config = {
            "description": "Auto-generated music configuration by SSBU Mod Manager",
            "exclude_vanilla": self.exclude_vanilla,
            "assignments": {},
            "safe_replacement_slots": sum(
                len(slot_map) for slot_map in self.replacement_assignments.values()
            ),
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

        config_file = config_mod / MUSIC_CONFIG_FILENAME
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except OSError as e:
            logger.error("MusicManager", f"Failed to write music config: {e}")

        return config_mod

    def _save_assignment_config(self, mods_root: Path) -> None:
        """Save current assignments to a persistent JSON config."""
        config_dir = CONFIG_DIR
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / ASSIGNMENTS_FILENAME

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
        config_file = CONFIG_DIR / ASSIGNMENTS_FILENAME
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
        replacement_stages = 0
        replacement_slots = 0

        for stage_id, playlist in self.stage_playlists.items():
            if playlist.tracks:
                total_stages += 1
                total_tracks += len(playlist.tracks)
                stages_with_music.append(playlist.stage_name)

        for stage_id, slot_map in self.replacement_assignments.items():
            if slot_map:
                replacement_stages += 1
                replacement_slots += len(slot_map)

        return {
            "stages_configured": total_stages,
            "total_assignments": total_tracks,
            "stages_with_music": stages_with_music,
            "exclude_vanilla": self.exclude_vanilla,
            "favorite_tracks": len(self.favorite_track_ids),
            "replacement_stages": replacement_stages,
            "replacement_slots": replacement_slots,
            "slot_source_mod": self.get_stage_slot_source_name(),
            "slot_catalog_stages": len(self.stage_slots),
        }

