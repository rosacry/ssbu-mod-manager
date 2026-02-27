import src.config as config_module
from src.config import ConfigManager
from src.models.settings import AppSettings


def test_config_roundtrip_online_metadata(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / ".cfg"
    config_file = config_dir / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    manager = ConfigManager()
    manager.save(
        AppSettings(
            emulator="Eden",
            emulator_version="v0.0.4-rc3",
            game_version="13.0.1",
            online_strict_audio_sync=True,
            online_strict_environment_match=True,
        )
    )

    loaded = ConfigManager().load()
    assert loaded.emulator == "Eden"
    assert loaded.emulator_version == "v0.0.4-rc3"
    assert loaded.game_version == "13.0.1"
    assert loaded.online_strict_audio_sync is True
    assert loaded.online_strict_environment_match is True
