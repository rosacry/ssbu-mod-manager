from src.core.plugin_manager import PluginManager
from src.models.plugin import PluginStatus


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
