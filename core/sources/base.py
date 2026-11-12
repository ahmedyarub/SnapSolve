import abc


class Source(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_text(self, *args, **kwargs) -> str:
        """Retrieves text from the source. Raises ValueError if unsupported or unavailable."""

    @abc.abstractmethod
    def get_image(self, *args, **kwargs) -> str:
        """Retrieves image path from the source. Raises ValueError if unsupported."""


class ImageSource(Source, abc.ABC):
    """Base for image sources; subclasses implement get_text and get_image."""

    @property
    def name(self):
        return "image"
