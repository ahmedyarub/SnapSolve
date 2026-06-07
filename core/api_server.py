import asyncio
import json
import logging
import os
import threading
from typing import Any, Optional, Dict

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Header
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

import core.remote_control_server as rc_server
from core.remote_control_server import (
    _handle_action,
    _handle_mouse_move,
    _handle_mouse_click,
    _handle_mouse_double_click,
    _handle_mouse_drag_start,
    _handle_mouse_drag_end,
    _handle_mouse_scroll,
    _handle_keyboard_type,
    _handle_set_transcription_language,
    mouse_blocker,
    _handle_connect,
    _handle_disconnect,
    _response_image_lock
)

logger = logging.getLogger(__name__)

app = FastAPI(title="SnapSolve API Server", docs_url="/")

# Application config dependency
_app_config: Dict[str, Any] = {}
_api_key: str = ""


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="Authorization")):
    if _api_key:
        if not x_api_key or x_api_key != _api_key:
            raise HTTPException(status_code=401, detail="Invalid API Key")
    return True


@app.get("/health", dependencies=[Depends(verify_api_key)])
async def health_check():
    import app.state as state
    import requests
    from core.sources.sound import is_whisperlive_service_online

    ocr_status = "None"
    if state.ocr_engine_instance:
        ocr_status = type(state.ocr_engine_instance).__name__

    whisperlive_status = "online" if is_whisperlive_service_online() else "offline"

    antigravity_status = "offline"
    try:
        if requests.get("http://localhost:8200/health", timeout=1).status_code == 200:
            antigravity_status = "online"
    except Exception:
        pass

    return {
        "status": "running",
        "server": "SnapSolve API Server",
        "downstream_services": {
            "ocr": ocr_status,
            "whisperlive": whisperlive_status,
            "antigravity": antigravity_status
        }
    }


@app.get("/config", dependencies=[Depends(verify_api_key)])
async def get_config():
    import copy
    redacted_config = copy.deepcopy(_app_config)
    for key in ["api_server_key", "google_api_key", "gemini_api_key", "ollama_api_key", "groq_api_key",
                "anthropic_api_key", "openai_api_key"]:
        if key in redacted_config and redacted_config[key]:
            redacted_config[key] = "***REDACTED***"
    return redacted_config


@app.get("/status")
async def status():
    # Legacy endpoint for Android client
    return {"status": "running", "server": "SnapSolve Remote Control"}


@app.get("/response_image")
async def get_response_image():
    # Legacy endpoint for Android client
    with _response_image_lock:
        image_path = rc_server._response_image_path

    if not image_path or not os.path.exists(image_path):
        return JSONResponse(status_code=404, content={"error": "No response image available"})
    return FileResponse(image_path, media_type="image/png")


# REST endpoints for actions and mouse/keyboard
class ActionRequest(BaseModel):
    action: str


@app.post("/action", dependencies=[Depends(verify_api_key)])
async def trigger_action(req: ActionRequest):
    result = _handle_action({"action": req.action}, _app_config)
    if result and result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


class MouseMoveRequest(BaseModel):
    dx: float
    dy: float


@app.post("/mouse/move", dependencies=[Depends(verify_api_key)])
async def mouse_move(req: MouseMoveRequest):
    result = _handle_mouse_move({"dx": req.dx, "dy": req.dy}, _app_config)
    if result and result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return {"status": "success"}


class MouseClickRequest(BaseModel):
    button: str = "left"


@app.post("/mouse/click", dependencies=[Depends(verify_api_key)])
async def mouse_click(req: MouseClickRequest):
    result = _handle_mouse_click({"button": req.button}, _app_config)
    if result and result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@app.post("/mouse/double_click", dependencies=[Depends(verify_api_key)])
async def mouse_double_click(req: MouseClickRequest):
    result = _handle_mouse_double_click({"button": req.button}, _app_config)
    if result and result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@app.post("/mouse/drag/start", dependencies=[Depends(verify_api_key)])
async def mouse_drag_start():
    result = _handle_mouse_drag_start(_app_config)
    if result and result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@app.post("/mouse/drag/end", dependencies=[Depends(verify_api_key)])
async def mouse_drag_end():
    result = _handle_mouse_drag_end(_app_config)
    if result and result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


class MouseScrollRequest(BaseModel):
    delta: float


@app.post("/mouse/scroll", dependencies=[Depends(verify_api_key)])
async def mouse_scroll(req: MouseScrollRequest):
    result = _handle_mouse_scroll({"delta": req.delta}, _app_config)
    if result and result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


class KeyboardTypeRequest(BaseModel):
    text: str


@app.post("/keyboard/type", dependencies=[Depends(verify_api_key)])
async def keyboard_type(req: KeyboardTypeRequest):
    result = _handle_keyboard_type({"text": req.text}, _app_config)
    if result and result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@app.post("/response_image/ack", dependencies=[Depends(verify_api_key)])
