from src.ui.pages.settings_page import is_valid_game_version, normalize_game_version


def test_normalize_game_version() -> None:
    assert normalize_game_version(" v13.0.1 ") == "13.0.1"
    assert normalize_game_version("13,0,1") == "13.0.1"
    assert normalize_game_version("13 . 0 . 1") == "13.0.1"


def test_validate_game_version_format() -> None:
    assert is_valid_game_version("")
    assert is_valid_game_version("13")
    assert is_valid_game_version("13.0")
    assert is_valid_game_version("13.0.1")
    assert is_valid_game_version("v13.0.1")

    assert not is_valid_game_version("13.0.beta")
    assert not is_valid_game_version("version13")
