"""Shared pytest configuration for louke tests.

Registers project-level markers (e.g. ``e2e``) so that ``-m e2e`` selection
and ``--markers`` listing work without an explicit pytest.ini.
"""

import os


def pytest_configure(config):
    """Register the ``e2e`` marker for end-to-end browser tests (Playwright).

    Args:
        config: the pytest Config object.
    """
    config.addinivalue_line("markers", "e2e: end-to-end browser test (Playwright)")
    config.addinivalue_line(
        "markers",
        "integration: integration test (real TestClient / temp store / HTTP), "
        "not a browser E2E (see gap-analysis §3 P1-1 / issue #177)",
    )
    config.addinivalue_line(
        "markers",
        "real_opencode: L3 smoke test that requires a live OpenCode provider "
        "(run only when LOUKE_RUN_REAL_OPENCODE=1 and real credentials are set)",
    )


def pytest_runtest_setup(item):
    """Set lifecycle scenario env var for parametrized lifecycle tests.

    The full-lifecycle fail tests are parametrized with ``failed_stage``,
    but the endpoint receives only the project_id from the URL. This hook
    communicates the parametrize value to the production code via an
    environment variable so the projection can halt at the correct stage.
    """
    if hasattr(item, "callspec") and "failed_stage" in item.callspec.params:
        os.environ["LOUKE_LIFECYCLE_FAIL_STAGE"] = item.callspec.params["failed_stage"]


def pytest_runtest_teardown(item, nextitem):
    """Clean up lifecycle scenario env var after each test."""
    os.environ.pop("LOUKE_LIFECYCLE_FAIL_STAGE", None)
