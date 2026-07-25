"""Louke web app (counterexample): ATDD route stub dropped."""

from starlette.applications import Starlette


def create_app(*, project_root=None, **kwargs):
    """Counterexample create_app stub."""
    return Starlette(routes=[])
