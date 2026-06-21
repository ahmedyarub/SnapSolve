"""LanguageTool HTTP client for grammar checking.

Wraps the LanguageTool API (both cloud Premium and local server) to provide
grammar corrections in the same format used by ``CorrectionEngine``.
Supports automatic language mapping from the app's transcription language
codes to LanguageTool's regional-variant codes.
"""
import logging
import time

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default language-variant mapping
# ---------------------------------------------------------------------------
# LanguageTool requires regional variants (e.g. ``en-US`` instead of ``en``)
# for spell-checking to work.  The app's transcription language uses bare
# ISO 639-1 codes (``en``, ``de``, ``fr``, …).  This table maps them to
# the most common LanguageTool variant.  Languages without variants (``fr``,
# ``es``, ``nl``, …) are passed through as-is.
_DEFAULT_VARIANT: dict[str, str] = {
    "en": "en-US",
    "de": "de-DE",
    "pt": "pt-BR",
    "nl": "nl-NL",
    "ca": "ca-ES",
}

# Cloud API base URL
_CLOUD_URL = "https://api.languagetoolplus.com"


class LanguageToolClient:
    """HTTP client for LanguageTool's ``/v2/check`` endpoint."""

    def __init__(self, config: dict):
        self._mode: str = config.get("languagetool_mode", "local")
        self._local_url: str = config.get("languagetool_url", "http://localhost:8081")
        self._username: str = config.get("languagetool_username", "")
        self._api_key: str = config.get("languagetool_api_key", "")
        self._language_override: str = config.get("languagetool_language", "auto")
        self._level: str = config.get("languagetool_level", "picky")
        self._transcription_language: str = config.get("transcription_language", "en")
        self._timeout: float = 10.0

        base = _CLOUD_URL if self._mode == "cloud" else self._local_url.rstrip("/")
        self._check_url: str = f"{base}/v2/check"
        self._languages_url: str = f"{base}/v2/languages"

        logger.info(
            "[LanguageTool] mode=%s, url=%s, language_override=%s, level=%s",
            self._mode, self._check_url, self._language_override, self._level,
        )

    # ------------------------------------------------------------------
    # Language resolution
    # ------------------------------------------------------------------

    def _resolve_language(self) -> str:
        """Map the transcription language to a LanguageTool language code.

        If ``languagetool_language`` is set to a specific variant (e.g.
        ``en-US``), that value is used directly.  When set to ``"auto"``
        (the default), the app's ``transcription_language`` is mapped
        through ``_DEFAULT_VARIANT`` so spell-checking is activated for
        languages that require a regional variant.
        """
        if self._language_override and self._language_override != "auto":
            return self._language_override

        lang = self._transcription_language
        if not lang:
            return "auto"

        return _DEFAULT_VARIANT.get(lang, lang)

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    def check(self, text: str, source_sentences: list[str] | None = None) -> list[dict]:
        """Send *text* to LanguageTool and return corrections.

        Each correction is a dict matching the format expected by
        ``CorrectionEngine``:

        .. code-block:: python

            {
                "timestamp": float,
                "type": "grammar",
                "original": str,
                "correction": str,
                "confidence": "HIGH",
                "explanation": str,
                "source_sentences": list[str],
                "rule_id": str,
            }
        """
        language = self._resolve_language()
        data: dict[str, str] = {
            "text": text,
            "language": language,
            "level": self._level,
        }

        # Cloud Premium authentication
        if self._mode == "cloud" and self._username and self._api_key:
            data["username"] = self._username
            data["apiKey"] = self._api_key

        try:
            logger.info(
                "[LanguageTool] Checking %d chars (lang=%s, level=%s)",
                len(text), language, self._level,
            )
            response = requests.post(
                self._check_url, data=data, timeout=self._timeout,
            )
            response.raise_for_status()
            result = response.json()
        except requests.ConnectionError:
            logger.error("[LanguageTool] Connection failed — is the server running at %s?", self._check_url)
            return []
        except requests.Timeout:
            logger.error("[LanguageTool] Request timed out after %.1fs", self._timeout)
            return []
        except requests.RequestException as exc:
            logger.error("[LanguageTool] HTTP error: %s", exc)
            return []
        except ValueError:
            logger.error("[LanguageTool] Invalid JSON response")
            return []

        matches = result.get("matches", [])
        is_premium = result.get("software", {}).get("premium", False)
        logger.info(
            "[LanguageTool] Got %d matches (premium=%s)", len(matches), is_premium,
        )

        corrections: list[dict] = []
        for match in matches:
            original_text = text[match["offset"]:match["offset"] + match["length"]]
            replacements = match.get("replacements", [])
            first_replacement = replacements[0]["value"] if replacements else ""
            rule = match.get("rule", {})

            corrections.append({
                "timestamp": time.time(),
                "type": "grammar",
                "original": original_text,
                "correction": first_replacement,
                "confidence": "HIGH",
                "explanation": match.get("message", ""),
                "source_sentences": source_sentences or [],
                "rule_id": rule.get("id", ""),
            })

        return corrections

    def is_available(self) -> bool:
        """Quick health check — verify the server is reachable."""
        try:
            response = requests.get(self._languages_url, timeout=3.0)
            return response.status_code == 200
        except requests.RequestException:
            return False
