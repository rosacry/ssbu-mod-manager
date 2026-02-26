from pathlib import Path
import threading

import src.core.conflict_resolver as conflict_resolver_module
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


def test_generate_msbt_overlays_can_cancel_mid_scan(tmp_path: Path, monkeypatch):
    mods_root = tmp_path / "mods"
    for idx in range(8):
        _write_dummy_msbt(
            mods_root / f"Mod{idx:02d}" / "ui" / "message" / "msg_title.msbt"
        )

    cancel_event = threading.Event()
    calls: list[Path] = []

    def fake_extract_entries(path: Path) -> dict[str, str]:
        calls.append(path)
        if len(calls) == 1:
            cancel_event.set()
        return {"bgm_title_TEST": "Test Track"}

    monkeypatch.setattr(
        conflict_resolver_module,
        "extract_entries_from_msbt",
        fake_extract_entries,
    )
    monkeypatch.setattr(
        conflict_resolver_module,
        "filter_custom_entries",
        lambda entries, inclusive=False: dict(entries),
    )

    resolver = ConflictResolver(mods_root)
    generated = resolver.generate_msbt_overlays(cancel_event=cancel_event)

    assert generated == 0
    assert len(calls) == 1
    assert not (mods_root / "_MergedResources").exists()
