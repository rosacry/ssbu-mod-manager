import pytest

import src.core.runtime_guard as runtime_guard


def test_runtime_guard_reports_running_emulator(monkeypatch):
    monkeypatch.setattr(
        runtime_guard,
        "_list_running_process_names",
        lambda: {"ryujinx.exe"},
    )

    with pytest.raises(runtime_guard.ContentOperationBlockedError) as exc:
        runtime_guard.ensure_runtime_content_change_allowed("mod", "disable")

    assert exc.value.info.title == "Cannot Disable Mod"
    assert "Ryujinx" in exc.value.info.message


def test_runtime_guard_reports_files_in_use_without_process_name(monkeypatch):
    monkeypatch.setattr(runtime_guard, "_list_running_process_names", lambda: set())
    with pytest.raises(runtime_guard.ContentOperationBlockedError) as exc:
        runtime_guard.raise_if_files_in_use(PermissionError("locked"), "plugin", "enable")

    assert "tool using these files" in exc.value.info.message
