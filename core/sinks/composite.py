import threading
from .base import Sink

class CompositeSink(Sink):
    """
    A Sink that forwards chunks to multiple underlying sinks.
    """
    def __init__(self, sinks: list[Sink], cancel_event: threading.Event = None):
        super().__init__(cancel_event)
        self.sinks = sinks

    def process_chunk(self, chunk: str, is_main: bool = True, replace: bool = False):
        if self.cancel_event.is_set():
            return
        for sink in self.sinks:
            sink.process_chunk(chunk, is_main, replace)

    def finish(self):
        if self.cancel_event.is_set():
            return
        for sink in self.sinks:
            if hasattr(sink, 'finish'):
                sink.finish()
