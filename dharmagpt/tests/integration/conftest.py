"""
conftest.py — fixtures and skip guards for integration tests.

All integration tests require live credentials. Any test in this directory
is automatically skipped if any required environment variable is missing —
this means they're safe to collect in CI without credentials, they'll just
be reported as skipped rather than failing.
"""

import os
import pytest

REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "PINECONE_API_KEY",
]


def pytest_collection_modifyitems(config, items):
    """Auto-skip all integration tests when credentials are absent."""
    missing = [v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if not missing:
        return
    skip = pytest.mark.skip(
        reason=f"Integration tests require env vars: {', '.join(missing)}"
    )
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)
