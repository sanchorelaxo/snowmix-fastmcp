import pytest


def pytest_configure(config):
    config.option.asyncio_mode = "auto"
