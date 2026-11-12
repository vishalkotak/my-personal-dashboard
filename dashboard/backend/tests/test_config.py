import pytest

from app.config import load_settings


def test_defaults():
    s = load_settings({})
    assert s.tz_name == "America/Los_Angeles" and not s.demo and s.database_url is None
    assert s.frontend_origins == ("http://localhost:5173", "http://127.0.0.1:5173")


def test_demo_flag_and_tz():
    s = load_settings({"DEMO": "1", "TZ_NAME": "Europe/Berlin", "HEALTH_USER_ID": "6F1C2A3E-0000-4000-8000-000000000001"})
    assert s.demo and s.tz_name == "Europe/Berlin"
    assert s.user_id == "6f1c2a3e-0000-4000-8000-000000000001"


@pytest.mark.parametrize("env", [{"TZ_NAME": "Mars/Olympus"}, {"HEALTH_USER_ID": "nope"}])
def test_invalid_settings_fail_fast(env):
    with pytest.raises(SystemExit):
        load_settings(env)


def test_main_binds_loopback_only():
    from app import __main__ as main

    assert main.HOST == "127.0.0.1"
