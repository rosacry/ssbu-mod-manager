"""Profile export/import for sharing mod configurations."""
import json
import hashlib
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional
from src.models.profile import (
    ShareProfile, ProfileModEntry, ProfilePluginEntry,
    ProfileMusicConfig, PROFILE_VERSION,
)
from src.models.mod import Mod
from src.models.plugin import Plugin


class ShareCodeManager:
    EMBED_SIZE_LIMIT = 256 * 1024  # 256KB

    @staticmethod
    def _base_plugin_filename(filename: str) -> str:
        suffix = ".disabled"
        if filename.lower().endswith(suffix):
            return filename[:-len(suffix)]
        return filename

    def export_profile(self, mods: list[Mod], plugins: list[Plugin],
                       profile_name: str, description: str = "",
                       embed_plugins: bool = False,
                       music_config: Optional[ProfileMusicConfig] = None) -> ShareProfile:
        """Create a share profile from current setup."""
        profile = ShareProfile(
            version=PROFILE_VERSION,
            profile_name=profile_name,
            created_at=datetime.now().isoformat(),
            description=description,
            music_config=music_config,
        )

        for mod in mods:
            entry = ProfileModEntry(
                name=mod.original_name,
                enabled=mod.status.value == "enabled",
                file_hash=self._hash_mod(mod.path),
            )
            profile.mods.append(entry)

        for plugin in plugins:
            embedded = None
            if embed_plugins and plugin.file_size < self.EMBED_SIZE_LIMIT:
                embedded = self._embed_file(plugin.path)

            entry = ProfilePluginEntry(
                filename=self._base_plugin_filename(plugin.filename),
                enabled=plugin.status.value == "enabled",
                file_size=plugin.file_size,
                file_hash=self._hash_file(plugin.path),
                embedded_data=embedded,
            )
            profile.plugins.append(entry)

        return profile

    def save_profile(self, profile: ShareProfile, output_path: Path) -> None:
        """Save a profile to a .smbprofile file."""
        data = {
            "version": profile.version,
            "profile_name": profile.profile_name,
            "created_by": profile.created_by,
            "created_at": profile.created_at,
            "description": profile.description,
            "mods": [
                {"name": m.name, "enabled": m.enabled, "file_hash": m.file_hash,
                 "download_url": m.download_url}
                for m in profile.mods
            ],
            "plugins": [
                {"filename": p.filename, "enabled": p.enabled, "file_size": p.file_size,
                 "file_hash": p.file_hash, "embedded_data": p.embedded_data}
                for p in profile.plugins
            ],
            "css_character_names": profile.css_character_names,
        }

        if profile.music_config:
            data["music_config"] = {
                "exclude_vanilla": profile.music_config.exclude_vanilla,
                "stage_assignments": profile.music_config.stage_assignments,
            }

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            raise OSError(f"Failed to save profile to {output_path}: {e}")

    def load_profile(self, input_path: Path) -> ShareProfile:
        """Load a profile from a .smbprofile file."""
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        profile = ShareProfile(
            version=data.get("version", "1.0"),
            profile_name=data.get("profile_name", ""),
            created_by=data.get("created_by", ""),
            created_at=data.get("created_at", ""),
            description=data.get("description", ""),
            css_character_names=data.get("css_character_names", []),
        )

        for m in data.get("mods", []):
            try:
                profile.mods.append(ProfileModEntry(
                    name=m.get("name", ""),
                    enabled=m.get("enabled", True),
                    file_hash=m.get("file_hash", ""),
                    download_url=m.get("download_url"),
                ))
            except (KeyError, TypeError):
                continue

        for p in data.get("plugins", []):
            try:
                profile.plugins.append(ProfilePluginEntry(
                    filename=p.get("filename", ""),
                    enabled=p.get("enabled", True),
                    file_size=p.get("file_size", 0),
                    file_hash=p.get("file_hash", ""),
                    embedded_data=p.get("embedded_data"),
                ))
            except (KeyError, TypeError):
                continue

        mc = data.get("music_config")
        if mc:
            profile.music_config = ProfileMusicConfig(
                exclude_vanilla=mc.get("exclude_vanilla", False),
                stage_assignments=mc.get("stage_assignments", {}),
            )

        return profile

    def compare_profile(self, profile: ShareProfile, current_mods: list[Mod],
                        current_plugins: list[Plugin]) -> dict:
        """Compare a profile against current setup."""
        current_mod_names = {m.original_name for m in current_mods}
        current_plugin_names = {
            self._base_plugin_filename(p.filename) for p in current_plugins
        }

        mod_comparison = {
            "matching": [],
            "missing": [],
            "extra": [],
        }

        for pm in profile.mods:
            if pm.name in current_mod_names:
                mod_comparison["matching"].append(pm.name)
            else:
                mod_comparison["missing"].append(pm.name)

        for cm in current_mods:
            if cm.original_name not in {pm.name for pm in profile.mods}:
                mod_comparison["extra"].append(cm.original_name)

        plugin_comparison = {
            "matching": [],
            "missing": [],
            "extra": [],
            "embeddable": [],
        }

        for pp in profile.plugins:
            clean_name = self._base_plugin_filename(pp.filename)
            if clean_name in current_plugin_names:
                plugin_comparison["matching"].append(pp.filename)
            else:
                plugin_comparison["missing"].append(pp.filename)
                if pp.embedded_data:
                    plugin_comparison["embeddable"].append(pp.filename)

        return {
            "mods": mod_comparison,
            "plugins": plugin_comparison,
        }

    def _hash_mod(self, mod_path: Path) -> str:
        """Hash a mod folder for identity."""
        try:
            config = mod_path / "config.json"
            if config.exists():
                return self._hash_file(config)
            # Fallback: hash sorted list of relative file paths
            files = sorted(str(f.relative_to(mod_path)) for f in mod_path.rglob("*") if f.is_file())
            content = "\n".join(files).encode()
            return f"sha256:{hashlib.sha256(content).hexdigest()[:16]}"
        except (PermissionError, OSError):
            return ""

    def _hash_file(self, path: Path) -> str:
        """SHA-256 hash of a file (first 16 hex chars for brevity)."""
        try:
            h = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return f"sha256:{h.hexdigest()[:16]}"
        except (PermissionError, OSError):
            return ""

    def install_embedded_plugins(self, profile: ShareProfile,
                                plugins_path: Path) -> dict:
        """Install embedded plugins from a profile to the plugins directory.

        Returns dict with 'installed' and 'failed' lists.
        """
        result = {"installed": [], "failed": []}

        if not plugins_path.exists():
            plugins_path.mkdir(parents=True, exist_ok=True)

        for pp in profile.plugins:
            if not pp.embedded_data:
                continue

            target = plugins_path / pp.filename
            if target.exists():
                continue  # Already installed

            try:
                data = base64.b64decode(pp.embedded_data)
                with open(target, 'wb') as f:
                    f.write(data)
                result["installed"].append(pp.filename)
            except Exception as e:
                result["failed"].append(f"{pp.filename}: {e}")

        return result

    def _embed_file(self, path: Path) -> Optional[str]:
        """Base64-encode a small file for embedding."""
        try:
            with open(path, 'rb') as f:
                data = f.read()
            return base64.b64encode(data).decode('ascii')
        except Exception:
            return None
