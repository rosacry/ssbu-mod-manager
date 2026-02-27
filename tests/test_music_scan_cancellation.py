from pathlib import Path
import threading

from src.core.conflict_resolver import ConflictResolver


def _write_dummy_msbt(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"dummy-msbt")


def test_generate_msbt_overlays_respects_pre_cancelled_event(tmp_path: Path):
    mods_root = tmp_path / "mods"
    _write_dummy_msbt(mods_root / "ModA" / "ui" / "message" / "msg_bgm.msbt")
    _write_dummy_msbt(mods_root / "ModB" / "ui" / "message" / "msg_bgm.msbt")

    cancel_event = threading.Event()
    cancel_event.set()

    resolver = ConflictResolver(mods_root)
    generated = resolver.generate_msbt_overlays(cancel_event=cancel_event)

    assert generated == 0
    assert not (mods_root / "_MergedResources").exists()


def test_generate_msbt_overlays_cleans_legacy_merged_resources(tmp_path: Path):
    mods_root = tmp_path / "mods"
    merged_root = mods_root / "_MergedResources"
    merged_file = merged_root / "ui" / "message" / "msg_name.xmsbt"
    merged_file.parent.mkdir(parents=True, exist_ok=True)
    merged_file.write_text("<xmsbt />", encoding="utf-8")

    resolver = ConflictResolver(mods_root)
    generated = resolver.generate_msbt_overlays()

    assert generated == 0
    assert not merged_root.exists()
