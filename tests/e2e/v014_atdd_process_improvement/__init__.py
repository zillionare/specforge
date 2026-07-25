"""v0.14-005 ATDD-process-improvement e2e test package.

The CI e2e command explicitly deselects the ``v014_005_full_lifecycle`` marker
(see project.toml [e2e].run); the dedicated full-lifecycle matrix lives in
``test_full_lifecycle.py`` and is invoked by the ``full-lifecycle`` CI job.
"""

from __future__ import annotations
