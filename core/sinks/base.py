import abc
import threading


class Sink(abc.ABC):
    def __init__(self, cancel_event: threading.Event = None):
        self.cancel_event = cancel_event or threading.Event()

    @abc.abstractmethod
    def process_chunk(self, chunk: str, is_main: bool = True, replace: bool = False):
        pass
