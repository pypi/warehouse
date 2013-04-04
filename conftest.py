import os


def pytest_addoption(parser):
    group = parser.getgroup("warehouse tests")
    group.addoption(
        "--config",
        dest="config",
        help="A .yaml file with config",
    )
    group.addoption(
        "--environment",
        dest="environment",
        help="A Warehouse environment name (default: TEST)",
        default="TEST",
    )


def pytest_configure(config):
    configfile = config.getoption("config")
    if configfile:
        os.environ["WAREHOUSE_CONF"] = configfile

    os.environ["WAREHOUSE_ENV"] = config.getoption("environment")
