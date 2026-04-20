from .base import Source

_active_source_instance: Source | None = None

def get_active_source_instance() -> Source | None:
    return _active_source_instance

def set_active_source_instance(instance: Source | None):
    global _active_source_instance
    _active_source_instance = instance
