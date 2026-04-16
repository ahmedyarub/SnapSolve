import abc

class Source(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self):
        pass

class ImageSource(Source):
    @property
    def name(self):
        return "image"

class TextSource(Source):
    @property
    def name(self):
        return "text"
