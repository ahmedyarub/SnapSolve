import abc
import logging
import threading

import numpy as np

# FORCE PyQt6 initialization in case this module is loaded by a PyTorch child process
try:
    import PyQt6.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Embedding failed. Callers must not store or compare against a result."""


class EmbeddingEngine(abc.ABC):
    @abc.abstractmethod
    def embed_texts(self, texts: list[str]) -> np.ndarray:
        """Returns a 2D numpy array of shape (len(texts), embedding_dim).

        Raises EmbeddingError when the texts cannot be embedded.
        """

    @abc.abstractmethod
    def get_dimension(self) -> int:
        pass


class GeminiEmbeddingEngine(EmbeddingEngine):
    def __init__(self, api_key: str, model_name: str = "text-embedding-004"):
        from google import genai

        self.api_key = api_key
        self.model_name = model_name
        self._client = genai.Client(api_key=api_key)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.get_dimension()))

        try:
            response = self._client.models.embed_content(
                model=self.model_name, contents=texts
            )
            # response.embeddings is a list of Embedding objects with 'values'
            embeddings = [emb.values for emb in response.embeddings]
            return np.array(embeddings, dtype=np.float32)
        except Exception as e:
            raise EmbeddingError(f"Gemini embedding failed: {e}") from e

    def get_dimension(self) -> int:
        return 768  # text-embedding-004 dimension


class LocalEmbeddingEngine(EmbeddingEngine):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._model_lock = threading.Lock()

    def _get_model(self):
        # Indexing threads and searches may ask at the same time; load it once.
        with self._model_lock:
            if self._model is None:
                self._model = self._load_model()
            return self._model

    def _load_model(self):
        """Load the sentence-transformers model (seconds; imports torch)."""
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.error("sentence-transformers is not installed.")
            raise
        try:
            return SentenceTransformer(self.model_name)
        except Exception as e:
            logger.error(f"Failed to load local embedding model: {e}")
            raise

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.get_dimension()))

        try:
            model = self._get_model()
            embeddings = model.encode(texts, convert_to_numpy=True)
            return embeddings.astype(np.float32)
        except Exception as e:
            raise EmbeddingError(f"Local embedding failed: {e}") from e

    def get_dimension(self) -> int:
        # all-MiniLM-L6-v2 dimension is 384
        return 384


_active_embedding_engine: EmbeddingEngine | None = None
_engine_lock = threading.Lock()


def get_embedding_engine(config: dict) -> EmbeddingEngine:
    with _engine_lock:
        return _select_embedding_engine(config)


def _select_embedding_engine(config: dict) -> EmbeddingEngine:
    global _active_embedding_engine

    engine_type = config.get("embedding_engine", "local")

    # Check if we need to recreate the engine
    if _active_embedding_engine is not None:
        if engine_type == "local" and isinstance(
            _active_embedding_engine, LocalEmbeddingEngine
        ):
            return _active_embedding_engine
        if engine_type == "remote" and isinstance(
            _active_embedding_engine, GeminiEmbeddingEngine
        ):
            # Check if API key changed
            api_key = config.get("gemini_api_key", "")
            if _active_embedding_engine.api_key == api_key:
                return _active_embedding_engine

    if engine_type == "remote":
        api_key = config.get("gemini_api_key", "")
        if not api_key:
            logger.warning(
                "Remote embedding selected but no Gemini API key found. Falling back to local."
            )
            engine_type = "local"
        else:
            _active_embedding_engine = GeminiEmbeddingEngine(api_key=api_key)
            return _active_embedding_engine

    if engine_type == "local":
        _active_embedding_engine = LocalEmbeddingEngine()
        return _active_embedding_engine

    # Default fallback
    _active_embedding_engine = LocalEmbeddingEngine()
    return _active_embedding_engine
