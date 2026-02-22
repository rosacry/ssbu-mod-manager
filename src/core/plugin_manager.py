"""Skyline plugin management."""
from pathlib import Path
from typing import Optional
from src.models.plugin import Plugin, PluginStatus, KnownPluginInfo
from src.constants import KNOWN_PLUGINS


class PluginManager:
    def __init__(self, plugins_path: Path):
        self.plugins_path = plugins_path
        self._plugins: list[Plugin] = []
        self._cached = False

    def list_plugins(self, force_refresh: bool = False) -> list[Plugin]:
        """List all plugins. Uses cache unless force_refresh."""
        if self._cached and not force_refresh:
            return self._plugins

        self._plugins = []
        if not self.plugins_path.exists():
            self._cached = True
            return self._plugins

        for fpath in sorted(self.plugins_path.iterdir()):
            if not fpath.is_file():
                continue

            fname = fpath.name

            if fname.endswith(".nro"):
                status = PluginStatus.ENABLED
                lookup_name = fname
            elif fname.endswith(".nro.disabled"):
                status = PluginStatus.DISABLED
                lookup_name = fname.replace(".disabled", "")
            else:
                continue

            known = KNOWN_PLUGINS.get(lookup_name)

            try:
                file_size = fpath.stat().st_size
            except OSError:
                file_size = 0

            plugin = Plugin(
                filename=fname,
                path=fpath,
                status=status,
                file_size=file_size,
                known_info=known,
            )
            self._plugins.append(plugin)

        self._cached = True
        return self._plugins

    def invalidate_cache(self):
        """Force next list_plugins() to re-scan."""
        self._cached = False

    def refresh(self) -> list[Plugin]:
        """Force refresh the plugin list."""
        return self.list_plugins(force_refresh=True)

    def enable_plugin(self, plugin: Plugin) -> None:
        """Enable a disabled plugin by removing .disabled suffix."""
        if plugin.status == PluginStatus.ENABLED:
            return

        new_name = plugin.filename.replace(".disabled", "")
        new_path = plugin.path.parent / new_name
        if new_path.exists():
            raise FileExistsError(f"Cannot enable: '{new_name}' already exists")

        plugin.path.rename(new_path)
        plugin.filename = new_name
        plugin.path = new_path
        plugin.status = PluginStatus.ENABLED
        self.invalidate_cache()

    def disable_plugin(self, plugin: Plugin) -> None:
        """Disable a plugin by adding .disabled suffix."""
        if plugin.status == PluginStatus.DISABLED:
            return

        new_name = f"{plugin.filename}.disabled"
        new_path = plugin.path.parent / new_name
        if new_path.exists():
            raise FileExistsError(f"Cannot disable: '{new_name}' already exists")

        plugin.path.rename(new_path)
        plugin.filename = new_name
        plugin.path = new_path
        plugin.status = PluginStatus.DISABLED
        self.invalidate_cache()

    def enable_all(self) -> int:
        """Enable all disabled plugins. Returns count enabled."""
        count = 0
        for plugin in self.list_plugins():
            if plugin.status == PluginStatus.DISABLED:
                try:
                    self.enable_plugin(plugin)
                    count += 1
                except (FileExistsError, OSError):
                    pass
        self.invalidate_cache()
        return count

    def disable_all(self, skip_required: bool = True) -> int:
        """Disable all enabled plugins. Skips required plugins by default. Returns count disabled."""
        count = 0
        for plugin in self.list_plugins():
            if plugin.status == PluginStatus.ENABLED:
                if skip_required and plugin.known_info and plugin.known_info.required:
                    continue
                try:
                    self.disable_plugin(plugin)
                    count += 1
                except (FileExistsError, OSError):
                    pass
        self.invalidate_cache()
        return count

    def get_plugin_info(self, filename: str) -> Optional[KnownPluginInfo]:
        """Get known info for a plugin by filename."""
        clean_name = filename.replace(".disabled", "")
        return KNOWN_PLUGINS.get(clean_name)
