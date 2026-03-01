import pytest

import src.core.plugin_manager as plugin_manager_module
from src.core.plugin_manager import PluginManager
from src.core.runtime_guard import ContentOperationBlockedError, RuntimeBlockInfo
from src.models.plugin import PluginStatus


@pytest.fixture(autouse=True)
def _allow_plugin_file_operations(monkeypatch):
    monkeypatch.setattr(
        plugin_manager_module,
        "ensure_runtime_content_change_allowed",
        lambda *_args, **_kwargs: None,
    )


def test_disable_enable_plugin_moves_between_live_and_disabled_folders(tmp_path):
    plugins_path = tmp_path / "sdmc" / "atmosphere" / "contents" / "title" / "romfs" / "skyline" / "plugins"
    plugins_path.mkdir(parents=True)
    live_plugin = plugins_path / "libexample.nro"
    live_plugin.write_bytes(b"plugin")

    manager = PluginManager(plugins_path)
    plugins = manager.list_plugins(force_refresh=True)
    assert len(plugins) == 1
    assert plugins[0].status == PluginStatus.ENABLED

    manager.disable_plugin(plugins[0])

    disabled_file = plugins_path.parent / "disabled_plugins" / "libexample.nro"
    assert not live_plugin.exists()
    assert disabled_file.exists()

    plugins = manager.list_plugins(force_refresh=True)
    assert len(plugins) == 1
    assert plugins[0].filename == "libexample.nro"
    assert plugins[0].status == PluginStatus.DISABLED

    manager.enable_plugin(plugins[0])

    assert live_plugin.exists()
    assert not disabled_file.exists()
    plugins = manager.list_plugins(force_refresh=True)
    assert len(plugins) == 1
    assert plugins[0].status == PluginStatus.ENABLED


def test_list_plugins_prefers_enabled_when_duplicate_exists(tmp_path):
    plugins_path = tmp_path / "plugins"
    disabled_path = plugins_path.parent / "disabled_plugins"
    plugins_path.mkdir(parents=True)
    disabled_path.mkdir(parents=True)

    (plugins_path / "libdup.nro").write_bytes(b"enabled")
    (disabled_path / "libdup.nro").write_bytes(b"disabled-copy")
    (disabled_path / "libother.nro").write_bytes(b"disabled")

    manager = PluginManager(plugins_path)
    plugins = manager.list_plugins(force_refresh=True)
    names = {p.filename: p.status for p in plugins}

    assert names["libdup.nro"] == PluginStatus.ENABLED
    assert names["libother.nro"] == PluginStatus.DISABLED
    assert len(plugins) == 2


def test_migrate_legacy_disabled_plugins(tmp_path):
    plugins_path = tmp_path / "plugins"
    plugins_path.mkdir(parents=True)
    legacy_file = plugins_path / "liblegacy.nro.disabled"
    legacy_file.write_bytes(b"legacy-disabled")

    manager = PluginManager(plugins_path)
    migrated = manager.migrate_legacy_disabled_plugins()
    assert migrated == 1

    migrated_file = plugins_path.parent / "disabled_plugins" / "liblegacy.nro"
    assert not legacy_file.exists()
    assert migrated_file.exists()

    plugins = manager.list_plugins(force_refresh=True)
    assert len(plugins) == 1
    assert plugins[0].filename == "liblegacy.nro"
    assert plugins[0].status == PluginStatus.DISABLED


def test_disable_plugin_surfaces_runtime_block(tmp_path, monkeypatch):
    plugins_path = tmp_path / "plugins"
    plugins_path.mkdir(parents=True)
    live_plugin = plugins_path / "libexample.nro"
    live_plugin.write_bytes(b"plugin")

    def _block(*_args, **_kwargs):
        raise ContentOperationBlockedError(
            RuntimeBlockInfo(
                target_label="plugin",
                action="disable",
                running_emulators=("Ryujinx",),
            )
        )

    monkeypatch.setattr(plugin_manager_module, "ensure_runtime_content_change_allowed", _block)

    manager = PluginManager(plugins_path)
    plugin = manager.list_plugins(force_refresh=True)[0]

    with pytest.raises(ContentOperationBlockedError) as exc:
        manager.disable_plugin(plugin)

    assert "Ryujinx" in str(exc.value)
