import abc


class OCREngine(abc.ABC):
    @abc.abstractmethod
    def extract_text(self, image_path: str, status_callback=None) -> str:
        pass
