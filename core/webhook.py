"""Webhook support for post-session actions."""
import json
import logging
import threading
import urllib.request
import urllib.error
from typing import Optional

from core.session_manager import SessionManager


logger = logging.getLogger(__name__)


def _send_webhook_thread(url: str, payload: dict):
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            logger.info(f"Webhook triggered successfully: {response.status}")
    except urllib.error.URLError as e:
        logger.error(f"Failed to trigger webhook {url}: {e.reason}")
    except Exception as e:
        logger.error(f"Unexpected error triggering webhook {url}: {e}")


def trigger_webhook(config: dict, session_manager: SessionManager, session_id: str, summary_text: Optional[str] = None):
    """Trigger a webhook asynchronously with session data."""
    webhook_url = config.get("webhook_url", "").strip()
    if not webhook_url:
        return
        
    session_data = session_manager.load_session_data(session_id)
    if not session_data:
        logger.warning(f"Webhook: Could not load session data for {session_id}")
        return
        
    payload = {
        "event": "session_summary" if summary_text else "manual_trigger",
        "session_id": session_id,
        "title": session_data.get("title"),
        "name": session_data.get("name"),
        "tags": session_data.get("tags", []),
        "speaker_name": session_data.get("speaker_name"),
    }
    
    if summary_text:
        payload["summary"] = summary_text
        
    thread = threading.Thread(target=_send_webhook_thread, args=(webhook_url, payload), daemon=True)
    thread.start()
