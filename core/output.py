"""Backward-compatible facade — re-exports everything from core.ui.

All existing ``from core.output import ...`` statements continue to work
without modification.  New code should import directly from ``core.ui``
or its submodules.
"""

# Facade: the star import is what callers of ``core.output`` use.
# noinspection PyUnresolvedReferences,PyUnusedImports
from core.ui import *  # noqa: F403


# Re-export the module-level mutable ``ui_manager`` so that callers who do
# ``from core.output import ui_manager`` always see the current value.
# The __init__ import only captures the initial ``None``; this property-style
# re-export via __getattr__ ensures the live singleton is returned.
def __getattr__(name):
    if name == "ui_manager":
        from core.ui.manager import ui_manager

        return ui_manager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
