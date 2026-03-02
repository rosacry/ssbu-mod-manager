"""Skin slot detection and base-slot reslot helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil


_FIGHTER_PATH_RE = re.compile(
    r"(?:^|/)fighter/([^/]+)(?:/[^/]+)*/c(\d{2,3})(?:/|$)",
    re.IGNORECASE,
)
_CAMERA_PATH_RE = re.compile(
    r"(?:^|/)camera/fighter/([^/]+)/c(\d{2,3})(?:/|$)",
    re.IGNORECASE,
)
_SOUND_PATH_RE = re.compile(
    r"(?:^|/)sound/bank/fighter(?:_voice)?/(?:vc_|se_)([^_/]+)_c(\d{2,3})",
    re.IGNORECASE,
)
_UI_PATH_RE = re.compile(
    r"(?:^|/)ui/(?:replace|replace_patch)/chara/[^/]+/[^/]+_([^_/]+)_(\d{2,3})\.bntx$",
    re.IGNORECASE,
)
_EFFECT_PATH_RE = re.compile(
    r"(?:^|/)effect/fighter/([^/]+)/.*?c(\d{2,3})(?:\b|(?=/)|(?=\.))",
    re.IGNORECASE,
)
_SLOT_HINT_RE = re.compile(r"(?:^|[^a-z0-9])c(\d{2,3})(?:[^a-z0-9]|$)", re.IGNORECASE)

_VARIANT_NAME_PRIORITY = (
    "default",
    "base",
    "main",
    "normal",
    "vanilla",
)
_VARIANT_NAME_DEMOTIONS = (
    "extra",
    "extras",
    "alt",
    "alts",
    "variant",
    "readme",
    "preview",
    "css",
)

_CLIMBER = {"popo", "nana"}
_TRAINER = {"ptrainer", "ptrainer_low", "pzenigame", "pfushigisou", "plizardon"}
_AEGIS = {"element", "eflame", "elight"}


@dataclass
class SlotAnalysis:
    fighter_slots: dict[str, list[int]] = field(default_factory=dict)
    slot_scores: dict[str, dict[int, int]] = field(default_factory=dict)
    slot_categories: dict[str, dict[int, frozenset[str]]] = field(default_factory=dict)
    primary_fighter: str | None = None
    primary_slot: int | None = None

    @property
    def has_detected_skin_slot(self) -> bool:
        return self.primary_fighter is not None and self.primary_slot is not None

    @property
    def slot_count(self) -> int:
        return sum(len(slots) for slots in self.fighter_slots.values())

    @property
    def visual_fighter_slots(self) -> dict[str, list[int]]:
        visual: dict[str, list[int]] = {}
        for fighter, per_slot in self.slot_categories.items():
            slots = sorted(
                slot
                for slot, categories in per_slot.items()
                if _is_visual_slot_categories(categories)
            )
            if slots:
                visual[fighter] = slots
        return visual

    @property
    def visual_slot_count(self) -> int:
        return sum(len(slots) for slots in self.visual_fighter_slots.values())

    @property
    def has_visual_skin_slot(self) -> bool:
        if self.primary_fighter is None or self.primary_slot is None:
            return False
        return self.has_visual_content_for_slot(self.primary_fighter, self.primary_slot)

    def categories_for_slot(self, fighter: str, slot: int) -> frozenset[str]:
        return self.slot_categories.get(str(fighter), {}).get(int(slot), frozenset())

    def has_visual_content_for_slot(self, fighter: str, slot: int) -> bool:
        return _is_visual_slot_categories(self.categories_for_slot(fighter, slot))


def normalize_rel_path(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def iter_slot_matches(relative_path: str | Path) -> list[tuple[str, int]]:
    rel = normalize_rel_path(relative_path)
    matches: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for pattern in (_FIGHTER_PATH_RE, _CAMERA_PATH_RE, _SOUND_PATH_RE, _UI_PATH_RE, _EFFECT_PATH_RE):
        match = pattern.search(rel)
        if match is None:
            continue
        item = (match.group(1).lower(), int(match.group(2)))
        if item not in seen:
            matches.append(item)
            seen.add(item)
    return matches


def analyze_relative_paths(paths: list[str], name_hints: list[str] | None = None) -> SlotAnalysis:
    fighter_slots: dict[str, set[int]] = {}
    slot_categories: dict[str, dict[int, set[str]]] = {}
    for path in paths:
        for fighter, slot in iter_slot_matches(path):
            fighter_slots.setdefault(fighter, set()).add(slot)
            slot_categories.setdefault(fighter, {}).setdefault(slot, set()).add(
                _slot_category_for_path(path)
            )

    normalized = {
        fighter: sorted(slots)
        for fighter, slots in sorted(fighter_slots.items())
    }
    scores = {
        fighter: {
            slot: sum(_CATEGORY_WEIGHTS.get(category, 0) for category in categories)
            for slot, categories in per_slot.items()
        }
        for fighter, per_slot in slot_categories.items()
    }
    normalized_categories = {
        fighter: {
            slot: frozenset(sorted(categories))
            for slot, categories in per_slot.items()
        }
        for fighter, per_slot in slot_categories.items()
    }
    primary_fighter, primary_slot = choose_primary_skin_slot(
        normalized,
        name_hints or [],
        slot_scores=scores,
    )
    return SlotAnalysis(
        fighter_slots=normalized,
        slot_scores=scores,
        slot_categories=normalized_categories,
        primary_fighter=primary_fighter,
        primary_slot=primary_slot,
    )


def analyze_mod_directory(mod_path: Path, name_hints: list[str] | None = None) -> SlotAnalysis:
    mod_path = Path(mod_path)
    rel_paths: list[str] = []
    for file_path in mod_path.rglob("*"):
        if file_path.is_file():
            rel_paths.append(normalize_rel_path(file_path.relative_to(mod_path)))
    hints = list(name_hints or []) + [mod_path.name]
    return analyze_relative_paths(rel_paths, hints)


def choose_primary_skin_slot(
    fighter_slots: dict[str, list[int]],
    name_hints: list[str] | None = None,
    slot_scores: dict[str, dict[int, int]] | None = None,
) -> tuple[str | None, int | None]:
    if not fighter_slots:
        return None, None

    hints = " ".join(name_hints or []).lower()
    hinted_slot = None
    match = _SLOT_HINT_RE.search(hints)
    if match:
        hinted_slot = int(match.group(1))

    hinted_fighters = [
        fighter
        for fighter in fighter_slots.keys()
        if fighter.lower() in hints
    ]
    preferred_fighters = hinted_fighters or list(fighter_slots.keys())

    for fighter in preferred_fighters:
        slots = fighter_slots[fighter]
        if hinted_slot is not None and hinted_slot in slots:
            return fighter, hinted_slot

    if slot_scores:
        best_pair = None
        best_score = None
        for fighter in preferred_fighters:
            for slot in fighter_slots[fighter]:
                score = int(slot_scores.get(fighter, {}).get(slot, 0))
                key = (-score, slot, fighter)
                if best_score is None or key < best_score:
                    best_score = key
                    best_pair = (fighter, slot)
        if best_pair is not None and int(slot_scores.get(best_pair[0], {}).get(best_pair[1], 0)) > 0:
            return best_pair

    for fighter, slots in fighter_slots.items():
        if hinted_slot is not None and hinted_slot in slots:
            return fighter, hinted_slot

    best_fighter = min(
        preferred_fighters,
        key=lambda fighter: (
            0 if 0 in fighter_slots[fighter] else 1,
            len(fighter_slots[fighter]),
            min(fighter_slots[fighter]),
            fighter,
        ),
    )
    slots = fighter_slots[best_fighter]
    slot = 0 if 0 in slots else min(slots)
    return best_fighter, slot


def choose_primary_variant_root(
    candidates: list[tuple[Path, str]],
    analyses: dict[str, SlotAnalysis],
    package_name: str,
) -> tuple[Path, str]:
    if len(candidates) == 1:
        return candidates[0]

    def score(item: tuple[Path, str]) -> tuple[int, int, int, int, str]:
        src, target_name = item
        analysis = analyses.get(str(src))
        text = f"{package_name} {src.name} {target_name}".lower()
        priority = 5
        for idx, marker in enumerate(_VARIANT_NAME_PRIORITY):
            if marker in text:
                priority = idx
                break
        demotion = 1 if any(marker in text for marker in _VARIANT_NAME_DEMOTIONS) else 0
        slot = analysis.primary_slot if analysis and analysis.primary_slot is not None else 999
        slot_count = analysis.slot_count if analysis else 999
        return (priority, demotion, slot, slot_count, target_name.lower())

    return min(candidates, key=score)


def choose_open_target_slot(fighter: str, source_slot: int, open_slots: list[int]) -> int | None:
    if not open_slots:
        return None
    preferred_share = assumed_share_slot(fighter, source_slot)
    ranked = sorted(
        open_slots,
        key=lambda slot: (
            0 if assumed_share_slot(fighter, slot) == preferred_share else 1,
            abs(slot - source_slot),
            slot,
        ),
    )
    return ranked[0] if ranked else None


def assumed_share_slot(fighter: str, slot: int) -> int:
    fighter = (fighter or "").lower()
    alts_last2 = {"edge", "szerosuit", "littlemac", "mario", "metaknight", "jack"}
    alts_odd = {
        "bayonetta", "master", "cloud", "kamui", "ike", "shizue", "demon",
        "link", "packun", "reflet", "wario", "wiifit",
        "ptrainer", "ptrainer_low", "pfushigisou", "plizardon", "pzenigame",
    }
    alts_all = {"koopajr", "murabito", "purin", "pikachu", "pichu", "sonic"}

    if fighter in {"brave", "trail"}:
        return slot % 4
    if fighter in {"pikmin", "popo", "nana"}:
        return 0 if slot < 4 else 4
    if fighter == "pacman":
        return 0 if slot in {0, 7} else slot
    if fighter == "ridley":
        return 0 if slot in {1, 7} else slot
    if fighter in {"inkling", "pickel"}:
        return slot % 2 if slot < 6 else slot
    if fighter == "shulk":
        return 0 if slot < 7 else 7
    if fighter in alts_last2:
        return 0 if slot < 6 else slot
    if fighter in alts_all:
        return slot
    if fighter in alts_odd:
        return slot % 2
    return 0


def copy_single_slot_variant(
    source_dir: Path,
    output_dir: Path,
    fighter: str,
    slot: int,
) -> None:
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    slot_token = f"c{slot:02d}"

    for file_path in source_dir.rglob("*"):
        if not file_path.is_file():
            continue
        rel = normalize_rel_path(file_path.relative_to(source_dir))
        if rel.lower() == "config.json":
            continue
        if not _should_keep_for_single_slot(rel, fighter, slot_token):
            continue

        out_path = output_dir / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, out_path)


def reslot_mod_directory(source_dir: Path, output_dir: Path, fighter: str, source_slot: int, target_slot: int) -> None:
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_token = f"c{source_slot:02d}"
    target_token = f"c{target_slot:02d}"
    source_num = f"{source_slot:02d}"
    target_num = f"{target_slot:02d}"

    for file_path in source_dir.rglob("*"):
        if not file_path.is_file():
            continue
        rel = normalize_rel_path(file_path.relative_to(source_dir))
        if rel.lower() == "config.json":
            continue

        new_rel = rel
        lower = rel.lower()
        targeted = _matches_slot_target(rel, fighter, source_token)

        fighter_prefix = f"fighter/{fighter.lower()}/"
        camera_prefix = f"camera/fighter/{fighter.lower()}/"
        effect_prefix = f"effect/fighter/{fighter.lower()}/"

        if targeted and (fighter_prefix in lower or camera_prefix in lower):
            new_rel = _replace_segment_token(new_rel, source_token, target_token)

        if targeted and (lower.startswith("sound/bank/fighter_voice/") or lower.startswith("sound/bank/fighter/")):
            new_rel = re.sub(
                rf"(?i)_c{source_num}(?=\.|_)",
                f"_c{target_num}",
                new_rel,
            )

        if targeted and (lower.startswith("ui/replace/chara/") or lower.startswith("ui/replace_patch/chara/")):
            new_rel = re.sub(
                rf"(?i)_{source_num}(?=\.bntx$)",
                f"_{target_num}",
                new_rel,
            )

        if targeted and lower.startswith(effect_prefix):
            before_effect = new_rel
            new_rel = re.sub(
                rf"(?i)(?<![a-z0-9])c{source_num}(?=[^0-9]|$)",
                target_token,
                new_rel,
            )
            # Only apply bare-number fallback when the canonical c## pass
            # made no changes, to avoid corrupting asset version numbers.
            if new_rel == before_effect:
                new_rel = re.sub(rf"(?i)(_|/){source_num}(?=\.|/|_|$)", lambda m: m.group(1) + target_num, new_rel)

        out_path = output_dir / new_rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, out_path)


def _should_keep_for_single_slot(relative_path: str, fighter: str, slot_token: str) -> bool:
    rel = normalize_rel_path(relative_path)
    lower = rel.lower()
    fighter = fighter.lower()
    slot_token = slot_token.lower()

    if lower in {"info.toml", "preview.webp", "preview.png", "preview.jpg"}:
        return True

    if lower.startswith(f"fighter/{fighter}/"):
        slot_segments = re.findall(r"/c\d{2,3}(?=/|$)", lower)
        if not slot_segments:
            return True
        return _path_has_slot_segment(lower, slot_token)

    if lower.startswith(f"camera/fighter/{fighter}/"):
        return f"/{slot_token}/" in lower

    if lower.startswith("sound/bank/fighter_voice/") or lower.startswith("sound/bank/fighter/"):
        if f"_{fighter}_" not in lower:
            return False
        return f"_c{slot_token[1:]}" in lower

    if lower.startswith("ui/replace/chara/") or lower.startswith("ui/replace_patch/chara/"):
        if f"_{fighter}_" not in lower:
            return False
        return lower.endswith(f"_{slot_token[1:]}.bntx")

    if lower.startswith(f"effect/fighter/{fighter}/"):
        # Effects are inconsistent; keep explicit source-slot files plus generic shared effects.
        return slot_token in lower or ("/transplant/" in lower) or ("ef_" not in lower)

    # Preserve other mod content that is not clearly tied to another slot.
    return not any(
        slot != slot_token
        for slot in re.findall(r"c\d{2,3}", lower)
    )


def _matches_slot_target(relative_path: str, fighter: str, slot_token: str) -> bool:
    rel = normalize_rel_path(relative_path)
    lower = rel.lower()
    fighter = fighter.lower()
    slot_token = slot_token.lower()

    if lower.startswith(f"fighter/{fighter}/"):
        return _path_has_slot_segment(lower, slot_token)
    if lower.startswith(f"camera/fighter/{fighter}/"):
        return _path_has_slot_segment(lower, slot_token)
    if lower.startswith("sound/bank/fighter_voice/") or lower.startswith("sound/bank/fighter/"):
        return f"_{fighter}_" in lower and f"_c{slot_token[1:]}" in lower
    if lower.startswith("ui/replace/chara/") or lower.startswith("ui/replace_patch/chara/"):
        return f"_{fighter}_" in lower and lower.endswith(f"_{slot_token[1:]}.bntx")
    if lower.startswith(f"effect/fighter/{fighter}/"):
        return slot_token in lower or re.search(rf"(?i)(_|/){slot_token[1:]}(?=\.|/|_|$)", lower) is not None
    return False


def _path_has_slot_segment(path: str, slot_token: str) -> bool:
    return re.search(rf"(?i)/{re.escape(slot_token)}(?=/|$)", path) is not None


_CATEGORY_WEIGHTS = {
    "model": 10,
    "ui": 8,
    "sound": 6,
    "camera": 4,
    "motion": 1,
    "fighter": 2,
    "effect": 3,
}


def _slot_category_for_path(relative_path: str) -> str:
    lower = normalize_rel_path(relative_path).lower()
    if lower.startswith("ui/replace/chara/") or lower.startswith("ui/replace_patch/chara/"):
        return "ui"
    if lower.startswith("sound/bank/fighter_voice/") or lower.startswith("sound/bank/fighter/"):
        return "sound"
    if lower.startswith("camera/fighter/"):
        return "camera"
    if lower.startswith("effect/fighter/"):
        return "effect"
    if "/model/" in lower:
        return "model"
    if "/motion/" in lower:
        return "motion"
    return "fighter"


def _replace_segment_token(path: str, old: str, new: str) -> str:
    parts = normalize_rel_path(path).split("/")
    replaced = [new if part.lower() == old.lower() else part for part in parts]
    return "/".join(replaced)


_VISUAL_SLOT_CATEGORIES = frozenset({"model", "ui"})


def _is_visual_slot_categories(categories: frozenset[str] | set[str]) -> bool:
    return bool(set(categories) & _VISUAL_SLOT_CATEGORIES)