async def response_image_ack():
    result = rc_server._handle_response_image_ack()
    if result and result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


class SetTranscriptionLanguageRequest(BaseModel):
    language: str


@app.post("/config/transcription_language", dependencies=[Depends(verify_api_key)])
async def set_transcription_language(req: SetTranscriptionLanguageRequest):
    result = _handle_set_transcription_language({"language": req.language}, _app_config)
    if result and result.get("type") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


# Screenpipe-like endpoints
@app.get("/search", dependencies=[Depends(verify_api_key)])
async def search_sessions(
    q: Optional[str] = None, 
    limit: int = 20, 
    offset: int = 0,
    semantic: bool = False,
    types: Optional[str] = None
):
    import app.state as state
    manager = state.session_manager
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")

    allowed_types = set(types.split(",")) if types else {"prompt", "response", "transcription", "app_name", "summary", "tag"}
    
    if not semantic or not q:
        # Standard text search across chunks
        all_chunks = manager.get_all_embeddings()
        
        results_map = {}
        q_lower = q.lower() if q else ""
        
        for c in all_chunks:
            if c.get("type") in allowed_types:
                if q_lower and q_lower not in c.get("text", "").lower():
                    continue
                    
                s_id = c.get("session_id")
                if s_id not in results_map:
                    results_map[s_id] = {
                        "id": s_id,
                        "timestamp": 0,
                        "tags": []
                    }
        
        # Populate session metadata
        sessions = manager.list_all_sessions()
        final_results = []
        for s in sessions:
            s_id = s.get("id")
            if not q_lower:
                # If no query, return all sessions
                final_results.append({
                    "id": s_id,
                    "name": s.get("name") or s.get("title") or s_id,
                    "timestamp": s.get("updated_at", 0),
                    "tags": s.get("tags", [])
                })
            elif s_id in results_map:
                res = results_map[s_id]
                res["name"] = s.get("name") or s.get("title") or s_id
                res["timestamp"] = s.get("updated_at", 0)
                res["tags"] = s.get("tags", [])
                final_results.append(res)
                
        final_results.sort(key=lambda x: x["timestamp"], reverse=True)
        return {"data": final_results[offset:offset + limit], "total": len(final_results)}

    # Semantic search logic
    try:
        from core.llm.embeddings import get_embedding_engine
        import numpy as np
        engine = get_embedding_engine(_app_config)
        query_embedding = engine.embed_texts([q])[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {e}")
        
    all_chunks = manager.get_all_embeddings()
    if not all_chunks:
        return {"data": [], "total": 0}
        
    allowed_types = set(types.split(",")) if types else {"prompt", "response", "transcription", "app_name", "summary", "tag"}
    
    filtered_chunks = []
    chunk_embeddings = []
    
    for c in all_chunks:
        if c.get("type") in allowed_types:
            emb = c.get("embedding")
            if emb:
                filtered_chunks.append(c)
                chunk_embeddings.append(emb)
                
    if not filtered_chunks:
        return {"data": [], "total": 0}
        
    chunk_embeddings_np = np.array(chunk_embeddings, dtype=np.float32)
    norms = np.linalg.norm(chunk_embeddings_np, axis=1)
    q_norm = np.linalg.norm(query_embedding)
    
    norms[norms == 0] = 1.0
    if q_norm == 0:
        q_norm = 1.0
        
    similarities = np.dot(chunk_embeddings_np, query_embedding) / (norms * q_norm)
    top_indices = np.argsort(similarities)[::-1]
    
    results = []
    for idx in top_indices:
        sim = float(similarities[idx])
        if sim < 0.15:  # lower threshold to allow more results
            continue
            
        c = filtered_chunks[idx]
        results.append({
            "session_id": c["session_id"],
            "type": c["type"],
            "index": c["index"],
            "text": c["text"],
            "score": sim
        })
        
    sliced_results = results[offset:offset + limit]
    return {"data": sliced_results, "total": len(results)}



@app.get("/tags", dependencies=[Depends(verify_api_key)])
async def get_tags():
    import app.state as state
    manager = state.session_manager
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")

    sessions = manager.list_all_sessions()
    all_tags = set()
    for s in sessions:
        for tag in s.get("tags", []):
            all_tags.add(tag)

    return {"data": list(all_tags)}


@app.get("/sessions", dependencies=[Depends(verify_api_key)])
async def get_sessions(limit: int = 20, offset: int = 0):
    import app.state as state
    manager = state.session_manager
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")

    sessions = manager.list_all_sessions()
    sessions.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    results = [{"id": s.get("id"), "name": s.get("name") or s.get("title") or "", "timestamp": s.get("updated_at"),
                "tags": s.get("tags", [])} for s in sessions[offset:offset + limit]]
    return {"data": results, "total": len(sessions)}


@app.get("/sessions/{session_id}", dependencies=[Depends(verify_api_key)])
async def get_session(session_id: str):
    import app.state as state
    manager = state.session_manager
    if not manager:
        raise HTTPException(status_code=500, detail="Session manager not initialized")

    session_data = manager.load_session_data(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    history = session_data.get("history", [])
    return {
        "id": session_id,
        "name": session_data.get("name") or session_data.get("title") or "",
        "tags": session_data.get("tags", []),
        "history": [msg if isinstance(msg, dict) else msg.model_dump_json() for msg in history]
    }


# Active websocket connections list for push updates
_active_websockets: list[WebSocket] = []


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    _active_websockets.append(websocket)
    # Trigger handle connect
    resp = _handle_connect(_app_config)
    await websocket.send_text(json.dumps(resp))

    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError as exc:
                await websocket.send_text(json.dumps({"type": "error", "message": f"Invalid JSON: {exc}"}))
                continue

            msg_type = data.get("type")
            if not msg_type:
                await websocket.send_text(json.dumps({"type": "error", "message": "Missing 'type' field"}))
                continue

            handlers = {
                "action": lambda: _handle_action(data, _app_config),
                "mouse_move": lambda: _handle_mouse_move(data, _app_config),
                "mouse_click": lambda: _handle_mouse_click(data, _app_config),
                "mouse_double_click": lambda: _handle_mouse_double_click(data, _app_config),
                "mouse_drag_start": lambda: _handle_mouse_drag_start(_app_config),
                "mouse_drag_end": lambda: _handle_mouse_drag_end(_app_config),
                "mouse_scroll": lambda: _handle_mouse_scroll(data, _app_config),
                "keyboard_type": lambda: _handle_keyboard_type(data, _app_config),
                "response_image_ack": lambda: rc_server._handle_response_image_ack(),
                "set_transcription_language": lambda: _handle_set_transcription_language(data, _app_config),
            }

            handler = handlers.get(msg_type)
            if handler is None:
                await websocket.send_text(json.dumps({"type": "error", "message": f"Unknown message type: {msg_type}"}))
                continue

            response = handler()
            if response:
                await websocket.send_text(json.dumps(response))

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.debug("WebSocket connection error: %s", exc)
    finally:
        _active_websockets.remove(websocket)
        if len(_active_websockets) == 0:
            _handle_disconnect()


async def broadcast_state(state: dict[str, dict[str, bool]]):
    with _response_image_lock:
        has_image = rc_server._has_new_response_image

    message = json.dumps({
        "type": "state_update",
        "buttons": state,
        "has_new_response_image": has_image,
        "transcription_language": _app_config.get("transcription_language", "en"),
        "periodic_screenshots_enabled": _app_config.get("periodic_screenshots_enabled", False),
    })

    for ws in _active_websockets:
        try:
            await ws.send_text(message)
        except Exception:
            pass


class APIServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 3031, config: Optional[dict] = None):
        self.host = host
        self.port = port
        global _app_config, _api_key
        _app_config = config or {}
        _api_key = _app_config.get("api_server_key", "")
        self.is_running = False
        self._server_thread: Optional[threading.Thread] = None
        self._uvicorn_server: Optional[uvicorn.Server] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self):
        if self.is_running:
            return

        self.is_running = True
        self._server_thread = threading.Thread(target=self._run_server, daemon=True, name="APIServer")
        self._server_thread.start()
        logger.info("API server starting on http://%s:%s", self.host, self.port)

    def _run_server(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        config = uvicorn.Config(app=app, host=self.host, port=self.port, log_level="warning")
        self._uvicorn_server = uvicorn.Server(config)

        try:
            self._loop.run_until_complete(self._uvicorn_server.serve())
        except Exception as exc:
            logger.error("API Server error: %s", exc)
        finally:
            self.is_running = False

    def schedule_push_state(self, state: dict[str, dict[str, bool]]):
        if self._loop and self.is_running:
            asyncio.run_coroutine_threadsafe(broadcast_state(state), self._loop)

    def stop(self):
        if not self.is_running:
            return

        mouse_blocker.unblock()
        self.is_running = False

        if self._uvicorn_server and self._loop:
            self._uvicorn_server.should_exit = True

        if self._server_thread:
            self._server_thread.join(timeout=5)

        logger.info("API server stopped")


api_server_instance: Optional[APIServer] = None


def start_api_server(host: str = "0.0.0.0", port: int = 3031, config: Optional[dict] = None) -> APIServer:
    global api_server_instance
    if api_server_instance is None:
        api_server_instance = APIServer(host, port, config)

    assert api_server_instance is not None

    api_server_instance.start()
    return api_server_instance


def stop_api_server() -> None:
    global api_server_instance
    if api_server_instance:
        api_server_instance.stop()
        api_server_instance = None
