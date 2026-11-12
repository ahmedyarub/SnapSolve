from .base import Source
from .manager import get_active_source_instance, set_active_source_instance
from .screenshot import ScreenshotSource
from .sound import SoundSource
from .text import TextSource

__all__ = [
    "ScreenshotSource",
    "SoundSource",
    "Source",
    "TextSource",
    "get_active_source_instance",
    "set_active_source_instance",
]
