class OCRError(Exception):
    """Base exception for OCR-related errors."""


class OCRInitializationError(OCRError):
    """Raised when the OCR engine fails to initialize."""


class OCRDependencyError(OCRError, ImportError):
    """Raised when a required OCR dependency is not installed."""


class OCRExecutionError(OCRError):
    """Raised when OCR text extraction fails during execution."""


class OCRCancelledError(OCRError):
    """Raised when an OCR operation is cancelled by the user."""
