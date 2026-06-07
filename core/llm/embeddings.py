import abc
import logging
import numpy as np
from typing import List, Optional

# FORCE PyQt6 initialization in case this module is loaded by a PyTorch child process
try:
    import PyQt6.QtWebEngineWidgets
except ImportError:
    pass

logger = logging.getLogger(__name__)


class EmbeddingEngine(abc.ABC):
    @abc.abstractmethod
    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Returns a 2D numpy array of shape (len(texts), embedding_dim)"""
        pass

    @abc.abstractmethod
    def get_dimension(self) -> int:
        pass


class GeminiEmbeddingEngine(EmbeddingEngine):
    def __init__(self, api_key: str, model_name: str = "text-embedding-004"):
        from google import genai
        self.api_key = api_key
        self.model_name = model_name
        self._client = genai.Client(api_key=api_key)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.get_dimension()))
            
        try:
            response = self._client.models.embed_content(
                model=self.model_name,
                contents=texts
            )
            # response.embeddings is a list of Embedding objects with 'values'
            embeddings = [emb.values for emb in response.embeddings]
            return np.array(embeddings, dtype=np.float32)
        except Exception as e:
            logger.error(f"Gemini embedding failed: {e}")
            # Return zero vectors as fallback
            return np.zeros((len(texts), self.get_dimension()), dtype=np.float32)

    def get_dimension(self) -> int:
        return 768  # text-embedding-004 dimension


class LocalEmbeddingEngine(EmbeddingEngine):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                # Load model lazily
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                logger.error("sentence-transformers is not installed.")
                raise
            except Exception as e:
                logger.error(f"Failed to load local embedding model: {e}")
                raise
        return self._model

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.get_dimension()))
            
        try:
            model = self._get_model()
            embeddings = model.encode(texts, convert_to_numpy=True)
            return embeddings.astype(np.float32)
        except Exception as e:
            logger.error(f"Local embedding failed: {e}")
            return np.zeros((len(texts), self.get_dimension()), dtype=np.float32)

    def get_dimension(self) -> int:
        # all-MiniLM-L6-v2 dimension is 384
        return 384


_active_embedding_engine: Optional[EmbeddingEngine] = None

def get_embedding_engine(config: dict) -> EmbeddingEngine:
    global _active_embedding_engine
    
    engine_type = config.get("embedding_engine", "local")
    
    # Check if we need to recreate the engine
    if _active_embedding_engine is not None:
        if engine_type == "local" and isinstance(_active_embedding_engine, LocalEmbeddingEngine):
            return _active_embedding_engine
        if engine_type == "remote" and isinstance(_active_embedding_engine, GeminiEmbeddingEngine):
            # Check if API key changed
            api_key = config.get("gemini_api_key", "")
            if _active_embedding_engine.api_key == api_key:
                return _active_embedding_engine
                
    if engine_type == "remote":
        api_key = config.get("gemini_api_key", "")
        if not api_key:
            logger.warning("Remote embedding selected but no Gemini API key found. Falling back to local.")
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

