"""Repository-wide pytest defaults for external-service tests."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run tests marked as requiring external services",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return

    skip_integration = pytest.mark.skip(
        reason="integration test skipped; use --run-integration to enable it"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
