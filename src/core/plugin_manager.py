"""Skyline plugin management."""
from pathlib import Path
from typing import Iterator, Optional
from src.models.plugin import Plugin, PluginStatus, KnownPluginInfo
from src.constants import KNOWN_PLUGINS


class PluginManager:
    """Manage plugin discovery and enable/disable operations.

    Disabled plugins are stored in a sibling folder:
    `<plugins_path>/../disabled_plugins/`

    Legacy `.nro.disabled` files are still supported for backward
    compatibility and can be migrated to `disabled_plugins`.
    """

    DISABLED_DIR_NAME = "disabled_plugins"

    def __init__(self, plugins_path: Path):
        self.plugins_path = plugins_path
        self._plugins: list[Plugin] = []
        self._cached = False

    @staticmethod
    def base_filename(filename: str) -> str:
        """Normalize legacy `.disabled` filenames to their base plugin name."""
        suffix = ".disabled"
        if filename.lower().endswith(suffix):
            return filename[:-len(suffix)]
        return filename

    @property
    def disabled_plugins_path(self) -> Path:
        return self.plugins_path.parent / self.DISABLED_DIR_NAME

    @staticmethod
    def _iter_files(directory: Path) -> Iterator[Path]:
        try:
            for path in sorted(directory.iterdir()):
                if path.is_file():
                    yield path
        except OSError:
            return

    @staticmethod
    def _is_enabled_plugin_filename(filename: str) -> bool:
        return filename.lower().endswith(".nro")

    @staticmethod
    def _is_legacy_disabled_filename(filename: str) -> bool:
        return filename.lower().endswith(".nro.disabled")

    def _append_plugin(self, filename: str, path: Path, status: PluginStatus) -> None:
        known = KNOWN_PLUGINS.get(filename)
        try:
            file_size = path.stat().st_size
        except OSError:
            file_size = 0

        self._plugins.append(
            Plugin(
                filename=filename,
                path=path,
                status=status,
                file_size=file_size,
                known_info=known,
            )
        )

    def list_plugins(self, force_refresh: bool = False) -> list[Plugin]:
        """List plugins using cache unless force_refresh=True.

        Enabled plugins are read from `plugins_path`.
        Disabled plugins are read from `disabled_plugins_path`.
        Legacy `.nro.disabled` files in `plugins_path` are treated as disabled.
        """
        if self._cached and not force_refresh:
            return self._plugins

        self._plugins = []
        if self.plugins_path == Path("."):
            self._cached = True
            return self._plugins

        enabled_plugins: dict[str, tuple[str, Path]] = {}
        disabled_plugins: dict[str, tuple[str, Path]] = {}

        if self.plugins_path.exists() and self.plugins_path.is_dir():
            for fpath in self._iter_files(self.plugins_path):
                fname = fpath.name
                if not self._is_enabled_plugin_filename(fname):
                    continue
                key = fname.lower()
                enabled_plugins[key] = (fname, fpath)

        disabled_root = self.disabled_plugins_path
        if disabled_root.exists() and disabled_root.is_dir():
            for fpath in self._iter_files(disabled_root):
                fname = fpath.name
                if not (
                    self._is_enabled_plugin_filename(fname)
                    or self._is_legacy_disabled_filename(fname)
                ):
                    continue
                base_name = self.base_filename(fname)
                key = base_name.lower()
                if key in enabled_plugins or key in disabled_plugins:
                    continue
                disabled_plugins[key] = (base_name, fpath)

        # Backward compatibility: plugins disabled via `.nro.disabled`
        # inside the live plugins directory.
        if self.plugins_path.exists() and self.plugins_path.is_dir():
            for fpath in self._iter_files(self.plugins_path):
                fname = fpath.name
                if not self._is_legacy_disabled_filename(fname):
                    continue
                base_name = self.base_filename(fname)
                key = base_name.lower()
                if key in enabled_plugins or key in disabled_plugins:
                    continue
                disabled_plugins[key] = (base_name, fpath)

        for key in sorted(enabled_plugins):
            filename, path = enabled_plugins[key]
            self._append_plugin(filename, path, PluginStatus.ENABLED)

        for key in sorted(disabled_plugins):
            filename, path = disabled_plugins[key]
            self._append_plugin(filename, path, PluginStatus.DISABLED)

        self._cached = True
        return self._plugins

    def migrate_legacy_disabled_plugins(self) -> int:
        """Move legacy `.nro.disabled` files into `disabled_plugins`."""
        if (
            self.plugins_path == Path(".")
            or not self.plugins_path.exists()
            or not self.plugins_path.is_dir()
        ):
            return 0

        migrated = 0
        disabled_root = self.disabled_plugins_path
        for fpath in list(self._iter_files(self.plugins_path)):
            if not self._is_legacy_disabled_filename(fpath.name):
                continue
            target_name = self.base_filename(fpath.name)
            target_path = disabled_root / target_name
            if target_path.exists():
                continue
            disabled_root.mkdir(parents=True, exist_ok=True)
            try:
                fpath.rename(target_path)
                migrated += 1
            except OSError:
                pass

        if migrated:
            self.invalidate_cache()
        return migrated

    def invalidate_cache(self):
        """Force next list_plugins() to re-scan."""
        self._cached = False

    def refresh(self) -> list[Plugin]:
        """Force refresh the plugin list."""
        return self.list_plugins(force_refresh=True)

    def enable_plugin(self, plugin: Plugin) -> None:
        """Enable a plugin by moving it back into the plugins folder."""
        if plugin.status == PluginStatus.ENABLED:
            return

        new_name = self.base_filename(plugin.filename)
        self.plugins_path.mkdir(parents=True, exist_ok=True)
        new_path = self.plugins_path / new_name
        if new_path.exists():
            raise FileExistsError(f"Cannot enable: '{new_name}' already exists")

        plugin.path.rename(new_path)
        plugin.filename = new_name
        plugin.path = new_path
        plugin.status = PluginStatus.ENABLED
        self.invalidate_cache()

    def disable_plugin(self, plugin: Plugin) -> None:
        """Disable a plugin by moving it to `disabled_plugins`."""
        if plugin.status == PluginStatus.DISABLED:
            return

        new_name = self.base_filename(plugin.filename)
        disabled_root = self.disabled_plugins_path
        disabled_root.mkdir(parents=True, exist_ok=True)
        new_path = disabled_root / new_name
        if new_path.exists():
            raise FileExistsError(f"Cannot disable: '{new_name}' already exists in disabled_plugins")

        plugin.path.rename(new_path)
        plugin.filename = new_name
        plugin.path = new_path
        plugin.status = PluginStatus.DISABLED
        self.invalidate_cache()

    def enable_all(self) -> int:
        """Enable all disabled plugins. Returns count enabled."""
        count = 0
        # Snapshot list to avoid iteration-during-mutation
        plugins_snapshot = list(self.list_plugins())
        for plugin in plugins_snapshot:
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
        # Snapshot list to avoid iteration-during-mutation
        plugins_snapshot = list(self.list_plugins())
        for plugin in plugins_snapshot:
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
        return KNOWN_PLUGINS.get(self.base_filename(filename))
