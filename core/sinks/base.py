import abc

class Sink(abc.ABC):
    @abc.abstractmethod
    def process_chunk(self, chunk: str, is_main: bool = True, replace: bool = False):
        pass
