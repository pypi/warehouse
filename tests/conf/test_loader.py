import os
import pytest

from warehouse.conf.loader import load_yaml_config, envvar_settings


FILENAME = os.path.join(os.path.dirname(__file__), "test_config.yaml")


@pytest.mark.parametrize(("filename", "environment", "expected"), [
    (None, "DEVELOPMENT", {}),
    (FILENAME, "DEVELOPMENT", {"SECRET_KEY": "secret key!", "DEBUG": True}),
    (FILENAME, "PRODUCTION", {"SECRET_KEY": "secret key!"}),
])
def test_load_yaml_config(filename, environment, expected):
    assert load_yaml_config(filename, environment) == expected


@pytest.mark.parametrize(("environment", "expected"), [
    ({"WAREHOUSE_CONF": "foo.yaml"}, {}),
    ({}, {"SECRET_KEY": "INSECURE, DO NOT USE"}),
])
def test_envvar_settings(environment, expected):
    assert envvar_settings(environment) == expected
