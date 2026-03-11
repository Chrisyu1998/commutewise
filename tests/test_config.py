from src import config


def test_default_constants() -> None:
    assert config.DEFAULT_TIMEZONE == "America/Los_Angeles"
    assert config.DEFAULT_RISK_MODE == "balanced"


def test_get_default_home_and_office() -> None:
    home = config.get_default_home_config()
    office = config.get_default_office_config()

    assert home.name == "Home"
    assert home.place.label == "Home"

    assert office.name == "Office"
    assert office.place.label == "Office"


def test_default_app_config_uses_helpers() -> None:
    app_cfg = config.default_app_config()

    assert app_cfg.default_timezone == config.DEFAULT_TIMEZONE
    assert app_cfg.home.name == "Home"
    assert app_cfg.office.name == "Office"
    assert app_cfg.default_risk_mode == config.DEFAULT_RISK_MODE

