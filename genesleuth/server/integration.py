"""Require real Side A data for the live server and rehearsal scripts."""

from __future__ import annotations

from types import ModuleType


def case_api(*, dev: bool = False) -> ModuleType:
    """Load the project data adapter with an explicit development boundary."""
    from genesleuth.data import api

    if not dev:
        # The adapter can return fixture cases while its release inputs are missing.
        ready = getattr(api, "real_ready", None) or getattr(api, "_real_ready", None)
        if not callable(ready) or not ready():
            raise RuntimeError("The live case data bundle is not ready.")
    return api
