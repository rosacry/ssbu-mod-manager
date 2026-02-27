import threading
import time
from pathlib import Path

import src.core.mod_manager as mod_manager_module
from src.core.desync_classifier import DesyncRiskLevel, ModDesyncReport
from src.core.mod_manager import ModManager


def _make_mod(root: Path, name: str) -> None:
    mod_dir = root / name
    (mod_dir / "ui").mkdir(parents=True, exist_ok=True)
    (mod_dir / "ui" / "marker.txt").write_text("x", encoding="utf-8")


def test_list_mods_thread_safe_no_duplicates(tmp_path: Path, monkeypatch) -> None:
    mods_root = tmp_path / "mods"
    mods_root.mkdir(parents=True, exist_ok=True)
    for name in ("A", "B", "C"):
        _make_mod(mods_root, name)

    barrier = threading.Barrier(2)
    first_hit = threading.Event()

    def fake_classify(_path: Path) -> ModDesyncReport:
        # Encourage overlap when lock protection is missing.
        if not first_hit.is_set():
            first_hit.set()
            try:
                barrier.wait(timeout=0.25)
            except threading.BrokenBarrierError:
                pass
        time.sleep(0.01)
        return ModDesyncReport(
            level=DesyncRiskLevel.SAFE_CLIENT_ONLY,
            reasons=[],
            scanned_files=1,
        )

    monkeypatch.setattr(mod_manager_module, "classify_mod_path", fake_classify)

    manager = ModManager(mods_root)

    results: list[list] = []

    def worker() -> None:
        results.append(manager.list_mods(force_refresh=True))

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(results) == 2

    final = manager.list_mods()
    assert len(final) == 3

    unique_keys = {(m.status.value, str(m.path).lower()) for m in final}
    assert len(unique_keys) == 3
