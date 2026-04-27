import abc

class Source(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_text(self, *args, **kwargs) -> str:
        """Retrieves text from the source. Raises ValueError if unsupported or unavailable."""
        pass

    @abc.abstractmethod
    def get_image(self, *args, **kwargs) -> str:
        """Retrieves image path from the source. Raises ValueError if unsupported."""
        pass

class ImageSource(Source):
    @property
    def name(self):
        return "image"
